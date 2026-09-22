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

# Diretórios de dados brutos e quarentena
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
QUARANTINE_ROOT = PROJECT_ROOT / "data" / "quarantine"

# Diretórios de auditoria
AUDIT_ROOT = PROJECT_ROOT / "audit"
AUDIT_REPORTS = AUDIT_ROOT / "reports"
AUDIT_DIFFERENCES = AUDIT_ROOT / "differences"
AUDIT_PROVENANCE = AUDIT_ROOT / "provenance"
