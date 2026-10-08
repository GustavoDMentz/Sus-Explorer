"""Optional HTTP adapter for SUS Explorer. Run: uvicorn web_api:app --reload."""
from functools import lru_cache
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sus_explorer.analytics.temporal_query import TemporalQueryError
from sus_explorer.service import SUSExplorer
from sus_explorer.llm import PlannerResponseError

app = FastAPI(title="SUS Explorer API", version="0.1.0")
origins = [origin.strip() for origin in os.getenv(
    "SUS_EXPLORER_WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST", "GET"], allow_headers=["Content-Type"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@lru_cache(maxsize=1)
def explorer() -> SUSExplorer:
    return SUSExplorer()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/ask")
def ask(payload: AskRequest):
    try:
        return explorer().ask(payload.question)
    except (TemporalQueryError, PlannerResponseError) as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from None
    except Exception:
        # Never return credentials, internal URLs, tracebacks or source microdata.
        raise HTTPException(status_code=503, detail={
            "code": "QUERY_UNAVAILABLE", "message": "Consulta indisponível. Tente novamente."
        }) from None
