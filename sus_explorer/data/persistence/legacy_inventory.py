"""Read-only inventory of legacy SI-PNI R2 partitions for controlled migration."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.fs as fs

from ...pni import PNIRemote


def _children(filesystem, path: str, pattern: str) -> list[str]:
    items = filesystem.get_file_info(fs.FileSelector(path, recursive=False, allow_not_found=True))
    result = []
    for item in items:
        if item.type == fs.FileType.Directory:
            name = item.path.rstrip("/").rsplit("/", 1)[-1]
            if re.fullmatch(pattern, name):
                result.append(name)
    return sorted(set(result))


def inventory(pni: PNIRemote, *, with_counts: bool = False) -> dict:
    root = f"{pni.config.r2_bucket}/{pni.config.r2_prefix}/"
    partitions = []
    for year_dir in _children(pni.s3, root, r"ano=20[0-9]{2}"):
        for month_dir in _children(pni.s3, root + year_dir + "/", r"mes=(0[1-9]|1[0-2])"):
            for uf_dir in _children(pni.s3, root + year_dir + "/" + month_dir + "/", r"uf=[A-Z]{2}"):
                year, month, uf = int(year_dir[4:]), int(month_dir[4:]), uf_dir[3:]
                entry = {"partition": f"{year_dir}/{month_dir}/{uf_dir}"}
                if with_counts:
                    dataset = pni.dataset(year, month, uf)
                    entry["source_rows"] = dataset.count_rows()
                    entry["fragments"] = sum(1 for _ in dataset.get_fragments())
                partitions.append(entry)
    return {"source": root, "checked_at": datetime.now(timezone.utc).isoformat(),
            "partition_count": len(partitions), "partitions": partitions}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--counts", action="store_true", help="Read Parquet footers for every partition")
    args = parser.parse_args()
    result = inventory(PNIRemote(), with_counts=args.counts)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"partition_count": result["partition_count"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
