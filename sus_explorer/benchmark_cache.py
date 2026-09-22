
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pyarrow.dataset as pds


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--year",
        type=int,
        default=2025,
    )

    parser.add_argument(
        "--uf",
        default="RS",
    )

    parser.add_argument(
        "--municipality",
        default="VACARIA",
    )

    parser.add_argument(
        "--cache-root",
        default="cache/pni_cube",
    )

    args = parser.parse_args()

    root = (
        Path(args.cache_root)
        / f"ano={args.year}"
        / f"uf={args.uf.upper()}"
    )

    started = time.perf_counter()

    ds = pds.dataset(
        root,
        format="parquet",
        partitioning="hive",
    )

    table = ds.to_table(
        columns=[
            "vaccine_code",
            "doses",
        ],
        filter=(
            pds.field("municipality_name")
            == args.municipality.upper()
        ),
    )

    pdf = table.to_pandas()

    total = int(
        pdf["doses"].sum()
    )

    ranking = (
        pdf.groupby(
            "vaccine_code",
            dropna=False,
        )["doses"]
        .sum()
        .sort_values(
            ascending=False
        )
        .head(10)
    )

    result = {
        "municipality": args.municipality.upper(),
        "year": args.year,
        "uf": args.uf.upper(),
        "total_doses": total,
        "top_vaccine_codes": {
            str(code): int(count)
            for code, count
            in ranking.items()
        },
        "elapsed_seconds": round(
            time.perf_counter()
            - started,
            4,
        ),
    }

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()