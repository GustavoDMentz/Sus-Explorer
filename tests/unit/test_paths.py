"""
Testes de verificação para o módulo sus_explorer.paths.
"""

from __future__ import annotations

from pathlib import Path

from sus_explorer.paths import (
    AUDIT_ROOT,
    CACHE_ROOT,
    PROJECT_ROOT,
    TERMINOLOGY_CACHE_FILE,
)


def test_paths_are_path_instances():
    for p in [
        PROJECT_ROOT,
        CACHE_ROOT,
        AUDIT_ROOT,
        TERMINOLOGY_CACHE_FILE,
    ]:
        assert isinstance(p, Path)


def test_project_root_contains_sus_explorer():
    assert (PROJECT_ROOT / "sus_explorer").is_dir()


def test_cache_root_relative_to_project_root():
    assert CACHE_ROOT == PROJECT_ROOT / "cache" / "pni_cube"
