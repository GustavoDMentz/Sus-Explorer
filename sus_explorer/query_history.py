"""Optional operational history boundary for the analytical service."""

from .data.persistence.history import record_query, safe_provenance
from .data.persistence.operational_events import event

__all__ = ["record_query", "safe_provenance", "event"]
