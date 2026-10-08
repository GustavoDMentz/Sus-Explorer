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

## Invalid planner output

The Gemini planner uses native JSON Schema with local QueryPlan validation.
Output is bounded to 8,192 tokens and accepted response text to 16,384 UTF-8
bytes. Truncated/blocked candidates, malformed JSON, invalid plans and SDK
integer-conversion failures produce HTTP 422 with code
`INVALID_PLANNER_RESPONSE`. The source query is not executed in this case.
The response never includes generated text or SDK exception details. Python's
integer conversion guard remains enabled. This bounds and handles invalid
output; it cannot guarantee a valid plan from an external model.

Regression validation (2026-10-08): `python -m pytest tests -q -rs`:
**249 passed, 7 skipped, 0 failed**. PostgreSQL tests require a disposable
configured database and were skipped locally. The SDK's parsing failure with
a 65,410-digit integer is reproduced offline, including the HTTP error path.
No live Gemini/R2 query was available in the validation environment.

### Planner recovery

The wire schema is now inlined (no `$ref`/`$defs`), without annotations/defaults,
with bounded monthly interval integers and `const` represented as `enum`.
The internal QueryPlan and query semantics are unchanged. Gemini 3 planners
request LOW thinking; the 8,192-token ceiling leaves more room for thinking
and the actual JSON than the initial 2,048-token limit.

A failed structured-output attempt is retried once in JSON mode without an
API-enforced schema. This avoids the SDK's automatic schema JSON parsing path.
The fallback receives the original question and public schema, never source
data or the malformed response. Both paths must pass the same strict local
QueryPlan validation before execution; invalid plans are never repaired by
coercion or executed. Network/API errors are not retried by this mechanism.

Updated offline validation: **253 passed, 7 skipped, 0 failed**. Recovery tests
cover the real SDK parser's 65,410-digit failure, truncated output and invalid
orders, followed by a valid plan and actual TemporalAnalytics execution on
synthetic monthly aggregates. The expected differences are exactly
`[null, 10, 10, 10, 10, 10]`, classified DERIVED. A live Gemini/R2 run remains
necessary to confirm provider behavior with the deployment's model/settings.
