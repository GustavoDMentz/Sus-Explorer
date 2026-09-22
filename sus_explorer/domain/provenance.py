"""
Modelos de dados para rastreabilidade, proveniência e auditoria do SUS Explorer.

Modelos futuros para registro de proveniência de dados e resultados de auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SourceFingerprint:
    """Impressão digital e proveniência de um recurso bruto fonte."""

    provider: str
    resource_id: str
    filename: str
    url: str | None = None
    sha256: str | None = None
    bytes_size: int | None = None
    retrieved_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class AuditResult:
    """Resultado estruturado de uma verificação de auditoria."""

    period: str
    raw_rows: int
    cube_rows: int
    raw_doses: int
    cube_doses: int
    status: str
    source_fingerprint: SourceFingerprint | None = None
    verified_at: str = field(default_factory=utc_now)
