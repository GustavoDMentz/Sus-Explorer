from __future__ import annotations
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


Operation = Literal["count", "group", "timeseries", "latency", "temporal"]
PlanStatus = Literal["ready", "needs_clarification"]
ResultClassification = Literal["DIRECT", "DERIVED", "ENRICHED"]


class TemporalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: Annotated[int, Field(strict=True, ge=1, le=3)]
    metric: Literal["doses"] = "doses"
    granularity: Literal["monthly"] = "monthly"


class QueryPlan(BaseModel):
    status: PlanStatus = "ready"
    temporal_analysis: TemporalRequest | None = None

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

    @model_validator(mode="before")
    @classmethod
    def validate_temporal_input(cls, values):
        if isinstance(values, dict) and values.get("operation") == "temporal":
            unknown = set(values) - set(cls.model_fields)
            if unknown:
                raise ValueError("Unsupported temporal plan fields")
            for name in ("start_year", "start_month", "end_year", "end_month", "age_min", "age_max"):
                if values.get(name) is not None and type(values[name]) is not int:
                    raise ValueError(f"{name} must be an integer")
        return values

    def temporal_missing_fields(self) -> list[str]:
        return [name for name in (
            "uf", "start_year", "start_month", "end_year", "end_month", "temporal_analysis"
        ) if getattr(self, name) is None or getattr(self, name) == ""]

    def validate_temporal(self) -> None:
        valid_ufs = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
        if self.uf and self.uf not in valid_ufs:
            raise ValueError("Invalid temporal UF")
        for name in ("start_year", "end_year", "start_month", "end_month"):
            value = getattr(self, name)
            if value is not None:
                lower, upper = (2020, 2100) if name.endswith("year") else (1, 12)
                if not lower <= value <= upper:
                    raise ValueError(f"Invalid temporal {name}")
        if all(value is not None for value in (self.start_year, self.start_month, self.end_year, self.end_month)):
            if (self.start_year, self.start_month) > (self.end_year, self.end_month):
                raise ValueError("Temporal start must not follow end")
        if self.top_n != 20 or any(getattr(self, name) is not None for name in ("year", "month", "day", "group_by")):
            raise ValueError("Temporal plans require an explicit monthly interval, without day/group_by")
        for name in ("age_min", "age_max"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 200:
                raise ValueError("Invalid temporal age filter")
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("Temporal age_min must not exceed age_max")
        if self.municipality_code and not re.fullmatch(r"[0-9]{6,7}", self.municipality_code):
            raise ValueError("Temporal municipality_code must be a public IBGE code")
        if self.municipality_code and self.municipality_name:
            raise ValueError("Choose municipality_code or municipality_name for temporal filtering")
        if self.vaccine_code and not re.fullmatch(r"[0-9]{1,8}", self.vaccine_code):
            raise ValueError("Temporal vaccine_code must be an explicit numeric code")
        for name in ("municipality_name", "vaccine_text"):
            value = getattr(self, name)
            if value is not None and (not value.strip() or len(value) > 128 or
                                      any(not (c.isalpha() or c.isdigit() or c in " -().'/") for c in value) or
                                      "://" in value):
                raise ValueError(f"Invalid temporal {name}")

    @model_validator(mode="after")
    def validate_plan(self):

        if self.uf:
            self.uf = self.uf.upper()

        if self.operation == "temporal":
            self.validate_temporal()
            if self.status == "ready" and (missing := self.temporal_missing_fields()):
                self.status = "needs_clarification"
                self.missing = missing
                self.clarification_question = "Informe os parâmetros temporais ausentes: " + ", ".join(missing)
        elif self.temporal_analysis is not None:
            raise ValueError("temporal_analysis requires operation=temporal")

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
