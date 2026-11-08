# OpenDataSUS CKAN discovery — PostgreSQL branch

This is **phase 1: discovery only**, intentionally isolated from the ingestion path.

The new module `sus_explorer.data.persistence.ckan_discovery` queries the configured CKAN catalog over HTTPS, lists dataset resources, and compares resource metadata with a saved JSON manifest. It does **not** download resource URLs, import data, modify PostgreSQL, schedule jobs, or promote a new version.

Example (replace the dataset slug with the verified official identifier):

```bash
python -m sus_explorer.data.persistence.ckan_discovery \
  --dataset OFFICIAL_DATASET_SLUG \
  --manifest audit/opendatasus-pni.json
```

This prints differences without changing files. After verifying the catalog response, append `--write` to save the manifest. The endpoint defaults to `https://dadosabertos.saude.gov.br/api/3/action`; confirm that the live portal exposes the expected CKAN API before enabling any automation. `OPENDATASUS_CKAN_BASE` can override the endpoint.

**Important:** catalog timestamps and hashes are hints, not proof of source content identity. The next phase must validate actual ZIP SHA-256, restrict download destinations to trusted HTTPS hosts, enforce file size/time limits, derive year/month from verified official metadata, stage downloads, call the existing `ingest_csv` only after validation, and preserve the previous successful partition if a new ingestion fails. Do not silently treat missing or removed resources as zero. Implement locking, retries/backoff, audit events, scheduler, retention and integration tests before unattended operation.

This branch derives from `review/postgres-ollama-migration`, not `master`.
