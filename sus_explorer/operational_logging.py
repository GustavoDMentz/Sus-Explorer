"""Structured JSONL logging for operational runs.

Operational logs are intentionally separate from scientific audit artifacts.
They contain execution metadata and aggregate counts only, never source rows.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .paths import PROJECT_ROOT


SCHEMA_VERSION = 1
OPERATIONAL_LOG_ROOT = PROJECT_ROOT / "logs"
_SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|credential|password|secret|token|api_key|access_key|cpf|cns|patient|paciente)($|_)",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|authorization|api[_-]?key|"
    r"access[_-]?key|credential|dsn)\b\s*[:=]\s*([^\s,;&]+)"
)
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_SENSITIVE_QUERY_NAMES = {
    "access_token", "apikey", "api_key", "authorization", "auth",
    "awsaccesskeyid", "googleaccessid", "id_token", "key", "key-pair-id",
    "password", "policy", "refresh_token", "secret", "sig", "signature",
    "token", "x-amz-credential", "x-amz-security-token", "x-amz-signature",
    "x-goog-credential", "x-goog-signature",
}


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp with a trailing Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def new_run_id(component: str) -> str:
    """Create a sortable, human-readable identifier for one execution."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_component = re.sub(r"[^a-z0-9_-]+", "-", component.lower()).strip("-")
    return f"{safe_component}-{stamp}-{uuid.uuid4().hex[:8]}"


def _sensitive_query_name(name: str) -> bool:
    normalized = name.casefold()
    return normalized in _SENSITIVE_QUERY_NAMES or normalized.endswith(
        ("credential", "password", "secret", "signature", "token")
    )


def _sanitize_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname or ""
        if parsed.port is not None:
            hostname = f"{hostname}:{parsed.port}"
        query = urlencode([
            (name, _REDACTED if _sensitive_query_name(name) else value)
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        ])
        return urlunsplit((parsed.scheme, hostname, parsed.path, query, ""))
    except Exception:
        return "[REDACTED_URL]"


def sanitize_text(value: str, secrets: Iterable[str] = ()) -> str:
    """Remove credentials and signed-URL material from arbitrary text."""
    sanitized = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}={_REDACTED}", value
    )
    sanitized = _URL.sub(_sanitize_url, sanitized)
    sanitized = _EMAIL.sub(_REDACTED, sanitized)
    sanitized = _CPF.sub(_REDACTED, sanitized)
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, _REDACTED)
    return sanitized


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return str(value)


def redact(value: Any, secrets: Iterable[str] = ()) -> Any:
    """Recursively redact sensitive fields and known secret values."""
    known = tuple(secret for secret in secrets if secret)

    def clean(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                str(key): _REDACTED if _SENSITIVE_KEY.search(str(key)) else clean(val)
                for key, val in item.items()
            }
        if isinstance(item, (list, tuple, set, frozenset)):
            return [clean(val) for val in item]
        normalized = _json_value(item)
        if isinstance(normalized, str):
            normalized = sanitize_text(normalized, known)
        return normalized

    return clean(value)


class JsonlRunLogger:
    """Append-only JSONL logger scoped to a single command execution."""

    def __init__(
        self,
        component: str,
        *,
        log_root: Path = OPERATIONAL_LOG_ROOT,
        run_id: str | None = None,
        secrets: Iterable[str] = (),
    ) -> None:
        self.component = component
        self.run_id = run_id or new_run_id(component)
        self.secrets = tuple(secret for secret in secrets if secret)
        self._lock = threading.Lock()
        self.path: Path | None = None
        self.last_error: Exception | None = None
        try:
            log_root.mkdir(parents=True, exist_ok=True)
            self.path = log_root / f"{self.run_id}.jsonl"
        except Exception as exc:
            self.last_error = exc

    def event(self, event: str, *, level: str = "INFO", **fields: Any) -> dict[str, Any]:
        try:
            record = {
                **fields,
                "schema_version": SCHEMA_VERSION,
                "timestamp": utc_timestamp(),
                "level": level.upper(),
                "component": self.component,
                "event": event,
                "run_id": self.run_id,
                "pid": os.getpid(),
            }
            safe_record = redact(record, self.secrets)
            encoded = json.dumps(safe_record, ensure_ascii=False, sort_keys=True)
            if self.path is not None:
                with self._lock, self.path.open("a", encoding="utf-8") as stream:
                    stream.write(encoded + "\n")
            return safe_record
        except Exception as exc:
            self.last_error = exc
            return {
                "schema_version": SCHEMA_VERSION,
                "component": self.component,
                "event": event,
                "run_id": self.run_id,
                "level": "ERROR",
                "logging_failed": True,
            }

    def exception(self, event: str, exc: BaseException, **fields: Any) -> dict[str, Any]:
        """Log exception metadata without a traceback or source data."""
        try:
            return self.event(
                event,
                level="ERROR",
                error_type=type(exc).__name__,
                error=str(exc),
                **fields,
            )
        except Exception as logging_exc:
            self.last_error = logging_exc
            return {
                "schema_version": SCHEMA_VERSION,
                "component": self.component,
                "event": event,
                "run_id": self.run_id,
                "level": "ERROR",
                "logging_failed": True,
            }
