from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pyarrow.parquet as pq


YEAR = 2023
MONTH = 10

ZIP_PATH = Path("tmp/pni_2023_10/vacinacao_out_2023_csv.zip")
CACHE_ROOT = Path("cache/pni_cube")
AUDIT_ROOT = Path("audit/ms_crosscheck")

RESOURCE_ID = "bb1c023c-e524-48ff-8471-f68f6cdf189e"

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

USECOLS = [
    "sg_uf_estabelecimento",
    "co_municipio_estabelecimento",
    "no_municipio_estabelecimento",
    "co_vacina",
    "tp_sexo_paciente",
    "nu_idade_paciente",
    "ds_tipo_dose",
]

KEYS = [
    "uf",
    "municipality_code",
    "municipality_name",
    "vaccine_code",
    "sex",
    "age_band",
    "dose",
]


def sha256_file(path: Path, chunk_size=8 * 1024 * 1024):
    h = hashlib.sha256()

    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)

    return h.hexdigest()


# Implementação propositalmente independente do build_cache.py.
def norm(s: pd.Series) -> pd.Series:
    return (
        s.astype("string")
        .str.strip()
        .fillna("IGNORADO")
    )


def age_band(s: pd.Series) -> pd.Series:
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


def cube_path(uf: str) -> Path:
    return (
        CACHE_ROOT
        / f"ano={YEAR}"
        / f"uf={uf}"
        / f"mes={MONTH:02d}"
        / "cube.parquet"
    )


def main():
    started = time.perf_counter()

    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)

    print("=== AUDITORIA MS × CUBO ===")
    print(f"Período: {YEAR}-{MONTH:02d}")
    print()

    # ---------------------------------------------------------
    # 1. Fingerprint da fonte
    # ---------------------------------------------------------

    print("Calculando SHA-256 da jamanta...")

    sha256 = sha256_file(ZIP_PATH)

    print("SHA-256:", sha256)
    print()

    # ---------------------------------------------------------
    # 2. Agregação independente do MS
    # ---------------------------------------------------------

    aggregates = []

    raw_rows = 0
    partitionable_rows = 0
    unpartitionable_rows = 0

    print("Lendo CSV oficial...")

    with ZipFile(ZIP_PATH) as z:
        csvs = [
            x for x in z.namelist()
            if x.lower().endswith(".csv")
        ]

        if len(csvs) != 1:
            raise RuntimeError(
                f"Esperava 1 CSV, encontrei: {csvs}"
            )

        with z.open(csvs[0]) as raw:
            reader = pd.read_csv(
                raw,
                sep=";",
                encoding="cp1252",
                usecols=USECOLS,
                dtype="string",
                chunksize=250_000,
                low_memory=False,
            )

            for n, pdf in enumerate(reader, 1):
                raw_rows += len(pdf)

                uf = (
                    pdf["sg_uf_estabelecimento"]
                    .astype("string")
                    .str.strip()
                    .str.upper()
                )

                valid = uf.isin(UFS)

                partitionable_rows += int(valid.sum())
                unpartitionable_rows += int((~valid).sum())

                pdf = pdf.loc[valid].copy()
                uf = uf.loc[valid]

                if pdf.empty:
                    continue

                x = pd.DataFrame({
                    "uf": uf,
                    "municipality_code":
                        norm(pdf["co_municipio_estabelecimento"]),
                    "municipality_name":
                        norm(pdf["no_municipio_estabelecimento"]),
                    "vaccine_code":
                        norm(pdf["co_vacina"]),
                    "sex":
                        norm(pdf["tp_sexo_paciente"]),
                    "age_band":
                        age_band(pdf["nu_idade_paciente"]),
                    "dose":
                        norm(pdf["ds_tipo_dose"]),
                })

                g = (
                    x.groupby(
                        KEYS,
                        dropna=False,
                        observed=True,
                    )
                    .size()
                    .reset_index(name="ms_doses")
                )

                aggregates.append(g)

                print(
                    f"\rchunk {n} | "
                    f"{raw_rows:,} linhas",
                    end="",
                    flush=True,
                )

    print()

    # Precisamos reagrupar porque a mesma chave pode
    # aparecer em vários chunks.
    ms = pd.concat(aggregates, ignore_index=True)

    ms = (
        ms.groupby(
            KEYS,
            dropna=False,
            observed=True,
            as_index=False,
        )["ms_doses"]
        .sum()
    )

    print(f"MS raw:             {raw_rows:,}")
    print(f"MS particionáveis:  {partitionable_rows:,}")
    print(f"MS não partic.:     {unpartitionable_rows:,}")
    print(f"MS chaves:          {len(ms):,}")
    print()

    # ---------------------------------------------------------
    # 3. Carrega os 27 cubos
    # ---------------------------------------------------------

    cubes = []

    for uf in sorted(UFS):
        path = cube_path(uf)

        if not path.exists():
            raise FileNotFoundError(path)

        table = pq.read_table(path)

        c = table.to_pandas()

        # year/month/uf podem ou não estar materializados
        # dependendo da versão do builder.
        c["uf"] = uf

        wanted = KEYS + ["doses"]

        missing = [
            col for col in wanted
            if col not in c.columns
        ]

        if missing:
            raise RuntimeError(
                f"{path}: colunas ausentes: {missing}"
            )

        c = c[wanted].copy()

        c = c.rename(
            columns={"doses": "cube_doses"}
        )

        cubes.append(c)

    cube = pd.concat(cubes, ignore_index=True)

    # Defesa extra contra duplicação acidental.
    cube = (
        cube.groupby(
            KEYS,
            dropna=False,
            observed=True,
            as_index=False,
        )["cube_doses"]
        .sum()
    )

    print(f"Cubo chaves:        {len(cube):,}")
    print(f"Cubo doses:         {cube['cube_doses'].sum():,}")
    print()

    # ---------------------------------------------------------
    # 4. Outer join — comparação célula por célula
    # ---------------------------------------------------------

    diff = ms.merge(
        cube,
        on=KEYS,
        how="outer",
        indicator=True,
    )

    diff["ms_doses"] = (
        diff["ms_doses"]
        .fillna(0)
        .astype("int64")
    )

    diff["cube_doses"] = (
        diff["cube_doses"]
        .fillna(0)
        .astype("int64")
    )

    diff["delta"] = (
        diff["cube_doses"]
        - diff["ms_doses"]
    )

    different = diff[
        (diff["delta"] != 0)
        | (diff["_merge"] != "both")
    ].copy()

    missing_from_cube = int(
        (diff["_merge"] == "left_only").sum()
    )

    extra_in_cube = int(
        (diff["_merge"] == "right_only").sum()
    )

    changed = int(
        (
            (diff["_merge"] == "both")
            & (diff["delta"] != 0)
        ).sum()
    )

    absolute_dose_delta = int(
        different["delta"].abs().sum()
    )

    net_delta = int(diff["delta"].sum())

    # ---------------------------------------------------------
    # 5. Persistência
    # ---------------------------------------------------------

    diff_path = (
        AUDIT_ROOT
        / f"{YEAR}_{MONTH:02d}_differences.parquet"
    )

    if len(different):
        different.to_parquet(
            diff_path,
            index=False,
            compression="zstd",
        )
    elif diff_path.exists():
        diff_path.unlink()

    exact = (
        missing_from_cube == 0
        and extra_in_cube == 0
        and changed == 0
        and int(ms["ms_doses"].sum())
            == int(cube["cube_doses"].sum())
    )

    summary = {
        "audit_version": 1,
        "period": f"{YEAR}-{MONTH:02d}",

        "official_source": {
            "provider": "Ministério da Saúde / OpenDataSUS",
            "resource_id": RESOURCE_ID,
            "filename": ZIP_PATH.name,
            "sha256": sha256,
            "encoding": "cp1252",
        },

        "ms": {
            "raw_rows": raw_rows,
            "partitionable_rows": partitionable_rows,
            "unpartitionable_rows": unpartitionable_rows,
            "cube_keys": len(ms),
            "partitionable_doses": int(
                ms["ms_doses"].sum()
            ),
        },

        "local_cube": {
            "cube_rows": len(cube),
            "doses": int(
                cube["cube_doses"].sum()
            ),
        },

        "comparison": {
            "missing_from_cube": missing_from_cube,
            "extra_in_cube": extra_in_cube,
            "changed_keys": changed,
            "different_keys": len(different),
            "absolute_dose_delta": absolute_dose_delta,
            "net_dose_delta": net_delta,
        },

        "status": (
            "EXACT_MATCH"
            if exact
            else "MISMATCH"
        ),

        "elapsed_seconds": round(
            time.perf_counter() - started,
            3,
        ),
    }

    summary_path = (
        AUDIT_ROOT
        / f"{YEAR}_{MONTH:02d}_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=== RESULTADO ===")
    print(json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
    ))

    print()
    print("Resumo salvo em:", summary_path)

    if len(different):
        print("Diferenças salvas em:", diff_path)

    # ---------------------------------------------------------
    # 6. NÃO apagamos automaticamente
    # ---------------------------------------------------------

    print()
    print("ZIP NÃO foi apagado.")
    print(
        "Apague somente depois de conferir "
        "status=EXACT_MATCH e o summary."
    )


if __name__ == "__main__":
    main()