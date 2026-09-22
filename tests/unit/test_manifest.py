"""
Testes de regressão para o manifest do cache SI-PNI.

REGRA: nenhum teste escreve em cache/pni_cube/manifest.json.
Todos usam tmp_path para fixtures sintéticas.
"""

from __future__ import annotations

import json

import pytest

from sus_explorer.build_cache import (
    load_manifest,
    save_manifest,
)


# ──────────────────────────────────────────────────────────
# load_manifest
# ──────────────────────────────────────────────────────────

class TestLoadManifest:
    """Congela o comportamento de load_manifest()."""

    def test_nonexistent_returns_empty(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = load_manifest(path)

        assert result["schema_version"] == 1
        assert result["partitions"] == {}
        assert "created_at" in result
        assert "updated_at" in result

    def test_loads_existing_preserves_content(self, tmp_path):
        """Carrega manifest existente sem modificá-lo."""
        manifest = {
            "schema_version": 1,
            "created_at": "2026-09-21T03:09:09.206609+00:00",
            "updated_at": "2026-09-21T03:09:09.206609+00:00",
            "partitions": {
                "2025/RS/01": {
                    "status": "cached",
                    "year": 2025,
                    "month": 1,
                    "uf": "RS",
                    "rows_cube": 67913,
                    "doses": 481488,
                    "bytes": 122340,
                }
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = load_manifest(path)

        assert result["schema_version"] == 1
        assert result["partitions"]["2025/RS/01"]["rows_cube"] == 67913
        assert result["partitions"]["2025/RS/01"]["doses"] == 481488

    def test_finds_known_partition(self, tmp_path):
        """Encontra partição conhecida pelo key."""
        manifest = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "partitions": {
                "2023/RS/10": {
                    "status": "cached",
                    "rows_cube": 1000,
                    "doses": 5000,
                }
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = load_manifest(path)

        assert "2023/RS/10" in result["partitions"]
        assert result["partitions"]["2023/RS/10"]["doses"] == 5000

    def test_preserves_schema_version(self, tmp_path):
        manifest = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "partitions": {},
        }
        path = tmp_path / "manifest.json"
        path.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        result = load_manifest(path)
        assert result["schema_version"] == 1

    def test_corrupted_raises_runtime_error(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("NOT JSON", encoding="utf-8")

        with pytest.raises(RuntimeError, match="Manifest inválido"):
            load_manifest(path)

    def test_read_only_does_not_modify_file(self, tmp_path):
        """load_manifest não escreve no arquivo."""
        manifest = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "partitions": {},
        }
        path = tmp_path / "manifest.json"
        original = json.dumps(manifest, ensure_ascii=False, indent=2)
        path.write_text(original, encoding="utf-8")

        mtime_before = path.stat().st_mtime
        load_manifest(path)
        mtime_after = path.stat().st_mtime

        assert mtime_before == mtime_after
        assert path.read_text(encoding="utf-8") == original


# ──────────────────────────────────────────────────────────
# save_manifest
# ──────────────────────────────────────────────────────────

class TestSaveManifest:
    """Congela o comportamento de save_manifest()."""

    def test_creates_file(self, tmp_path):
        path = tmp_path / "subdir" / "manifest.json"
        manifest = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "partitions": {},
        }

        save_manifest(path, manifest)

        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["schema_version"] == 1
        # updated_at deve ter sido atualizado
        assert loaded["updated_at"] != "2026-01-01T00:00:00+00:00"

    def test_atomic_write_no_tmp_leftover(self, tmp_path):
        """save_manifest usa escrita atômica (os.replace)."""
        path = tmp_path / "manifest.json"
        manifest = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "partitions": {},
        }

        save_manifest(path, manifest)

        # O .tmp não deve ficar para trás
        tmp_file = path.with_suffix(path.suffix + ".tmp")
        assert not tmp_file.exists()

    def test_roundtrip_preserves_partitions(self, tmp_path):
        path = tmp_path / "manifest.json"
        manifest = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "partitions": {
                "2023/RS/10": {
                    "status": "cached",
                    "doses": 12345,
                }
            },
        }

        save_manifest(path, manifest)

        loaded = load_manifest(path)
        assert loaded["partitions"]["2023/RS/10"]["doses"] == 12345
        assert loaded["schema_version"] == 1
