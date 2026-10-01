"""Manual CLI for a single query against the current R2/LLM flow."""

import json
import sys

from sus_explorer.query_service import SUSExplorer


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python -m scripts.demo "pergunta"')
    result = SUSExplorer().ask(" ".join(sys.argv[1:]))
    print("\n=== RESPOSTA ===\n", result["answer"])
    print("\n=== PLANO ===")
    print(json.dumps(result["plan"], ensure_ascii=False, indent=2))
    print("\n=== RESULTADO ===")
    print(json.dumps(result["result"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
