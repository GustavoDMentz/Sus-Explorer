"""Database connection configuration, independent of the current Parquet reader."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


def connect() -> psycopg.Connection:
    """Connect using environment variables; never print credentials in errors."""
    load_dotenv()
    required = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing database settings: " + ", ".join(missing))
    try:
        return psycopg.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            row_factory=dict_row,
        )
    except psycopg.Error:
        raise RuntimeError("Could not connect to PostgreSQL; check database settings and availability") from None
