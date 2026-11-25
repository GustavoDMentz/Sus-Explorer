import json
import os
import stat
import subprocess

import pytest

from sus_explorer.operational_logging import JsonlRunLogger, redact, sanitize_text


@pytest.mark.parametrize("text, leaked", [
    ("Authorization: Bearer abc123tokenvalue", "abc123tokenvalue"),
    ("Bearer eyJhbGci.abc.def.ghijk", "eyJhbGci"),
    ('{"password": "hunter2"}', "hunter2"),
    ("DB_PASSWORD=hunter2", "hunter2"),
    ("AWS_SECRET_ACCESS_KEY=abcd1234", "abcd1234"),
    ("postgresql://u:pw123@localhost:5432/db", "pw123"),
    ("redis://:senhaforte@cache:6379/0", "senhaforte"),
    ("senha=abc", "abc"),
    ('password="my secret pass"', "secret pass"),
    ("accessToken: abc123", "abc123"),
    ("cartao CNS 700000000000000", "700000000000000"),
])
def test_common_credential_formats_are_redacted(text, leaked):
    assert leaked not in sanitize_text(text)


@pytest.mark.parametrize("text", ["secretaria=RS", "tokens=3", "status=200 count=3", "uf=RS"])
def test_ordinary_text_is_not_redacted(text):
    assert sanitize_text(text) == text


def test_camel_case_and_portuguese_keys_are_redacted():
    cleaned = redact({"apiKey": "x", "accessToken": "y", "database_url": "z",
                      "senha": "w", "nu_cep": "9", "secretaria": "RS", "uf": "RS"})
    assert {k: v for k, v in cleaned.items() if v != "[REDACTED]"} == {"secretaria": "RS", "uf": "RS"}


def test_log_files_have_restricted_permissions(tmp_path):
    logger = JsonlRunLogger("perm_test", log_root=tmp_path / "logs", run_id="perm-run")
    logger.event("ok", rows=1)
    mode = stat.S_IMODE(logger.path.stat().st_mode)
    if os.name == "nt":
        # Windows ignores POSIX mode bits on creation. Check the effective
        # inherited ACL instead; the temp directory grants only owner, SYSTEM
        # and administrators in the supported Windows test environment.
        acl = subprocess.run(
            ["icacls", str(logger.path)], capture_output=True, text=True, check=True
        ).stdout.casefold()
        assert not any(name in acl for name in (
            "everyone", "todos", "authenticated users", "usuários autenticados",
            "builtin\\users", "builtin\\usuários",
        ))
    else:
        assert mode & 0o077 == 0
    assert json.loads(logger.path.read_text("utf-8"))["event"] == "ok"
