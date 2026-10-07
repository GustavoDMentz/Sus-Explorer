"""Best-effort PostgreSQL events using the canonical operational logger."""

from __future__ import annotations

from typing import Any

from ...operational_logging import JsonlRunLogger


_logger: JsonlRunLogger | None = None


def get_logger() -> JsonlRunLogger:
    """Create one lazy logger so imports never make logging a hard dependency."""
    global _logger
    if _logger is None:
        _logger = JsonlRunLogger("postgres")
    return _logger


def event(name: str, *, level: str = "INFO", **fields: Any) -> dict[str, Any]:
    """Emit a sanitized event without allowing telemetry to break persistence."""
    try:
        return get_logger().event(name, level=level, **fields)
    except Exception:
        return {
            "component": "postgres",
            "event": name,
            "level": "ERROR",
            "logging_failed": True,
        }
