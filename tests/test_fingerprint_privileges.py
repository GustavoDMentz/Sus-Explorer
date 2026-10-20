"""Offline checks for narrow runtime UPDATE privileges."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "sus_explorer" / "data" / "persistence" / "migrations"


def test_migration_revokes_fingerprint_update():
    sql = (MIGRATIONS / "006_immutable_source_fingerprint.sql").read_text()
    assert "REVOKE UPDATE (source_fingerprint)" in sql
    assert "FROM sus_explorer_runtime" in sql


def test_deduplication_does_not_update_fingerprint():
    source = (ROOT / "sus_explorer" / "data" / "persistence" / "result_versions.py").read_text()
    start = source.index("UPDATE analytical_result_versions")
    end = source.index('"""', start)
    assert "source_fingerprint" not in source[start:end]
    assert "last_seen_at" in source[start:end]
    assert "observations" in source[start:end]
