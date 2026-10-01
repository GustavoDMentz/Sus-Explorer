"""Manual remote smoke test; requires R2 configuration."""

from sus_explorer.pni import PNIRemote
from sus_explorer.schemas import QueryPlan


def main() -> None:
    plan = QueryPlan(operation="count", year=2026, month=5, uf="RS")
    print(PNIRemote().execute(plan).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
