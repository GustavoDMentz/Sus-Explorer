"""Smoke test for one already imported PostgreSQL competence."""

from sus_explorer.postgres_executor import PostgresQueryExecutor
from sus_explorer.schemas import QueryPlan


if __name__ == "__main__":
    plan = QueryPlan(operation="count", year=2020, month=1, uf="AC")
    print(PostgresQueryExecutor().execute(plan).model_dump_json(indent=2))
