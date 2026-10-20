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
        elif before["Fragmentos"] != row["Fragmentos"]:
            status = "Quantidade de fragmentos alterada"
        elif before["Tamanho (MiB)"] != row["Tamanho (MiB)"]:
            status = "Tamanho alterado"
        elif before["Última modificação (UTC)"] != row["Última modificação (UTC)"]:
            status = "Data de modificação alterada"
        else:
            status = "Sem alteração detectada"
        changes.append({
            "Mês": month,
            "Comparação": status,
            "Fragmentos anteriores": before["Fragmentos"] if before else None,
            "Fragmentos atuais": row["Fragmentos"],
            "Tamanho anterior (MiB)": before["Tamanho (MiB)"] if before else None,
            "Tamanho atual (MiB)": row["Tamanho (MiB)"],
        })
    return changes
