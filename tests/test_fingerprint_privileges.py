"""Regression contract for migration 006 (offline, no PostgreSQL required)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "sus_explorer" / "data" / "persistence" / "migrations"


def test_fingerprint_update_is_revoked_in_new_migration():
    migration = (MIGRATIONS / "006_immutable_source_fingerprint.sql").read_text()
    assert "REVOKE UPDATE (source_fingerprint) ON analytical_result_versions" in migration
    assert "FROM sus_explorer_runtime" in migration
    assert "REVOKE UPDATE (last_seen_at" not in migration
    assert "REVOKE UPDATE (observations" not in migration


def test_runtime_deduplication_does_not_update_fingerprint():
    source = (ROOT / "sus_explorer" / "data" / "persistence" / "result_versions.py").read_text()
    start = source.index("UPDATE analytical_result_versions")
    end = source.index('"""', start)
    assert "source_fingerprint" not in source[start:end]
    assert "last_seen_at" in source[start:end]
    assert "observations" in source[start:end]
