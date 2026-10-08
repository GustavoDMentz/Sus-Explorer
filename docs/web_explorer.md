# SUS Explorer Web v1

The web interface is an optional client of the existing deterministic Python engine.

## Local development

Python API (from repository root):

```bash
pip install -r requirements-web.txt
uvicorn web_api:app --reload --host 127.0.0.1 --port 8000
```

Frontend (second terminal):

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000. Gemini and R2 credentials are configured on the Python side as described in the root README.

## Architecture

- `POST /api/ask`: accepts `{"question":"..."}`, returns the existing `SUSExplorer.ask` response. Validation errors and controlled temporal errors return HTTP 422. Unexpected errors return a generic HTTP 503 without backend details.
- `GET /api/health`: liveness only; does not assert that Gemini or R2 is reachable.
- The client does not implement calculations. It renders backend values, including `null`, and never changes query semantics when switching views.
- Scientific mode displays monthly observations and selected differences; dashboard mode displays KPI cards, charts and an interpretation.
- Both modes share the same result and a collapsible provenance panel. Preference is stored locally in the browser.
- The initial chart is **synthetic demonstration data**, visibly labeled as such. It is replaced by live results only when monthly rows exist. Count/group/latency results may not have monthly rows and require dedicated visualizations in a subsequent iteration.
- Browser charting necessarily converts safe numeric values to JavaScript numbers. Exact decimal strings remain unchanged in the scientific table. Unsafe large integers are omitted from charts rather than rounded silently.
- CORS is restricted to local frontend origins by default; configure `SUS_EXPLORER_WEB_ORIGINS` for another origin. No authentication or rate limiting is included; do **not** expose the API to the public internet without those controls.
- This version is a local development prototype, not a public production deployment.

## Checks

```bash
pip install -r requirements-web.txt pytest httpx
pytest tests/unit/test_web_api.py
cd frontend && npm install && npm run build
```

No migrations, Parquet/R2 execution logic, operational logging, or historical scientific artifacts are changed.
