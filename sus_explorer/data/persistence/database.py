"""PostgreSQL connection configuration without import-time side effects."""

from __future__ import annotations

import logging
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


logger = logging.getLogger(__name__)


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
        logger.error(
            "postgres_configuration_missing",
            extra={"event": "postgres_configuration_missing", "missing": missing},
        )
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
    except (psycopg.Error, ValueError):
        logger.exception(
            "postgres_connection_failed",
            extra={"event": "postgres_connection_failed"},
        )
        raise RuntimeError(
            "Could not connect to PostgreSQL; check database settings and availability"
        ) from None

    logger.info("postgres_connected", extra={"event": "postgres_connected"})
    return connection
