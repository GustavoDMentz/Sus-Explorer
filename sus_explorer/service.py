from __future__ import annotations

from .llm import GeminiAnalyst
from .pni import PNIRemote


FIELD_LABELS = {
    "year": "ano",
    "month": "mês",
    "day": "dia",
    "period": "período",
    "uf": "UF",
    "municipality": "município",
    "start_year": "ano inicial",
    "start_month": "mês inicial",
    "end_year": "ano final",
    "end_month": "mês final",
    "temporal_analysis": "ordem da diferença temporal",
}


def humanize_fields(fields: list[str]) -> list[str]:
    return [
        FIELD_LABELS.get(field, field)
        for field in fields
    ]


class SUSExplorer:
    def __init__(self):
        self.llm = GeminiAnalyst()
        self.pni = PNIRemote()

    def ask(self, question: str) -> dict:
        plan = self.llm.plan(question)

        if plan.status == "needs_clarification":
            return {
                "needs_clarification": True,
                "clarification_question": (
                    plan.clarification_question
                    or "Preciso de mais informações para fazer a consulta."
                ),
                "missing": humanize_fields(plan.missing),
                "missing_internal": plan.missing,
                "plan": plan.model_dump(),
                "result": None,
                "answer": None,
            }

        missing = self._missing_fields(plan)

        if missing:
            readable = humanize_fields(missing)

            if missing == ["year"]:
                question_text = "De qual ano?"
            elif missing == ["uf"]:
                question_text = "De qual estado (UF)?"
            else:
                question_text = (
                    "Preciso que você informe: "
                    + ", ".join(readable)
                    + "."
                )

            return {
                "needs_clarification": True,
                "clarification_question": question_text,
                "missing": readable,
                "missing_internal": missing,
                "plan": plan.model_dump(),
                "result": None,
                "answer": None,
            }

        result = self.pni.execute(plan)

        answer = self.llm.answer(
            question,
            plan,
            result,
        )

        return {
            "needs_clarification": False,
            "clarification_question": None,
            "missing": [],
            "missing_internal": [],
            "plan": plan.model_dump(),
            "result": result.model_dump(),
            "answer": answer,
        }

    @staticmethod
    def _missing_fields(plan) -> list[str]:
        missing = []

        if not plan.uf:
            missing.append("uf")

        if plan.operation in {
            "count",
            "group",
            "latency",
        }:
            # Ano é obrigatório.
            #
            # Mês NÃO é obrigatório:
            # year=2024, month=None significa o ano inteiro.
            if plan.year is None:
                missing.append("year")

        elif plan.operation in {"timeseries", "temporal"}:
            required = {
                "start_year": plan.start_year,
                "start_month": plan.start_month,
                "end_year": plan.end_year,
                "end_month": plan.end_month,
            }

            for field, value in required.items():
                if value is None:
                    missing.append(field)

            if plan.operation == "temporal" and plan.temporal_analysis is None:
                missing.append("temporal_analysis")

        elif plan.operation is None:
            raise ValueError(
                "O planner não definiu uma operação."
            )

        return list(dict.fromkeys(missing))
