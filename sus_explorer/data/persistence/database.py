"""PostgreSQL connection configuration without import-time side effects."""

from __future__ import annotations

import os
import re

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from .operational_events import event


_SCHEMA = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_APPLICATION_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SSLMODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def _integer_setting(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid PostgreSQL setting: {name}") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"PostgreSQL setting outside allowed range: {name}")
    return value


def configured_schema() -> str:
    schema = os.getenv("POSTGRES_SCHEMA", "sus_explorer")
    if not _SCHEMA.fullmatch(schema):
        raise RuntimeError("Invalid PostgreSQL setting: POSTGRES_SCHEMA")
    return schema


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

    schema = configured_schema()
    application_name = os.getenv("POSTGRES_APPLICATION_NAME", "sus-explorer")
    sslmode = os.getenv("POSTGRES_SSLMODE", "prefer")
    if not _APPLICATION_NAME.fullmatch(application_name):
        raise RuntimeError("Invalid PostgreSQL setting: POSTGRES_APPLICATION_NAME")
    if sslmode not in _SSLMODES:
        raise RuntimeError("Invalid PostgreSQL setting: POSTGRES_SSLMODE")
    connect_timeout = _integer_setting(
        "POSTGRES_CONNECT_TIMEOUT", 10, minimum=1, maximum=60
    )
    statement_timeout = _integer_setting(
        "POSTGRES_STATEMENT_TIMEOUT_MS", 30_000, minimum=100, maximum=300_000
    )
    lock_timeout = _integer_setting(
        "POSTGRES_LOCK_TIMEOUT_MS", 5_000, minimum=100, maximum=60_000
    )
    idle_timeout = _integer_setting(
        "POSTGRES_IDLE_TRANSACTION_TIMEOUT_MS",
        30_000,
        minimum=1_000,
        maximum=300_000,
    )
    options = (
        f"-c statement_timeout={statement_timeout} "
        f"-c lock_timeout={lock_timeout} "
        f"-c idle_in_transaction_session_timeout={idle_timeout} "
        f"-c search_path={schema},pg_catalog"
    )

    try:
        connection = psycopg.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=connect_timeout,
            application_name=application_name,
            sslmode=sslmode,
            options=options,
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
