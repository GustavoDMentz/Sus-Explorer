"""Apply numbered SQL migrations once, transactionally and in filename order."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .database import connect


MIGRATIONS = Path(__file__).parent / "migrations"


def migrate(connection, directory: Path = MIGRATIONS) -> list[str]:
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("No SQL migrations found")
    applied = []
    with connection.transaction():
        with connection.cursor() as cursor:
            # Serialize concurrent deploys; rollback also releases the lock.
            cursor.execute("SELECT pg_advisory_xact_lock(91627134)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    sha256 text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            cursor.execute("SELECT version, sha256 FROM schema_migrations")
            previous = {row["version"]: row["sha256"] for row in cursor.fetchall()}
            names = {path.name for path in files}
            if unknown := set(previous) - names:
                raise RuntimeError("Applied migrations missing from source: " + ", ".join(sorted(unknown)))
            pending = False
            for path in files:
                sql = path.read_text(encoding="utf-8")
                digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                if path.name in previous:
                    if previous[path.name] != digest:
                        raise RuntimeError(f"Migration changed after application: {path.name}")
                    if pending:
                        raise RuntimeError(f"Migration applied out of order: {path.name}")
                    continue
                pending = True
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO schema_migrations (version, sha256) VALUES (%s, %s)",
                    (path.name, digest),
                )
                applied.append(path.name)
    return applied


if __name__ == "__main__":
    with connect() as connection:
        for name in migrate(connection):
            print(f"Applied {name}")
