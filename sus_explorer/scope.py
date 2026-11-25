"""Explicit analytical scope boundaries for the SI-PNI-only product."""
from __future__ import annotations

import re
import unicodedata


_UNSUPPORTED = (
    (re.compile(r"\b(?:producao|procedimentos?)\s+ambulatori"),
     "produção ou procedimentos ambulatoriais"),
    (re.compile(r"\b(?:valor(?:es)?\s+financeir|faturamento|custo(?:s)?\s+hospitalar)"),
     "valores financeiros"),
    (re.compile(r"\b(?:pacientes?\s+unic|pessoas?\s+vacinad)"),
     "pessoas ou pacientes únicos"),
    (re.compile(r"\b(?:numero|quantidade|total)\s+de\s+atendimentos?\b"),
     "quantidade de atendimentos"),
    (re.compile(r"\bcobertura\s+vacinal\b"), "cobertura vacinal"),
)


def unsupported_scope(question: str) -> str | None:
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", question.casefold())
        if not unicodedata.combining(char)
    )
    for pattern, label in _UNSUPPORTED:
        if pattern.search(normalized):
            return label
    return None


def scope_message(label: str) -> str:
    return (
        f"O SUS Explorer atual não possui dados para responder sobre {label}. "
        "A base analítica implementada contém eventos de doses registradas no SI-PNI; "
        "ela não mede pessoas únicas, atendimentos, produção ambulatorial, valores "
        "financeiros nem cobertura vacinal."
    )
