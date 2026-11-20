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
    r"(^|_)(authorization|credential|credentials|password|passwd|pwd|senha|secret|token|"
    r"api_key|apikey|access_key|accesskey|private_key|dsn|database_url|connection_string|"
    r"cpf|cns|patient|paciente|nascimento|birth_date|cep)($|_)",
    re.IGNORECASE,
)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _is_sensitive_key(key: Any) -> bool:
    """Match sensitive names in snake_case, kebab-case and camelCase."""
    normalized = _CAMEL_BOUNDARY.sub("_", str(key)).replace("-", "_")
    return bool(_SENSITIVE_KEY.search(normalized))

_REDACTED = "[REDACTED]"
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    r"(?P<key>[A-Za-z0-9_-]*(?:password|passwd|pwd|senha|secret|token|authorization|"
    r"api[_-]?key|access[_-]?key|private[_-]?key|credential|dsn|database[_-]?url|"
    r"connection[_-]?string)(?:[_-][A-Za-z0-9_-]*|(?-i:[A-Z])[A-Za-z0-9_-]*)?)"
    r"(?P<sep>[\"']?\s*[:=]\s*)"
    r"(?P<value>(?:(?:Bearer|Basic)\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;&}\]]+))"
)
_BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}")
# usuario:senha@host em qualquer esquema (postgresql://, redis://, s3://...)
_URI_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]*):([^@\s/]+)@")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
# Digests hexadecimais (SHA-256 etc.) trazem com frequência 11 dígitos seguidos
# (~4% dos SHA-256) e não podem ser confundidos com CPF.
_HEX_DIGEST = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{32,}(?![0-9A-Za-z])")
_CNS = re.compile(r"(?<!\d)\d{15}(?!\d)")
_CPF_OUTSIDE_DIGEST = re.compile(
    f"(?P<digest>{_HEX_DIGEST.pattern})|(?P<cns>{_CNS.pattern})|(?P<cpf>{_CPF.pattern})"
)
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
    # http(s) primeiro: _sanitize_url remove userinfo e assinaturas e mantém a URL válida.
    sanitized = _URL.sub(_sanitize_url, value)
    sanitized = _URI_USERINFO.sub(
        lambda match: f"{match.group(1)}{match.group(2)}:{_REDACTED}@", sanitized
    )
    sanitized = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}{_REDACTED}", sanitized
    )
    sanitized = _BEARER.sub(lambda match: f"{match.group(1)} {_REDACTED}", sanitized)
    sanitized = _EMAIL.sub(_REDACTED, sanitized)
    sanitized = _CPF_OUTSIDE_DIGEST.sub(
        lambda match: match.group("digest") or _REDACTED, sanitized
    )
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
                str(key): _REDACTED if _is_sensitive_key(key) else clean(val)
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
            log_root.mkdir(mode=0o700, parents=True, exist_ok=True)
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
                with self._lock:
                    descriptor = os.open(
                        self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
                    )
                    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
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
