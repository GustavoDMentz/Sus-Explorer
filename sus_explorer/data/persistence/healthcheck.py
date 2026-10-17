"""Real PostgreSQL connectivity check with no schema mutation."""

from .database import connect


def check_postgres() -> bool:
    with connect() as connection:
        row = connection.execute("SELECT 1 AS healthy").fetchone()
        return row is not None and row["healthy"] == 1


if __name__ == "__main__":
    if check_postgres():
        print("PostgreSQL: healthy")
    else:
        raise SystemExit("PostgreSQL: unhealthy")
