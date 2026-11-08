"""Explicit batch migration of inventoried legacy partitions into PostgreSQL."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ...pni import PNIRemote
from .ingest_r2 import ingest_partition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--start-at", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    partitions = manifest.get("partitions")
    if not isinstance(partitions, list) or not 0 <= args.start_at < len(partitions) or not 1 <= args.limit <= len(partitions):
        parser.error("Manifesto, início ou limite inválido")
    pni = PNIRemote()
    for index in range(args.start_at, min(args.start_at + args.limit, len(partitions))):
        label = partitions[index]["partition"]
        match = re.fullmatch(r"ano=(20[0-9]{2})/mes=(0[1-9]|1[0-2])/uf=([A-Z]{2})", label)
        if match is None:
            raise ValueError("Partição inválida no manifesto")
        year, month, uf = match.groups()
        result = ingest_partition(int(year), int(month), uf, pni=pni, batch_size=args.batch_size)
        print(json.dumps({"index": index, "partition": label, "run_id": result["id"],
                          "status": result["status"], "rows": result["records_received"]}), flush=True)
        if result["status"] != "SUCCESS":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
