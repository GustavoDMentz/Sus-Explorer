"""PostgreSQL connection configuration without import-time side effects."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from .operational_events import event


def connect() -> psycopg.Connection:
    """Connect from environment variables without logging credentials or DSNs."""
    load_dotenv()
    required = (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        event("postgres_configuration_missing", level="ERROR", missing=missing)
        raise RuntimeError("Missing database settings: " + ", ".join(missing))

    try:
        connection = psycopg.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")),
            row_factory=dict_row,
        )
    except (psycopg.Error, ValueError) as exc:
        event(
            "postgres_connection_failed",
            level="ERROR",
            error_type=type(exc).__name__,
        )
        raise RuntimeError(
            "Could not connect to PostgreSQL; check database settings and availability"
        ) from None

    event("postgres_connected")
    return connection
