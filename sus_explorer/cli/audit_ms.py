"""
Auditoria independente MS × Cubo SI-PNI no Cloudflare R2.

Compara diretamente:
  - Fonte oficial: ZIP do Ministério da Saúde / OpenDataSUS
  - Target: bucket sus-dados / prefixo cache/pni_cube no Cloudflare R2

INDEPENDÊNCIA DO AUDITOR:
    Este módulo NÃO importa lógica de transformação de sus_explorer.transform.pni.
    As funções norm() e age_band() são implementadas localmente para evitar
    common-mode failure: um bug no pipeline não pode ser reproduzido automaticamente
    pelo auditor.

    Infraestrutura neutra reutilizada:
        - sus_explorer.config.settings (credenciais — sem vazar valores)
        - sus_explorer.paths (paths de saída de auditoria)

Uso:
    python -m sus_explorer.cli.audit_ms --year 2023 --month 10
    python -m sus_explorer.cli.audit_ms --year 2023 --month 10 \\
        --zip-path /path/to/vacinacao_out_2023_csv.zip \\
        --resource-id bb1c023c-e524-48ff-8471-f68f6cdf189e
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import warnings
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pyarrow.fs as pa_fs
import pyarrow.parquet as pq

from ..config import settings
from ..paths import PROJECT_ROOT


# ─────────────────────────────────────────────────────────────────────────────
# Constantes — implementação independente, não importada de transform.pni
# ─────────────────────────────────────────────────────────────────────────────

# 27 UFs brasileiras — cópia local intencional para independência da auditoria.
UFS: frozenset[str] = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})

# Colunas originais lidas do CSV oficial.
USECOLS = [
    "sg_uf_estabelecimento",
    "co_municipio_estabelecimento",
    "no_municipio_estabelecimento",
    "co_vacina",
    "tp_sexo_paciente",
    "nu_idade_paciente",
    "ds_tipo_dose",
]

# Chaves do cubo — definidas aqui independentemente de CUBE_ALIASES.
KEYS = [
    "uf",
    "municipality_code",
    "municipality_name",
    "vaccine_code",
    "sex",
    "age_band",
    "dose",
]

# Encoding do CSV oficial do MS (cp1252 = Windows-1252).
CSV_ENCODING = "cp1252"

# Diretório de auditoria.
AUDIT_CROSSCHECK = PROJECT_ROOT / "audit" / "ms_crosscheck"


# ─────────────────────────────────────────────────────────────────────────────
# Transformações independentes
# Implementação propositalmente independente de sus_explorer.transform.pni
# para garantir auditoria cega e isenta de common-mode failure.
# ─────────────────────────────────────────────────────────────────────────────

def norm(s: pd.Series) -> pd.Series:
    """Normaliza string: strip + fillna('IGNORADO')."""
    return (
        s.astype("string")
        .str.strip()
        .fillna("IGNORADO")
    )


def age_band(s: pd.Series) -> pd.Series:
    """Classifica idade em faixa etária."""
    x = pd.to_numeric(s, errors="coerce")
    return pd.cut(
        x,
        bins=[-1, 4, 9, 14, 19, 29, 39, 49, 59, 69, 79, 200],
        labels=[
            "00-04", "05-09", "10-14", "15-19",
            "20-29", "30-39", "40-49", "50-59",
            "60-69", "70-79", "80+",
        ],
        include_lowest=True,
        right=True,
    ).astype("string").fillna("IGNORADA")


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários de I/O (semânticamente neutros — permitidos pelo escopo)
# ─────────────────────────────────────────────────────────────────────────────

def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Calcula SHA-256 de um arquivo em chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def make_audit_filesystem() -> pa_fs.S3FileSystem:
    """
    Cria filesystem S3 para o bucket sus-dados (read-only audit).

    Usa exclusivamente SUS_DATA_R2_* — sem fallback para healthbr-data.
    Levanta RuntimeError se as credenciais não estiverem configuradas.
    """
    endpoint = settings.sus_data_r2_endpoint
    access_key = settings.sus_data_r2_access_key
    secret_key = settings.sus_data_r2_secret_key

    if not all([endpoint, access_key, secret_key]):
        missing = []
        if not endpoint:
            missing.append("SUS_DATA_R2_ENDPOINT")
        if not access_key:
            missing.append("SUS_DATA_R2_ACCESS_KEY_ID")
        if not secret_key:
            missing.append("SUS_DATA_R2_SECRET_ACCESS_KEY")
        raise RuntimeError(
            f"Credenciais ausentes para o bucket de auditoria: {', '.join(missing)}"
        )

    return pa_fs.S3FileSystem(
        endpoint_override=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region="auto",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Leitura do ZIP oficial do MS
# ─────────────────────────────────────────────────────────────────────────────

def read_ms_zip(
    zip_path: Path,
    year: int,
    month: int,
    chunk_size: int = 250_000,
) -> tuple[pd.DataFrame, int, int, int, list[dict]]:
    """
    Lê o ZIP oficial do MS, agrega por KEYS, e separa registros não particionáveis.

    Returns:
        ms_df:                  DataFrame agrupado por KEYS com coluna ms_doses
        raw_rows:               Total de linhas no CSV
        partitionable_rows:     Linhas com UF válida
        unpartitionable_rows:   Linhas com UF inválida/ausente
        unpartitionable_sample: Lista de dicts com campos mínimos dos registros não particionáveis
    """
    aggregates: list[pd.DataFrame] = []
    raw_rows = 0
    partitionable_rows = 0
    unpartitionable_rows = 0
    unpartitionable_sample: list[dict] = []

    with ZipFile(zip_path) as z:
        csvs = [x for x in z.namelist() if x.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise RuntimeError(f"Esperava 1 CSV no ZIP, encontrei: {csvs}")

        with z.open(csvs[0]) as raw:
            reader = pd.read_csv(
                raw,
                sep=";",
                encoding=CSV_ENCODING,
                usecols=USECOLS,
                dtype="string",
                chunksize=chunk_size,
                low_memory=False,
            )

            for n, pdf in enumerate(reader, 1):
                raw_rows += len(pdf)

                uf_col = (
                    pdf["sg_uf_estabelecimento"]
                    .astype("string")
                    .str.strip()
                    .str.upper()
                )

                valid = uf_col.isin(UFS)

                partitionable_rows += int(valid.sum())
                unpartitionable_n = int((~valid).sum())
                unpartitionable_rows += unpartitionable_n

                # Persiste apenas campos mínimos necessários à auditoria
                if unpartitionable_n > 0:
                    inv = pdf.loc[~valid].copy()
                    for _, row in inv.iterrows():
                        unpartitionable_sample.append({
                            "year": year,
                            "month": month,
                            "sg_uf_estabelecimento": str(row.get("sg_uf_estabelecimento", "")),
                            "co_municipio_estabelecimento": str(row.get("co_municipio_estabelecimento", "")),
                        })

                pdf = pdf.loc[valid].copy()
                uf_col = uf_col.loc[valid]

                if pdf.empty:
                    continue

                x = pd.DataFrame({
                    "uf": uf_col,
                    "municipality_code": norm(pdf["co_municipio_estabelecimento"]),
                    "municipality_name": norm(pdf["no_municipio_estabelecimento"]),
                    "vaccine_code": norm(pdf["co_vacina"]),
                    "sex": norm(pdf["tp_sexo_paciente"]),
                    "age_band": age_band(pdf["nu_idade_paciente"]),
                    "dose": norm(pdf["ds_tipo_dose"]),
                })

                g = (
                    x.groupby(KEYS, dropna=False, observed=True)
                    .size()
                    .reset_index(name="ms_doses")
                )
                aggregates.append(g)

                print(
                    f"\r  chunk {n} | {raw_rows:,} linhas",
                    end="",
                    flush=True,
                )

    print()

    # Reagrupa — a mesma chave pode aparecer em vários chunks.
    ms_df = pd.concat(aggregates, ignore_index=True)
    ms_df = (
        ms_df.groupby(KEYS, dropna=False, observed=True, as_index=False)["ms_doses"]
        .sum()
    )

    return ms_df, raw_rows, partitionable_rows, unpartitionable_rows, unpartitionable_sample


# ─────────────────────────────────────────────────────────────────────────────
# Leitura do cubo no Cloudflare R2 (sus-dados)
# ─────────────────────────────────────────────────────────────────────────────

def read_r2_cube(
    s3: pa_fs.S3FileSystem,
    year: int,
    month: int,
) -> pd.DataFrame:
    """
    Lê as 27 partições do cubo SI-PNI diretamente do Cloudflare R2 (sus-dados).

    Estrutura esperada:
        sus-dados/cache/pni_cube/ano=YYYY/uf=UF/mes=MM/cube.parquet

    Lança FileNotFoundError se alguma partição estiver ausente.
    Agrupa defensivamente para eliminar eventual duplicação.
    """
    bucket = settings.sus_data_r2_bucket
    prefix = settings.sus_data_r2_cube_prefix
    cubes: list[pd.DataFrame] = []

    for uf in sorted(UFS):
        r2_path = f"{bucket}/{prefix}/ano={year}/uf={uf}/mes={month:02d}/cube.parquet"

        try:
            f = s3.open_input_file(r2_path)
        except Exception as exc:
            raise FileNotFoundError(
                f"Partição ausente no R2: {r2_path}"
            ) from exc

        table = pq.read_table(f)
        c = table.to_pandas()

        # Garante que 'uf' existe (pode ou não estar materializado)
        c["uf"] = uf

        wanted = KEYS + ["doses"]
        missing = [col for col in wanted if col not in c.columns]
        if missing:
            raise RuntimeError(
                f"{r2_path}: colunas ausentes no cubo: {missing}"
            )

        c = c[wanted].copy()
        c = c.rename(columns={"doses": "cube_doses"})
        cubes.append(c)

        print(f"  R2 {uf} OK ({len(c):,} linhas)", flush=True)

    cube_df = pd.concat(cubes, ignore_index=True)

    # Defesa extra contra duplicação acidental.
    cube_df = (
        cube_df.groupby(KEYS, dropna=False, observed=True, as_index=False)["cube_doses"]
        .sum()
    )

    return cube_df


# ─────────────────────────────────────────────────────────────────────────────
# Comparação MS × R2
# ─────────────────────────────────────────────────────────────────────────────

def compare_ms_vs_cube(
    ms_df: pd.DataFrame,
    cube_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Outer join MS × R2 e calcula métricas de comparação.

    Returns:
        different:   DataFrame com linhas que diferem (vazio se EXACT_MATCH)
        metrics:     dict com missing_from_bucket, extra_in_bucket, etc.
    """
    diff = ms_df.merge(cube_df, on=KEYS, how="outer", indicator=True)

    diff["ms_doses"] = diff["ms_doses"].fillna(0).astype("int64")
    diff["cube_doses"] = diff["cube_doses"].fillna(0).astype("int64")
    diff["delta"] = diff["cube_doses"] - diff["ms_doses"]

    different = diff[
        (diff["delta"] != 0) | (diff["_merge"] != "both")
    ].copy()

    missing_from_bucket = int((diff["_merge"] == "left_only").sum())
    extra_in_bucket = int((diff["_merge"] == "right_only").sum())
    changed_keys = int(
        ((diff["_merge"] == "both") & (diff["delta"] != 0)).sum()
    )
    absolute_dose_delta = int(different["delta"].abs().sum())
    net_dose_delta = int(diff["delta"].sum())

    metrics = {
        "missing_from_bucket": missing_from_bucket,
        "extra_in_bucket": extra_in_bucket,
        "changed_keys": changed_keys,
        "different_keys": len(different),
        "absolute_dose_delta": absolute_dose_delta,
        "net_dose_delta": net_dose_delta,
    }

    return different, metrics


def is_exact_match(
    metrics: dict,
    ms_df: pd.DataFrame,
    cube_df: pd.DataFrame,
) -> bool:
    """EXACT_MATCH somente quando zero diferenças E doses totais idênticas."""
    return (
        metrics["missing_from_bucket"] == 0
        and metrics["extra_in_bucket"] == 0
        and metrics["changed_keys"] == 0
        and int(ms_df["ms_doses"].sum()) == int(cube_df["cube_doses"].sum())
    )


# ─────────────────────────────────────────────────────────────────────────────
# Persistência de artefatos
# ─────────────────────────────────────────────────────────────────────────────

def save_unpartitionable(
    audit_dir: Path,
    year: int,
    month: int,
    records: list[dict],
) -> Path | None:
    """Salva registros não particionáveis em JSONL (campos mínimos)."""
    if not records:
        return None
    path = audit_dir / f"{year}_{month:02d}_unpartitionable.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def save_differences(
    audit_dir: Path,
    year: int,
    month: int,
    different: pd.DataFrame,
) -> Path | None:
    """Salva parquet de diferenças somente se existirem."""
    diff_dir = audit_dir / "differences"
    diff_path = diff_dir / f"{year}_{month:02d}_differences.parquet"

    if len(different):
        diff_dir.mkdir(parents=True, exist_ok=True)
        different.to_parquet(diff_path, index=False, compression="zstd")
        return diff_path
    elif diff_path.exists():
        diff_path.unlink()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(
        description=(
            "Auditoria independente: MS oficial × cubo SI-PNI no Cloudflare R2 (sus-dados).\n"
            "Credenciais: SUS_DATA_R2_ACCESS_KEY_ID, SUS_DATA_R2_SECRET_ACCESS_KEY, "
            "SUS_DATA_R2_ENDPOINT (via .env ou variáveis de ambiente)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--year", type=int, required=True, help="Ano (ex: 2023)")
    parser.add_argument("--month", type=int, required=True, help="Mês (ex: 10)")
    parser.add_argument(
        "--zip-path",
        type=Path,
        default=None,
        help=(
            "Caminho para o ZIP oficial do MS. "
            "Padrão: tmp/pni_YYYY_MM/<primeiro .zip encontrado>"
        ),
    )
    parser.add_argument(
        "--resource-id",
        default=None,
        help="resource_id OpenDataSUS do ZIP. Se omitido, será registrado como null.",
    )
    parser.add_argument(
        "--expected-sha256",
        default=None,
        help=(
            "SHA-256 esperado do ZIP. Se fornecido e divergir, a auditoria "
            "para imediatamente sem processar."
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=250_000,
        help="Tamanho de cada chunk CSV (padrão: 250000)",
    )

    args = parser.parse_args()

    year: int = args.year
    month: int = args.month

    # ── Diretório de saída ────────────────────────────────────────────────────
    audit_dir = AUDIT_CROSSCHECK
    audit_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== AUDITORIA MS × R2 (sus-dados) ===")
    print(f"Período: {year}-{month:02d}")
    print()

    started = time.perf_counter()

    # ── Localização do ZIP ────────────────────────────────────────────────────
    zip_path: Path | None = args.zip_path

    if zip_path is None:
        default_dir = PROJECT_ROOT / f"tmp/pni_{year}_{month:02d}"
        zips = list(default_dir.glob("*.zip")) if default_dir.is_dir() else []
        if len(zips) == 1:
            zip_path = zips[0]
        elif len(zips) > 1:
            raise RuntimeError(
                f"Múltiplos ZIPs em {default_dir}: {zips}. "
                "Use --zip-path para especificar."
            )
        else:
            raise FileNotFoundError(
                f"ZIP não encontrado em {default_dir}. "
                "Use --zip-path para especificar o caminho."
            )

    print(f"ZIP: {zip_path}")

    # ── SHA-256 ───────────────────────────────────────────────────────────────
    print("Calculando SHA-256...")
    observed_sha256 = sha256_file(zip_path)
    print(f"SHA-256 observado:  {observed_sha256}")

    if args.expected_sha256:
        expected = args.expected_sha256.strip().lower()
        if observed_sha256 != expected:
            print()
            print("❌ ATENÇÃO: SHA-256 DIVERGE DA FONTE DE REFERÊNCIA!")
            print(f"  Esperado:  {expected}")
            print(f"  Observado: {observed_sha256}")
            print()
            print("A fonte oficial pode ter sido alterada. Interrompendo auditoria.")
            raise SystemExit(1)
        print("✅ SHA-256 verificado.")
    else:
        warnings.warn(
            f"SHA-256 não foi verificado (--expected-sha256 não fornecido). "
            f"SHA-256 observado: {observed_sha256}",
            stacklevel=1,
        )
    print()

    # ── resource_id ───────────────────────────────────────────────────────────
    resource_id = args.resource_id
    if resource_id is None:
        warnings.warn(
            "resource_id não fornecido (--resource-id). "
            "Será registrado como null no summary.",
            stacklevel=1,
        )

    # ── Agregação independente do MS ──────────────────────────────────────────
    print("Lendo CSV oficial do MS...")
    (
        ms_df,
        raw_rows,
        partitionable_rows,
        unpartitionable_rows,
        unpartitionable_sample,
    ) = read_ms_zip(zip_path, year, month, chunk_size=args.chunk_size)

    print(f"MS raw:             {raw_rows:,}")
    print(f"MS particionáveis:  {partitionable_rows:,}")
    print(f"MS não partic.:     {unpartitionable_rows:,}")
    print(f"MS chaves:          {len(ms_df):,}")
    print(f"MS doses:           {int(ms_df['ms_doses'].sum()):,}")
    print()

    # ── Quarentena dos não particionáveis ─────────────────────────────────────
    unpart_path = save_unpartitionable(audit_dir, year, month, unpartitionable_sample)
    if unpart_path:
        print(f"Registros não particionáveis: {unpartitionable_rows} → {unpart_path}")
        print()

    # ── Leitura do cubo no R2 ─────────────────────────────────────────────────
    print("Conectando ao R2 (sus-dados)...")
    s3 = make_audit_filesystem()
    print(f"Lendo cubo R2: {settings.sus_data_r2_bucket}/{settings.sus_data_r2_cube_prefix}")
    print()
    cube_df = read_r2_cube(s3, year, month)
    print()
    print(f"R2 chaves:          {len(cube_df):,}")
    print(f"R2 doses:           {int(cube_df['cube_doses'].sum()):,}")
    print()

    # ── Comparação ────────────────────────────────────────────────────────────
    print("Executando comparação MS × R2...")
    different, metrics = compare_ms_vs_cube(ms_df, cube_df)
    exact = is_exact_match(metrics, ms_df, cube_df)
    status = "EXACT_MATCH" if exact else "MISMATCH"
    print()

    # ── Persistência ──────────────────────────────────────────────────────────
    diff_path = save_differences(audit_dir, year, month, different)

    elapsed = round(time.perf_counter() - started, 3)

    summary = {
        "audit_version": 2,
        "period": f"{year}-{month:02d}",

        "official_source": {
            "provider": "Ministério da Saúde / OpenDataSUS",
            "resource_id": resource_id,
            "filename": zip_path.name,
            "sha256": observed_sha256,
            "encoding": CSV_ENCODING,
        },

        "target": {
            "type": "cloudflare_r2",
            "bucket": settings.sus_data_r2_bucket,
            "prefix": settings.sus_data_r2_cube_prefix,
        },

        "ms": {
            "raw_rows": raw_rows,
            "partitionable_rows": partitionable_rows,
            "unpartitionable_rows": unpartitionable_rows,
            "cube_keys": len(ms_df),
            "partitionable_doses": int(ms_df["ms_doses"].sum()),
        },

        "r2_cube": {
            "cube_rows": len(cube_df),
            "doses": int(cube_df["cube_doses"].sum()),
        },

        "comparison": metrics,

        "status": status,
        "elapsed_seconds": elapsed,
    }

    summary_path = audit_dir / f"{year}_{month:02d}_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── Resultado ─────────────────────────────────────────────────────────────
    print("=== RESULTADO ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print()
    print("Summary salvo em:", summary_path)

    if diff_path:
        print("Diferenças salvas em:", diff_path)
    else:
        print("Nenhuma diferença encontrada.")

    if status == "MISMATCH":
        print()
        print("⚠️  MISMATCH detectado. Não adaptar transformação para 'fazer bater'.")
        print("   Investigar e relatar a divergência.")

    print()
    print("ZIP NÃO foi apagado automaticamente.")
    if status == "EXACT_MATCH":
        print(
            f"Pode remover manualmente {zip_path} "
            "após confirmar status=EXACT_MATCH e o summary."
        )


if __name__ == "__main__":
    main()
