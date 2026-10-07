"""Defensive validation for untrusted operational persistence inputs."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import Any

from ...operational_logging import sanitize_text


SOURCE_MAX_CHARS = 128
RESOURCE_TYPE_MAX_CHARS = 128
SOURCE_RESOURCE_ID_MAX_CHARS = 1024
RECORD_KEY_MAX_CHARS = 1024
EXTERNAL_ID_MAX_CHARS = 1024
PROJECTION_TEXT_MAX_CHARS = 256
MUNICIPALITY_CODE_MAX_CHARS = 16
ERROR_SUMMARY_MAX_CHARS = 2048
METADATA_MAX_BYTES = 256 * 1024
PAYLOAD_MAX_BYTES = 4 * 1024 * 1024
JSON_MAX_DEPTH = 32
JSON_MAX_NODES = 100_000

_SECRET_ENV_NAME = re.compile(
    r"(?:password|secret|token|api_key|access_key|credential)", re.IGNORECASE
)


def validate_text(
    name: str,
    value: str | None,
    *,
    max_chars: int,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    if value != value.strip() or not value:
        raise ValueError(f"{name} must be non-empty and trimmed")
    if "\x00" in value or len(value) > max_chars:
        raise ValueError(f"{name} exceeds its allowed size")
    return value


def validate_json_object(
    name: str,
    value: Mapping[str, Any],
    *,
    max_bytes: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")

    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > JSON_MAX_NODES or depth > JSON_MAX_DEPTH:
            raise ValueError(f"{name} exceeds JSON complexity limits")
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str) or "\x00" in key:
                    raise ValueError(f"{name} contains an invalid object key")
                stack.append((child, depth + 1))
        elif isinstance(item, (list, tuple)):
            stack.extend((child, depth + 1) for child in item)

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"{name} must contain valid JSON values") from exc
    if len(encoded) > max_bytes:
        raise ValueError(f"{name} exceeds its allowed size")
    return dict(value)


def sanitize_error_summary(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("error_summary must be text")
    secrets = tuple(
        env_value
        for env_name, env_value in os.environ.items()
        if env_value and _SECRET_ENV_NAME.search(env_name)
    )
    sanitized = sanitize_text(value, secrets)
    sanitized = " ".join(sanitized.split())
    if not sanitized:
        return None
    return sanitized[:ERROR_SUMMARY_MAX_CHARS]
