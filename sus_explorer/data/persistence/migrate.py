"""Apply immutable numbered SQL migrations transactionally and in order."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .database import connect


logger = logging.getLogger(__name__)
MIGRATIONS = Path(__file__).parent / "migrations"


def migrate(connection, directory: Path = MIGRATIONS) -> list[str]:
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("No SQL migrations found")
    if len({path.name[:3] for path in files}) != len(files):
        raise RuntimeError("Duplicate migration version")

    applied: list[str] = []
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(91627134)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    sha256 text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
                )
            """)
            cursor.execute("SELECT version, sha256 FROM schema_migrations")
            previous = {row["version"]: row["sha256"] for row in cursor.fetchall()}
            names = {path.name for path in files}
            if unknown := set(previous) - names:
                raise RuntimeError(
                    "Applied migrations missing from source: "
                    + ", ".join(sorted(unknown))
                )

            pending_seen = False
            for path in files:
                sql = path.read_text(encoding="utf-8")
                digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                if path.name in previous:
                    if previous[path.name] != digest:
                        raise RuntimeError(
                            f"Migration changed after application: {path.name}"
                        )
                    if pending_seen:
                        raise RuntimeError(f"Migration applied out of order: {path.name}")
                    continue

                pending_seen = True
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO schema_migrations (version, sha256) VALUES (%s, %s)",
                    (path.name, digest),
                )
                applied.append(path.name)
                logger.info(
                    "postgres_migration_applied",
                    extra={"event": "postgres_migration_applied", "migration": path.name},
                )
    return applied


if __name__ == "__main__":
    with connect() as connection:
        migrate(connection)
