#!/usr/bin/env bash
# Regenerates requirements-lock.txt (direct + transitive pins with SHA-256 hashes).
# Run with Python 3.12 on Linux, the same target as CI.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install --quiet pip-tools
python -m piptools compile --quiet --generate-hashes --strip-extras --no-emit-index-url \
  --constraint constraints.txt --output-file requirements-lock.txt requirements-dev.txt
echo "requirements-lock.txt atualizado: revise o diff e rode a suíte de testes."
