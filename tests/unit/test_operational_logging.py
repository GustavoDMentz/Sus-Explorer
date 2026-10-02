from __future__ import annotations

import json
from pathlib import Path

import pytest

from sus_explorer.operational_logging import JsonlRunLogger, redact, sanitize_text


def test_jsonl_record_has_stable_envelope(tmp_path):
    logger = JsonlRunLogger(
        "test_component",
        log_root=tmp_path,
        run_id="test-run",
    )

    returned = logger.event(
        "completed",
        run_id="cannot-override",
        rows=12,
    )

    lines = logger.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved == returned
    assert saved["schema_version"] == 1
    assert saved["component"] == "test_component"
    assert saved["event"] == "completed"
    assert saved["run_id"] == "test-run"
    assert saved["level"] == "INFO"
    assert saved["timestamp"].endswith("Z")
    assert saved["rows"] == 12
    assert isinstance(saved["pid"], int)


def test_redact_hides_sensitive_keys_recursively():
    value = {
        "access_key_id": "key-value",
        "nested": {
            "client_secret": "secret-value",
            "cpf": "12345678900",
            "safe_count": 3,
        },
        "items": [{"refresh_token": "token-value"}],
    }

    cleaned = redact(value)

    assert cleaned["access_key_id"] == "[REDACTED]"
    assert cleaned["nested"]["client_secret"] == "[REDACTED]"
    assert cleaned["nested"]["cpf"] == "[REDACTED]"
    assert cleaned["nested"]["safe_count"] == 3
    assert cleaned["items"][0]["refresh_token"] == "[REDACTED]"


def test_known_secret_is_removed_from_free_text(tmp_path):
    logger = JsonlRunLogger(
        "test_component",
        log_root=tmp_path,
        run_id="test-run",
        secrets=("super-secret-value",),
    )

    logger.exception(
        "failed",
        RuntimeError("connection rejected super-secret-value"),
    )

    raw = logger.path.read_text(encoding="utf-8")
    saved = json.loads(raw)
    assert "super-secret-value" not in raw
    assert saved["error"] == "connection rejected [REDACTED]"
    assert saved["error_type"] == "RuntimeError"
    assert "traceback" not in saved


def test_path_and_collection_values_are_json_serializable(tmp_path):
    logger = JsonlRunLogger(
        "test_component",
        log_root=tmp_path,
        run_id="test-run",
    )

    logger.event("values", path=tmp_path, ufs={"RS", "SC"})

    saved = json.loads(logger.path.read_text(encoding="utf-8"))
    assert saved["path"] == str(tmp_path)
    assert set(saved["ufs"]) == {"RS", "SC"}


def test_mkdir_failure_is_fail_safe(tmp_path, monkeypatch):
    def fail_mkdir(*args, **kwargs):
        raise PermissionError("read only")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    logger = JsonlRunLogger("test_component", log_root=tmp_path)

    saved = logger.event("still_safe", rows=1)

    assert logger.path is None
    assert isinstance(logger.last_error, PermissionError)
    assert saved["event"] == "still_safe"


def test_write_failure_is_fail_safe(tmp_path, monkeypatch):
    logger = JsonlRunLogger("test_component", log_root=tmp_path)

    def fail_open(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", fail_open)
    saved = logger.event("write_failed", rows=1)

    assert saved["logging_failed"] is True
    assert isinstance(logger.last_error, OSError)


def test_unserializable_object_is_fail_safe(tmp_path):
    class BrokenString:
        def __str__(self):
            raise RuntimeError("cannot stringify")

    logger = JsonlRunLogger("test_component", log_root=tmp_path)
    saved = logger.event("serialization_failed", value=BrokenString())

    assert saved["logging_failed"] is True
    assert isinstance(logger.last_error, RuntimeError)


def test_broken_logger_does_not_mask_application_exception(tmp_path, monkeypatch):
    logger = JsonlRunLogger("test_component", log_root=tmp_path)

    def fail_event(*args, **kwargs):
        raise OSError("logger unavailable")

    monkeypatch.setattr(logger, "event", fail_event)
    with pytest.raises(ValueError, match="original application failure"):
        try:
            raise ValueError("original application failure")
        except ValueError as exc:
            logger.exception("run_failed", exc)
            raise


def test_signed_url_is_sanitized_in_exception(tmp_path):
    logger = JsonlRunLogger("test_component", log_root=tmp_path)
    url = (
        "https://user:password@example.com/data?"
        "X-Amz-Credential=AKIA%2Fscope&X-Amz-Signature=deadbeef&part=1"
    )

    logger.exception("network_failed", RuntimeError(f"request failed: {url}"))

    raw = logger.path.read_text(encoding="utf-8")
    saved = json.loads(raw)
    assert "user:password" not in raw
    assert "AKIA" not in raw
    assert "deadbeef" not in raw
    assert "part=1" in saved["error"]
    assert "%5BREDACTED%5D" in saved["error"]


def test_sensitive_query_parameters_are_case_insensitive():
    text = sanitize_text(
        "https://example.com/object?SiGnAtUrE=abc&ACCESS_TOKEN=def&safe=yes"
    )

    assert "abc" not in text
    assert "def" not in text
    assert "safe=yes" in text


def test_run_id_is_stable_per_instance_and_unique_between_instances(tmp_path):
    first = JsonlRunLogger("test_component", log_root=tmp_path)
    second = JsonlRunLogger("test_component", log_root=tmp_path)

    first_event = first.event("first")
    second_event = first.event("second")

    assert first_event["run_id"] == second_event["run_id"] == first.run_id
    assert first.run_id != second.run_id
