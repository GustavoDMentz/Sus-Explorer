"""Conservative deterministic planner for a small, auditable subset of SI-PNI questions.

Returns None when the entire utterance does not match a supported grammar.
No partial interpretation or guessing of missing parameters.
"""
from __future__ import annotations

import re
import unicodedata

from sus_explorer.schemas import QueryPlan

MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
MONTH = "(?:" + "|".join(MONTHS) + ")"
UF = "(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)"
YEAR = r"20\d{2}"

def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))

# Full-string patterns intentionally exclude unsupported qualifiers and filters.
_COUNT = re.compile(
    rf"(?:quantas doses foram aplicadas|qual o total de doses|total de doses)"
    rf" (?:de influenza )?(?:no|em) (?P<uf>{UF})"
    rf" (?:em )?(?:(?P<month>{MONTH}) de )?(?P<year>{YEAR})\??",
    re.IGNORECASE,
)
_TEMPORAL = re.compile(
    rf"(?P<intent>qual foi a variacao mensal das doses|"
    rf"calcule a segunda diferenca das doses|"
    rf"calcule a terceira diferenca das doses)"
    rf" (?:no|em) (?P<uf>{UF})"
    rf" (?:de|entre) (?P<start>{MONTH}) (?:a|ate|e)"
    rf" (?P<end>{MONTH}) de (?P<year>{YEAR})\??",
    re.IGNORECASE,
)

def deterministic_plan(question: str) -> QueryPlan | None:
    """Recognize complete, unambiguous templates; otherwise delegate to LLM."""
    if not isinstance(question, str) or len(question) > 2048:
        return None
    q = _normalize(question.strip())
    match = _COUNT.fullmatch(q)
    if match:
        payload = {
            "operation": "count",
            "uf": match["uf"].upper(),
            "year": int(match["year"]),
        }
        if match["month"]:
            payload["month"] = MONTHS[match["month"]]
    else:
        match = _TEMPORAL.fullmatch(q)
        if not match:
            return None
        start, end = MONTHS[match["start"]], MONTHS[match["end"]]
        if start > end:
            return None
        intent = match["intent"]
        order = 3 if "terceira" in intent else 2 if "segunda" in intent else 1
        payload = {
            "operation": "temporal",
            "uf": match["uf"].upper(),
            "start_year": int(match["year"]),
            "start_month": start,
            "end_year": int(match["year"]),
            "end_month": end,
            "temporal_analysis": {
                "order": order,
                "comparison": "mom",
                "metric": "doses",
                "granularity": "monthly",
            },
        }
    try:
        plan = QueryPlan.model_validate(payload)
    except ValueError:
        return None
    return plan if plan.status == "ready" else None
