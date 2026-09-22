from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


Operation = Literal["count", "group", "timeseries", "latency"]
PlanStatus = Literal["ready", "needs_clarification"]


class QueryPlan(BaseModel):
    status: PlanStatus = "ready"

    clarification_question: str | None = None
    missing: list[str] = Field(default_factory=list)

    operation: Operation | None = None

    year: int | None = Field(default=None, ge=2020, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)

    start_year: int | None = None
    start_month: int | None = None
    end_year: int | None = None
    end_month: int | None = None

    uf: str | None = None
    municipality_code: str | None = None
    municipality_name: str | None = None

    vaccine_code: str | None = None
    vaccine_text: str | None = None

    age_min: int | None = None
    age_max: int | None = None
    sex: Literal["M", "F"] | None = None

    group_by: str | None = None
    top_n: int = 20

    @model_validator(mode="after")
    def validate_plan(self):

        if self.uf:
            self.uf = self.uf.upper()

        # Se o planner já reconheceu falta de informação,
        # não exige plano executável.
        if self.status == "needs_clarification":
            if not self.clarification_question:
                raise ValueError(
                    "needs_clarification exige clarification_question"
                )
            return self

        if self.operation is None:
            raise ValueError("Plano ready exige operation.")

        return self
