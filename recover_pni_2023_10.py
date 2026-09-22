from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from sus_explorer.transform.pni import (
    UFS,
    age_band_series,
    normalize_string,
    partition_key,
)

from sus_explorer.build_cache import (
    cache_file,
    load_manifest,
    save_manifest,
    utc_now,
)


YEAR = 2023
MONTH = 10

ZIP_PATH = Path(
    "tmp/pni_2023_10/vacinacao_out_2023_csv.zip"
)

CACHE_ROOT = Path("cache/pni_cube")
MANIFEST_PATH = CACHE_ROOT / "manifest.json"

RESOURCE_ID = "bb1c023c-e524-48ff-8471-f68f6cdf189e"
SOURCE_FILE = "vacinacao_out_2023_csv.zip"

CHUNK_SIZE = 250_000

USECOLS = [
    "sg_uf_estabelecimento",
    "co_municipio_estabelecimento",
    "no_municipio_estabelecimento",
    "co_vacina",
    "tp_sexo_paciente",
    "nu_idade_paciente",
    "ds_tipo_dose",
]

GROUP_COLS = [
    "municipality_code",
    "municipality_name",
    "vaccine_code",
    "sex",
    "age_band",
    "dose",
]




def main() -> None:
    started = time.perf_counter()

    if not ZIP_PATH.exists():
        raise FileNotFoundError(ZIP_PATH)

    print("=== RECUPERAÇÃO SI-PNI OUTUBRO/2023 ===")
    print("ZIP:", ZIP_PATH)
    print(f"Tamanho ZIP: {ZIP_PATH.stat().st_size / 1024**3:.3f} GiB")
    print("Encoding: cp1252")
    print("Separador: ;")
    print("Partição: sg_uf_estabelecimento")
    print()

    # aggregate[UF][chave do cubo] = doses
    aggregates: dict[
        str,
        dict[tuple[str, ...], int]
    ] = {
        uf: defaultdict(int)
        for uf in UFS
    }

    raw_rows = 0
    valid_rows = 0
    invalid_uf_rows = 0
    chunk_number = 0

    with ZipFile(ZIP_PATH) as z:
        names = [
            name
            for name in z.namelist()
            if name.lower().endswith(".csv")
        ]

        if len(names) != 1:
            raise RuntimeError(
                f"Esperava exatamente 1 CSV no ZIP; encontrei {names}"
            )

        csv_name = names[0]
        print("CSV interno:", csv_name)
        print()

        with z.open(csv_name) as raw:
            reader = pd.read_csv(
                raw,
                sep=";",
                encoding="cp1252",
                usecols=USECOLS,
                dtype="string",
                chunksize=CHUNK_SIZE,
                low_memory=False,
            )

            for pdf in reader:
                chunk_number += 1
                raw_rows += len(pdf)

                uf_series = (
                    pdf["sg_uf_estabelecimento"]
                    .astype("string")
                    .str.strip()
                    .str.upper()
                )

                valid_mask = uf_series.isin(UFS)

                invalid = int((~valid_mask).sum())
                invalid_uf_rows += invalid

                pdf = pdf.loc[valid_mask].copy()
                uf_series = uf_series.loc[valid_mask]

                valid_rows += len(pdf)

                if pdf.empty:
                    continue

                frame = pd.DataFrame({
                    "uf": uf_series,
                    "municipality_code": normalize_string(
                        pdf["co_municipio_estabelecimento"]
                    ),
                    "municipality_name": normalize_string(
                        pdf["no_municipio_estabelecimento"]
                    ),
                    "vaccine_code": normalize_string(
                        pdf["co_vacina"]
                    ),
                    "sex": normalize_string(
                        pdf["tp_sexo_paciente"]
                    ),
                    "age_band": age_band_series(
                        pdf["nu_idade_paciente"]
                    ),
                    "dose": normalize_string(
                        pdf["ds_tipo_dose"]
                    ),
                })

                grouped = (
                    frame.groupby(
                        ["uf"] + GROUP_COLS,
                        dropna=False,
                        observed=True,
                    )
                    .size()
                    .reset_index(name="doses")
                )

                for row in grouped.itertuples(index=False):
                    uf = str(row.uf)

                    key = (
                        str(row.municipality_code),
                        str(row.municipality_name),
                        str(row.vaccine_code),
                        str(row.sex),
                        str(row.age_band),
                        str(row.dose),
                    )

                    aggregates[uf][key] += int(row.doses)

                elapsed = time.perf_counter() - started
                rate = raw_rows / elapsed if elapsed else 0

                print(
                    f"\rChunks: {chunk_number:,} | "
                    f"linhas: {raw_rows:,} | "
                    f"{rate:,.0f} linhas/s | "
                    f"UF inválida: {invalid_uf_rows:,}",
                    end="",
                    flush=True,
                )

    print("\n")
    print("Leitura concluída.")
    print(f"Linhas brutas:       {raw_rows:,}")
    print(f"Linhas válidas:      {valid_rows:,}")
    print(f"UF inválida/ausente: {invalid_uf_rows:,}")
    print()

    if raw_rows == 0:
        raise RuntimeError("CSV não contém registros")

    if valid_rows == 0:
        raise RuntimeError("Nenhuma linha com UF válida")

    manifest = load_manifest(MANIFEST_PATH)

    summaries = {}

    print("=== ESCREVENDO CUBOS ===")

    for uf in UFS:
        agg = aggregates[uf]

        if not agg:
            raise RuntimeError(
                f"{uf}: nenhuma linha encontrada no CSV oficial"
            )

        rows = []

        for key, doses in agg.items():
            rows.append({
                "municipality_code": key[0],
                "municipality_name": key[1],
                "vaccine_code": key[2],
                "sex": key[3],
                "age_band": key[4],
                "dose": key[5],
                "doses": doses,
            })

        result = pd.DataFrame(rows)

        result = result.sort_values(
            GROUP_COLS,
            kind="stable",
        ).reset_index(drop=True)

        output = cache_file(
            CACHE_ROOT,
            YEAR,
            MONTH,
            uf,
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        tmp = output.with_suffix(".parquet.tmp")

        table = pa.Table.from_pandas(
            result,
            preserve_index=False,
        )

        pq.write_table(
            table,
            tmp,
            compression="zstd",
        )

        # Validação antes do replace atômico
        metadata = pq.read_metadata(tmp)

        check = pq.read_table(
            tmp,
            columns=["doses"],
        )

        doses = int(
            check["doses"]
            .combine_chunks()
            .to_numpy()
            .sum()
        )

        expected_doses = sum(agg.values())

        if doses != expected_doses:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"{uf}: doses escritas={doses:,} "
                f"!= esperadas={expected_doses:,}"
            )

        os.replace(tmp, output)

        info = {
            "status": "cached",
            "year": YEAR,
            "month": MONTH,
            "uf": uf,
            "rows_cube": metadata.num_rows,
            "doses": doses,
            "bytes": output.stat().st_size,

            # Proveniência explícita
            "source": "opendatasus_csv_recovery",
            "source_resource_id": RESOURCE_ID,
            "source_file": SOURCE_FILE,
            "source_encoding": "cp1252",
            "source_partition_column": "sg_uf_estabelecimento",

            "updated_at": utc_now(),
        }

        manifest["partitions"][
            partition_key(YEAR, MONTH, uf)
        ] = info

        summaries[uf] = info

        print(
            f"{uf}: "
            f"{doses:,} doses | "
            f"{metadata.num_rows:,} linhas | "
            f"{output.stat().st_size / 1024**2:.2f} MiB"
        )

    # Só salva manifest depois que TODAS as 27 partições
    # foram produzidas e validadas.
    save_manifest(
        MANIFEST_PATH,
        manifest,
    )

    elapsed = time.perf_counter() - started

    total_doses = sum(
        x["doses"]
        for x in summaries.values()
    )

    total_cube_rows = sum(
        x["rows_cube"]
        for x in summaries.values()
    )

    total_bytes = sum(
        x["bytes"]
        for x in summaries.values()
    )

    print()
    print("=== RECUPERAÇÃO CONCLUÍDA ===")
    print(json.dumps(
        {
            "year": YEAR,
            "month": MONTH,
            "source": "OpenDataSUS CSV oficial",
            "resource_id": RESOURCE_ID,
            "raw_rows": raw_rows,
            "valid_rows": valid_rows,
            "invalid_uf_rows": invalid_uf_rows,
            "doses": total_doses,
            "cube_rows": total_cube_rows,
            "cube_size_mib": round(
                total_bytes / 1024**2,
                2,
            ),
            "elapsed_seconds": round(
                elapsed,
                3,
            ),
            "manifest": str(MANIFEST_PATH),
        },
        indent=2,
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
