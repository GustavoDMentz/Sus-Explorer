"""
Definições de caminhos centralizadas do SUS Explorer.

Todos os caminhos padrão são baseados na raiz do projeto.
"""

from __future__ import annotations

from pathlib import Path

# Raiz do projeto (diretório pai de sus_explorer)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Cache local do cubo SI-PNI
CACHE_ROOT = PROJECT_ROOT / "cache" / "pni_cube"

# Audit artifacts stay separate from disposable caches.
AUDIT_ROOT = PROJECT_ROOT / "audit"

# FHIR terminology is a per-user cache, not part of the PNI cube.
TERMINOLOGY_CACHE_FILE = Path.home() / ".cache" / "sus_explorer" / "BRImunobiologico_ms_go.json"
