"""PostgreSQL connection configuration without import-time side effects."""

from __future__ import annotations

import functools
import ipaddress
import os
import re

import psycopg
from psycopg import sql
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


def _is_loopback_ip(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def allow_long_ingestion_statement(connection) -> None:
    """Raise statement_timeout for the current transaction only.

    Reconciliation counts scan a whole partition and can exceed the 30 s default that
    protects the interactive app; a timeout there would leave a finished load marked
    FAILED or RUNNING. Capped at one hour; applies to the open transaction only.
    """
    milliseconds = _integer_setting(
        "POSTGRES_INGEST_STATEMENT_TIMEOUT_MS", 300_000, minimum=1_000, maximum=3_600_000
    )
    connection.execute("SELECT set_config('statement_timeout', %s, true)", (str(milliseconds),))


def configured_schema() -> str:
    schema = os.getenv("POSTGRES_SCHEMA", "sus_explorer")
    if not _SCHEMA.fullmatch(schema):
        raise RuntimeError("Invalid PostgreSQL setting: POSTGRES_SCHEMA")
    return schema


# Least-privilege login profiles. Each maps to a login role that is a member of exactly one
# structural group role (see docs/database.md):
#   reader   -> sus_explorer_reader   (analytical queries, RAG search: read-only)
#   ingest   -> sus_explorer_runtime  (imports: writes raw records and runs)
#   history  -> sus_explorer_history  (opt-in query/result history: insert-only tables)
#   migrator -> sus_explorer_migrator (migrations, purge, RAG indexing: schema owner)
PROFILES = ("reader", "ingest", "history", "migrator")
_warned_fallback: set[str] = set()


def _credentials(profile: str | None) -> tuple[str | None, str | None, list[str]]:
    """User, password and the names of the variables that are missing."""
    if profile is None:
        names = ("POSTGRES_USER", "POSTGRES_PASSWORD")
    else:
        if profile not in PROFILES:
            raise RuntimeError("Unknown PostgreSQL profile")
        names = (f"POSTGRES_{profile.upper()}_USER", f"POSTGRES_{profile.upper()}_PASSWORD")
        if os.getenv(names[0]) and os.getenv(names[1]):
            return os.environ[names[0]], os.environ[names[1]], []
        if os.getenv("POSTGRES_REQUIRE_PROFILES") == "1":
            return None, None, [name for name in names if not os.getenv(name)]
        # Backward compatible: without profile credentials, the single legacy login is
        # used, which in the default compose setup is a superuser. Say so, once.
        if profile not in _warned_fallback:
            _warned_fallback.add(profile)
            event("postgres_profile_fallback", level="WARNING", profile=profile)
        names = ("POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [name for name in names if not os.getenv(name)]
    return os.getenv(names[0]), os.getenv(names[1]), missing


def connect(profile: str | None = None) -> psycopg.Connection:
    """Connect from environment variables without logging credentials or DSNs."""
    load_dotenv()
    user, password, missing_credentials = _credentials(profile)
    required = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB")
    missing = [name for name in required if not os.getenv(name)] + missing_credentials
    if missing:
        event("postgres_configuration_missing", level="ERROR", missing=missing)
        raise RuntimeError("Missing database settings: " + ", ".join(missing))

    schema = configured_schema()
    application_name = os.getenv("POSTGRES_APPLICATION_NAME", "sus-explorer")
    host = os.environ["POSTGRES_HOST"]
    local_host = host.startswith("/") or host == "localhost" or host.endswith(".localhost") or _is_loopback_ip(host)
    sslmode = os.getenv("POSTGRES_SSLMODE", "prefer" if local_host else "require")
    if not _APPLICATION_NAME.fullmatch(application_name):
        raise RuntimeError("Invalid PostgreSQL setting: POSTGRES_APPLICATION_NAME")
    if sslmode not in _SSLMODES:
        raise RuntimeError("Invalid PostgreSQL setting: POSTGRES_SSLMODE")
    if not local_host and sslmode in ("disable", "allow", "prefer"):
        raise RuntimeError("POSTGRES_SSLMODE must be require or stronger for a remote host")
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
            user=user,
            password=password,
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
    # pgvector may have been installed in a shared schema by an earlier
    # migration. Include only the extension's actual namespace, never an
    # untrusted schema name from application input.
    with connection.cursor() as cursor:
        cursor.execute("""SELECT n.nspname AS extension_schema FROM pg_extension e
            JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'""")
        extension = cursor.fetchone()
        if extension and extension["extension_schema"] != schema:
            cursor.execute(sql.SQL("SET search_path TO {}, {}, pg_catalog").format(
                sql.Identifier(schema), sql.Identifier(extension["extension_schema"])))
    connection.commit()
    return connection


# Ready-made factories for call sites that take a ``connect_db`` callable.
connect_reader = functools.partial(connect, "reader")
connect_ingest = functools.partial(connect, "ingest")
connect_history = functools.partial(connect, "history")
connect_migrator = functools.partial(connect, "migrator")
