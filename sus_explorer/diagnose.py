"""Read-only diagnostics for the local SUS Explorer runtime."""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageBudget:
    temporary_gib: float | None = None
    postgres_gib: float | None = None
    indexes_gib: float | None = None
    wal_gib: float | None = None
    margin_gib: float | None = None

    @property
    def total_gib(self) -> float:
        return sum(value for value in (
            self.temporary_gib, self.postgres_gib, self.indexes_gib,
            self.wal_gib, self.margin_gib) if value is not None)

    @property
    def complete(self) -> bool:
        return all(value is not None for value in (
            self.temporary_gib, self.postgres_gib, self.indexes_gib,
            self.wal_gib, self.margin_gib))

    def validate(self) -> None:
        if any(value is not None and value < 0 for value in (
                self.temporary_gib, self.postgres_gib, self.indexes_gib,
                self.wal_gib, self.margin_gib)):
            raise ValueError("Estimativas de armazenamento não podem ser negativas")


def run(storage: StorageBudget | None = None) -> int:
    storage = storage or StorageBudget()
    storage.validate()
    failures = 0

    def report(name: str, ok: bool, detail: str) -> None:
        nonlocal failures
        print(f"{'OK' if ok else 'PENDENTE'} {name}: {detail}")
        failures += not ok

    report("Python", sys.version_info >= (3, 12), sys.version.split()[0]
           + (" (recomendado: 3.12)" if sys.version_info[:2] != (3, 12) else ""))
    for package in ("streamlit", "pydantic", "psycopg", "requests", "python-dotenv"):
        try:
            report(f"Dependência {package}", True, importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:
            report(f"Dependência {package}", False, "não instalada neste ambiente Python")

    env_path = Path(".env")
    report("Configuração", env_path.exists(), ".env presente" if env_path.exists()
           else "crie .env a partir de .env.example e configure as senhas reais")

    disk = shutil.disk_usage(Path.cwd())
    free_gb = disk.free / (1024 ** 3)
    categories = (
        ("temporário de uma competência", storage.temporary_gib),
        ("dados PostgreSQL", storage.postgres_gib),
        ("índices", storage.indexes_gib),
        ("WAL/manutenção", storage.wal_gib),
        ("margem operacional", storage.margin_gib),
    )
    detail = "; ".join(
        f"{name}={value:.1f} GiB" if value is not None else f"{name}=não informado"
        for name, value in categories)
    report("Armazenamento", storage.complete and storage.total_gib <= free_gb,
           f"{free_gb:.1f} GiB livres; soma conhecida={storage.total_gib:.1f} GiB ({detail})")

    try:
        from .data.persistence.database import connect_reader
        with connect_reader() as db:
            db.execute("SELECT 1").fetchone()
            vector = db.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            versions = {row["version"] for row in db.execute("SELECT version FROM schema_migrations").fetchall()}
        report("PostgreSQL", True, "conexão de leitura operacional")
        report("pgvector", vector is not None, vector["extversion"] if vector else "extensão vector ausente")
        migrations = sorted(p.name for p in (Path(__file__).parent / "data/persistence/migrations").glob("[0-9][0-9][0-9]_*.sql"))
        pending = sorted(set(migrations) - versions)
        report("Migrations", not pending, "todas aplicadas" if not pending else "pendentes: " + ", ".join(pending))
    except Exception as exc:
        report("PostgreSQL", False, f"{type(exc).__name__}; confira variáveis e serviço")
        report("pgvector/migrations", False, "não verificável sem conexão PostgreSQL")

    try:
        from .ollama import OllamaClient
        client = OllamaClient()
        model = os.getenv("OLLAMA_CHAT_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
        embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b")
        response = client.session.get(
            client.base_url + "/api/tags", timeout=(5, 10), allow_redirects=False
        )
        if 300 <= response.status_code < 400:
            raise RuntimeError("Ollama redirect refused")
        response.raise_for_status()
        models = response.json().get("models", [])
        names = {item.get("name") for item in models}
        report("Ollama", True, client.base_url)
        report("Modelo de chat", model in names, model if model in names else f"ausente: {model}")
        if embedding_model in names:
            dimension = len(client.embed(["Verificação de dimensão do SUS Explorer."])[0])
            expected = int(os.getenv("RAG_EMBEDDING_DIM", "1024"))
            report("Modelo de embedding", dimension == expected,
                   f"{embedding_model}; dimensão {dimension}, esperada {expected}")
        else:
            report("Modelo de embedding", False, f"ausente: {embedding_model}")
    except Exception as exc:
        report("Ollama", False, f"{type(exc).__name__}; confira endpoint e serviço")
        report("Modelos/dimensão", False, "não verificáveis sem Ollama")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporary-gib", type=float,
                        help="maior ZIP mantido no staging durante a carga incremental")
    parser.add_argument("--postgres-gib", type=float,
                        help="estimativa medida ou planejada para tabelas PostgreSQL")
    parser.add_argument("--indexes-gib", type=float)
    parser.add_argument("--wal-gib", type=float,
                        help="reserva para WAL e operações de manutenção")
    parser.add_argument("--margin-gib", type=float)
    args = parser.parse_args()
    budget = StorageBudget(args.temporary_gib, args.postgres_gib, args.indexes_gib,
                           args.wal_gib, args.margin_gib)
    try:
        budget.validate()
    except ValueError as exc:
        parser.error(str(exc))
    return run(budget)


if __name__ == "__main__":
    raise SystemExit(main())
