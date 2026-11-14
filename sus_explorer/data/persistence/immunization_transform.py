"""Shared SI-PNI row validation for legacy migration and direct imports."""
from __future__ import annotations
import re
from datetime import date, datetime
from .repositories import ImmunizationProjection
from .validation import PAYLOAD_MAX_BYTES, validate_json_object

DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}(?:$|[T ])")

def _text(value, name: str, *, max_length: int = 256) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"Invalid {name}")
    result = str(value).strip()
    if not result or len(result) > max_length or "\x00" in result:
        raise ValueError(f"Invalid {name}")
    return result


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and DATE_PREFIX.match(value):
        try:
            if len(value) > 10:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    raise ValueError("Invalid dt_vacina")


def project(row: dict, uf: str) -> tuple[str, dict, ImmunizationProjection]:
    key = _text(row.get("co_documento"), "co_documento", max_length=1024)
    vaccine = _text(row.get("co_vacina"), "co_vacina")
    municipality = _text(
        row.get("co_municipio_estabelecimento"), "co_municipio_estabelecimento",
        max_length=16,
    )
    if not re.fullmatch(r"[0-9]{1,8}", vaccine):
        raise ValueError("Invalid co_vacina")
    if not re.fullmatch(r"[0-9]{6,7}", municipality):
        raise ValueError("Invalid co_municipio_estabelecimento")
    row_uf = _text(row.get("sg_uf_estabelecimento"), "sg_uf_estabelecimento", max_length=2)
    if row_uf != uf:
        raise ValueError("Source UF differs from selected partition")
    dose = next((row[name] for name in ("ds_tipo_dose", "ds_dose_vacina", "co_dose_vacina", "co_dose")
                 if name in row and row[name] is not None), None)
    dose = _text(dose, "dose") if dose is not None else None
    vaccination_date = _date(row.get("dt_vacina"))
    payload = {}
    for name, value in row.items():
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        if value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
            raise ValueError("Unsupported source value type")
        payload[name] = value
    payload = validate_json_object("payload", payload, max_bytes=PAYLOAD_MAX_BYTES)
    return key, payload, ImmunizationProjection(
        vaccine_code=vaccine, dose_code=dose, application_date=vaccination_date,
        establishment_municipality_code=municipality, establishment_uf=row_uf,
    )


