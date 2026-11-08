"""Compare two catalog snapshots from the same UF/year in one Streamlit session.

Metadata changes indicate possible storage updates, not confirmed revisions
to vaccination records. Unverified months are never classified as changes.
"""
from __future__ import annotations


def compare_snapshots(previous: dict, current: dict) -> list[dict]:
    if (previous["uf"], previous["year"]) != (current["uf"], current["year"]):
        raise ValueError("Compare apenas verificações da mesma UF e ano.")
    old = {row["Mês"]: row for row in previous["rows"]}
    changes = []
    for row in current["rows"]:
        month = row["Mês"]
        before = old.get(month)
        if before is None or "Não verificada" in (before["Situação"], row["Situação"]):
            status = "Comparação indisponível"
        elif before["Situação"] != row["Situação"]:
            status = "Disponibilidade alterada"
        elif before["Registros"] != row["Registros"]:
            status = "Quantidade de registros alterada"
        elif before["Execução"] != row["Execução"]:
            status = "Execução de ingestão alterada"
        elif before["Última ingestão (UTC)"] != row["Última ingestão (UTC)"]:
            status = "Data de ingestão alterada"
        else:
            status = "Sem alteração detectada"
        changes.append({
            "Mês": month,
            "Comparação": status,
            "Registros anteriores": before["Registros"] if before else None,
            "Registros atuais": row["Registros"],
            "Execução anterior": before["Execução"] if before else None,
            "Execução atual": row["Execução"],
        })
    return changes
