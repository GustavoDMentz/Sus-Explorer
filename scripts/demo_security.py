"""Demonstração executável dos controles de segurança e privacidade (nov/2026).

Roda offline, sem banco, sem rede e sem credenciais; só usa valores sintéticos. Cada seção
mostra a entrada e o resultado real do código que está na `master`.

    python scripts/demo_security.py

A parte que depende de PostgreSQL (privilégios por login, troca atômica, expurgo) é provada
pelos testes de integração; veja docs/security-architecture.md.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sus_explorer import disclosure  # noqa: E402
from sus_explorer.data.persistence.immunization_transform import project  # noqa: E402
from sus_explorer.data.zip_guard import UnsafeZipError, check_archive  # noqa: E402
from sus_explorer.operational_logging import redact, sanitize_text  # noqa: E402
from sus_explorer.schemas import QueryPlan  # noqa: E402
from sus_explorer.text_safety import strip_remote_images  # noqa: E402


def section(title: str) -> None:
    print(f"\n## {title}")


def logs() -> None:
    section("1. Redação de logs (credenciais nunca chegam ao arquivo)")
    for text in ("Authorization: Bearer abc123tokenvalue", "DB_PASSWORD=hunter2",
                 "postgresql://u:pw123@localhost:5432/db", "senha=abc", "secretaria=RS"):
        print(f"  {text!r:46} -> {sanitize_text(text)!r}")
    print("  ", redact({"apiKey": "x", "accessToken": "y", "uf": "RS"}))


def plan_bounds() -> None:
    section("2. Limites do plano gerado pelo LLM (qualquer operação)")
    for extra in ({"uf": "ZZ"}, {"municipality_code": "12"}, {"vaccine_text": "x" * 129}, {"top_n": 101}):
        label = {k: (v if len(str(v)) < 12 else str(v)[:9] + "...") for k, v in extra.items()}
        try:
            QueryPlan(operation="count", year=2026, month=5, **extra)
            print(f"  aceito   {label}")
        except Exception as exc:
            print(f"  recusado {str(label):38} -> {type(exc).__name__}")


def disclosure_control() -> None:
    section("3. Controle de divulgação (limiar 5)")
    count = {"doses": 3}
    disclosure.apply("count", count, 5)
    print("  contagem 3          ->", count)
    group = {"rows": [{"value": "F", "count": 50}, {"value": "M", "count": 3}], "total_after_filters": 53}
    disclosure.apply("group", group, 5)
    print("  grupo com célula 3  ->", group)
    visible = {"rows": [{"value": "F", "count": 50}, {"value": "M", "count": 40}], "total_after_filters": 90}
    disclosure.apply("group", visible, 5)
    print("  grupo sem células pequenas ->", visible)
    latency = {"n_valid": 3, "median_days": 1.0, "p90_days": 2.0, "p95_days": 3.0}
    disclosure.apply("latency", latency, 5)
    print("  latência, 3 registros ->", latency)
    print("  idade 87-87 vira", disclosure.snap_age_range(87, 87)[:2], "| 18-64 vira", disclosure.snap_age_range(18, 64)[:2])


def payload_allowlist() -> None:
    section("4. Lista de colunas guardadas (minimização)")
    row = {"co_documento": "doc-1", "co_vacina": "33", "dt_vacina": "2026-05-01",
           "co_municipio_estabelecimento": "4314902", "sg_uf_estabelecimento": "RS", "tp_sexo_paciente": "F",
           "co_paciente": "PAC-1", "nu_cep": "90010000", "dt_nascimento": "1950-01-01"}
    _, payload, _ = project(row, "RS")
    print("  colunas da entrada :", sorted(row))
    print("  colunas guardadas  :", sorted(payload))
    print("  descartadas        :", sorted(set(row) - set(payload)))


def zips() -> None:
    section("5. Leitura de ZIP (zip-slip e zip bomb)")

    def make(members, compression=zipfile.ZIP_STORED):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression) as archive:
            for name, data in members:
                archive.writestr(name, data)
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    cases = (("normal", make([("a.csv", b"x")]), "a.csv"),
             ("zip-slip", make([("../evil.csv", b"x")]), None),
             ("zip bomb (5 MB de zeros)", make([("a.csv", b"0" * 5_000_000)], zipfile.ZIP_DEFLATED), "a.csv"))
    for label, archive, member in cases:
        try:
            check_archive(archive, member)
            print(f"  {label:26} -> aceito")
        except UnsafeZipError as exc:
            print(f"  {label:26} -> recusado: {exc}")


def images() -> None:
    section("6. Imagens remotas em texto de terceiros (beacon)")
    text = "veja ![x](https://evil.example/p.png) e [link](https://example.org)"
    print(f"  {text!r}\n  -> {strip_remote_images(text)!r}")


if __name__ == "__main__":
    for step in (logs, plan_bounds, disclosure_control, payload_allowlist, zips, images):
        step()
    print("\nOK: todos os controles acima rodaram offline com dados sintéticos.")
