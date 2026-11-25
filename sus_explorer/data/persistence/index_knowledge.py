"""Explicit operator-only indexing of curated local Markdown and text files."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from ...rag import KnowledgeStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Trusted directory containing public project documents")
    parser.add_argument("files", nargs="+", type=Path, help="Explicit public files to index")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("root must be an existing directory")
    store = KnowledgeStore()
    for path in args.files:
        try:
            status = store.index(path, root=root)
        except Exception as exc:
            print(f"ERRO ao indexar {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        print(f"{path}: {status}")


if __name__ == "__main__":
    main()
