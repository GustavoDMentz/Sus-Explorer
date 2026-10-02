
from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import settings
from .data.cache.manifest import (
    cache_file,
    load_manifest,
    save_manifest,
    utc_now,
    validate_existing_cache,
)
from .data.remote.r2 import (
    make_filesystem,
    open_partition,
    partition_path,
)
from .paths import CACHE_ROOT
from .operational_logging import JsonlRunLogger
from .transform.pni import (
    UFS,
    CUBE_ALIASES,
    age_band_series,
    normalize_string,
    parse_ufs,
    partition_key,
    resolve_col,
)

# Nome interno mantido para compatibilidade com o resto do módulo.
ALIASES = CUBE_ALIASES

# Backward compat aliases.
make_s3 = make_filesystem
source_path = partition_path



def build_partition(
    s3,
    year: int,
    month: int,
    uf: str,
    output_file: Path,
    batch_size: int,
) -> dict:
    started = time.perf_counter()

    try:
        ds = open_partition(s3, year, month, uf)
    except FileNotFoundError:
        return {
            "status": "missing",
            "year": year,
            "month": month,
            "uf": uf,
            "elapsed_seconds": round(
                time.perf_counter() - started,
                3,
            ),
        }

    physical = {
        logical: resolve_col(ds, logical)
        for logical in ALIASES
    }

    missing_cols = [
        logical
        for logical, column in physical.items()
        if column is None
    ]

    if missing_cols:
        raise KeyError(
            f"{year}/{uf}/{month:02d}: "
            "colunas necessárias ausentes: "
            + ", ".join(missing_cols)
        )

    columns = list(dict.fromkeys(physical.values()))

    aggregate: dict[tuple[str, ...], int] = {}
    raw_rows = 0
    fragments = sum(1 for _ in ds.get_fragments())

    scanner = ds.scanner(
        columns=columns,
        batch_size=batch_size,
        use_threads=True,
    )

    for batch in scanner.to_batches():
        raw_rows += batch.num_rows

        pdf = pa.Table.from_batches([batch]).to_pandas()

        frame = pd.DataFrame({
            "municipality_code": normalize_string(
                pdf[physical["municipality_code"]]
            ),
            "municipality_name": normalize_string(
                pdf[physical["municipality_name"]]
            ),
            "vaccine_code": normalize_string(
                pdf[physical["vaccine_code"]]
            ),
            "sex": normalize_string(
                pdf[physical["sex"]]
            ),
            "age_band": age_band_series(
                pdf[physical["age"]]
            ),
            "dose": normalize_string(
                pdf[physical["dose"]]
            ),
        })

        grouped = (
            frame.groupby(
                [
                    "municipality_code",
                    "municipality_name",
                    "vaccine_code",
                    "sex",
                    "age_band",
                    "dose",
                ],
                dropna=False,
                observed=True,
            )
            .size()
            .reset_index(name="doses")
        )

        for row in grouped.itertuples(index=False):
            key = (
                str(row.municipality_code),
                str(row.municipality_name),
                str(row.vaccine_code),
                str(row.sex),
                str(row.age_band),
                str(row.dose),
            )
            aggregate[key] = (
                aggregate.get(key, 0)
                + int(row.doses)
            )

    rows = [
        {
            "year": year,
            "month": month,
            "uf": uf,
            "municipality_code": key[0],
            "municipality_name": key[1],
            "vaccine_code": key[2],
            "sex": key[3],
            "age_band": key[4],
            "dose": key[5],
            "doses": count,
        }
        for key, count in aggregate.items()
    ]

    out_df = pd.DataFrame(rows)

    if not out_df.empty:
        out_df = out_df.sort_values(
            [
                "municipality_code",
                "vaccine_code",
                "sex",
                "age_band",
                "dose",
            ],
            kind="stable",
        )

    cube_doses = int(out_df["doses"].sum()) if len(out_df) else 0

    # Invariante fundamental: o cubo deve representar todas as linhas
    # brutas da partição, exatamente uma vez.
    if cube_doses != raw_rows:
        raise RuntimeError(
            f"Falha de validação em {year}/{uf}/{month:02d}: "
            f"SUM(doses)={cube_doses:,} != raw_rows={raw_rows:,}"
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)

    tmp = output_file.with_name(
        output_file.name + ".tmp"
    )

    table = pa.Table.from_pandas(
        out_df,
        preserve_index=False,
    )

    pq.write_table(
        table,
        tmp,
        compression="zstd",
        compression_level=6,
        use_dictionary=True,
        write_statistics=True,
    )

    # Valida o arquivo gravado antes de torná-lo oficial.
    written = pq.read_table(tmp, columns=["doses"])
    written_doses = int(
        written["doses"]
        .combine_chunks()
        .to_numpy()
        .sum()
    )

    if written_doses != raw_rows:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Falha pós-gravação em {year}/{uf}/{month:02d}: "
            f"SUM(doses)={written_doses:,} != raw_rows={raw_rows:,}"
        )

    os.replace(tmp, output_file)

    return {
        "status": "built",
        "year": year,
        "month": month,
        "uf": uf,
        "raw_rows": raw_rows,
        "rows_cube": len(out_df),
        "doses": cube_doses,
        "fragments": fragments,
        "bytes": output_file.stat().st_size,
        "reduction_ratio": (
            round(raw_rows / len(out_df), 2)
            if len(out_df)
            else None
        ),
        "elapsed_seconds": round(
            time.perf_counter() - started,
            3,
        ),
    }


def build_with_retry(
    s3,
    year: int,
    month: int,
    uf: str,
    output_file: Path,
    batch_size: int,
    retries: int,
    logger: JsonlRunLogger | None = None,
) -> dict:
    last_exc = None

    for attempt in range(1, retries + 2):
        try:
            result = build_partition(
                s3=s3,
                year=year,
                month=month,
                uf=uf,
                output_file=output_file,
                batch_size=batch_size,
            )
            result["attempts"] = attempt
            return result
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            last_exc = exc

            if attempt > retries:
                break

            wait = min(2 ** (attempt - 1), 30)
            if logger is not None:
                logger.exception(
                    "partition_retry",
                    exc,
                    year=year,
                    month=month,
                    uf=uf,
                    attempt=attempt,
                    retry_in_seconds=wait,
                )
            print(
                f"    erro: {exc} | retry em {wait}s "
                f"({attempt}/{retries})",
                flush=True,
            )
            time.sleep(wait)

    assert last_exc is not None
    raise last_exc




def _run(logger: JsonlRunLogger) -> None:
    current_year = datetime.now().year

    parser = argparse.ArgumentParser(
        description=(
            "Constrói, valida e retoma o cache nacional "
            "agregado do SI-PNI."
        )
    )

    parser.add_argument(
        "--start-year",
        type=int,
        default=2020,
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=current_year,
    )
    parser.add_argument(
        "--ufs",
        help="Ex.: RS,SC,PR. Omitido = Brasil inteiro.",
    )
    parser.add_argument(
        "--cache-root",
        default=str(CACHE_ROOT),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100_000,
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Tenta novamente partições marcadas como failed.",
    )

    args = parser.parse_args()

    if args.start_year > args.end_year:
        parser.error("--start-year não pode ser maior que --end-year")

    ufs = parse_ufs(args.ufs)
    cache_root = Path(args.cache_root)
    logger.event(
        "run_started",
        start_year=args.start_year,
        end_year=args.end_year,
        ufs=ufs,
        batch_size=args.batch_size,
        retries=args.retries,
        overwrite=args.overwrite,
        retry_failed=args.retry_failed,
    )
    manifest_path = cache_root / "manifest.json"
    manifest = load_manifest(manifest_path)
    s3 = make_s3()

    run_started = time.perf_counter()

    counters = {
        "built": 0,
        "cached": 0,
        "missing": 0,
        "failed": 0,
    }

    print(
        f"Cache nacional SI-PNI: "
        f"{args.start_year}-{args.end_year} | "
        f"{len(ufs)} UF(s)",
        flush=True,
    )

    try:
        for year in range(
            args.start_year,
            args.end_year + 1,
        ):
            for uf in ufs:
                for month in range(1, 13):
                    key = partition_key(
                        year,
                        month,
                        uf,
                    )
                    output = cache_file(
                        cache_root,
                        year,
                        month,
                        uf,
                    )
                    old = manifest["partitions"].get(key)

                    if output.exists() and not args.overwrite:
                        try:
                            existing = validate_existing_cache(
                                output
                            )

                            entry = {
                                "status": "cached",
                                "year": year,
                                "month": month,
                                "uf": uf,
                                **existing,
                                "updated_at": utc_now(),
                            }

                            manifest["partitions"][key] = entry
                            counters["cached"] += 1
                            save_manifest(
                                manifest_path,
                                manifest,
                            )
                            logger.event(
                                "partition_cached",
                                year=year,
                                month=month,
                                uf=uf,
                                rows_cube=existing["rows_cube"],
                                doses=existing["doses"],
                                bytes=existing["bytes"],
                            )

                            print(
                                f"[CACHE] {key} | "
                                f"{existing['rows_cube']:,} linhas | "
                                f"{existing['bytes']/1024/1024:.2f} MiB",
                                flush=True,
                            )
                            continue
                        except Exception as exc:
                            logger.exception(
                                "cached_partition_invalid",
                                exc,
                                year=year,
                                month=month,
                                uf=uf,
                            )
                            print(
                                f"[CACHE INVÁLIDO] {key}: {exc}",
                                flush=True,
                            )
                            output.unlink(missing_ok=True)

                    if (
                        old
                        and old.get("status") == "failed"
                        and not args.retry_failed
                        and not args.overwrite
                    ):
                        counters["failed"] += 1
                        logger.event(
                            "partition_skipped_failed",
                            level="WARNING",
                            year=year,
                            month=month,
                            uf=uf,
                        )
                        print(
                            f"[SKIP FAILED] {key} "
                            "(use --retry-failed)",
                            flush=True,
                        )
                        continue

                    print(
                        f"[BUILD] {key}",
                        flush=True,
                    )
                    logger.event(
                        "partition_started",
                        year=year,
                        month=month,
                        uf=uf,
                    )

                    try:
                        result = build_with_retry(
                            s3=s3,
                            year=year,
                            month=month,
                            uf=uf,
                            output_file=output,
                            batch_size=args.batch_size,
                            retries=args.retries,
                            logger=logger,
                        )

                        result["updated_at"] = utc_now()
                        manifest["partitions"][key] = result
                        counters[result["status"]] += 1
                        logger.event(
                            "partition_finished",
                            **result,
                        )

                        if result["status"] == "built":
                            print(
                                "    "
                                f"raw={result['raw_rows']:,} | "
                                f"cube={result['rows_cube']:,} | "
                                f"{result['bytes']/1024/1024:.2f} MiB | "
                                f"{result['elapsed_seconds']:.2f}s",
                                flush=True,
                            )
                        else:
                            print(
                                f"    {result['status']}",
                                flush=True,
                            )

                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        counters["failed"] += 1
                        logger.exception(
                            "partition_failed",
                            exc,
                            year=year,
                            month=month,
                            uf=uf,
                        )

                        manifest["partitions"][key] = {
                            "status": "failed",
                            "year": year,
                            "month": month,
                            "uf": uf,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                            "updated_at": utc_now(),
                        }

                        print(
                            f"    FAILED: {type(exc).__name__}: {exc}",
                            flush=True,
                        )

                    finally:
                        save_manifest(
                            manifest_path,
                            manifest,
                        )

    except KeyboardInterrupt:
        print(
            "\nInterrompido. Manifest salvo; "
            "a próxima execução retoma do cache existente.",
            flush=True,
        )
        save_manifest(
            manifest_path,
            manifest,
        )

    files = list(
        cache_root.rglob("cube.parquet")
    )

    total_bytes = sum(
        path.stat().st_size
        for path in files
    )

    # Auditoria final usa o manifest, sem reler milhões de linhas.
    completed = [
        entry
        for entry in manifest["partitions"].values()
        if entry.get("status") in {"built", "cached"}
    ]

    total_doses = sum(
        int(entry.get("doses", 0))
        for entry in completed
    )

    total_cube_rows = sum(
        int(entry.get("rows_cube", 0))
        for entry in completed
    )

    summary = {
        "range": [
            args.start_year,
            args.end_year,
        ],
        "ufs": ufs,
        "run": counters,
        "cache_files": len(files),
        "cached_partitions": len(completed),
        "represented_doses_records": total_doses,
        "cube_rows": total_cube_rows,
        "size_bytes": total_bytes,
        "size_mib": round(
            total_bytes / 1024 / 1024,
            2,
        ),
        "size_gib": round(
            total_bytes / 1024 / 1024 / 1024,
            3,
        ),
        "elapsed_seconds": round(
            time.perf_counter() - run_started,
            3,
        ),
        "manifest": str(manifest_path),
    }

    print("\n=== RESUMO NACIONAL ===")
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )
    logger.event("run_finished", **summary)


def main() -> None:
    logger = JsonlRunLogger(
        "build_cache",
        secrets=(
            settings.r2_access_key,
            settings.r2_secret_key,
        ),
    )
    try:
        _run(logger)
    except KeyboardInterrupt:
        logger.event("run_interrupted", level="WARNING")
        raise
    except Exception as exc:
        logger.exception("run_failed", exc)
        raise


if __name__ == "__main__":
    main()
