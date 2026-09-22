"""
Testes unitários para sus_explorer.domain.provenance.
"""

from __future__ import annotations

from sus_explorer.domain.provenance import AuditResult, SourceFingerprint


def test_source_fingerprint_creation():
    fp = SourceFingerprint(
        provider="opendatasus",
        resource_id="bb1c023c-e524-48ff-8471-f68f6cdf189e",
        filename="vacinacao_out_2023_csv.zip",
    )
    assert fp.provider == "opendatasus"
    assert fp.filename == "vacinacao_out_2023_csv.zip"
    assert fp.retrieved_at is not None


def test_audit_result_creation():
    fp = SourceFingerprint(
        provider="opendatasus",
        resource_id="bb1c023c-e524-48ff-8471-f68f6cdf189e",
        filename="vacinacao_out_2023_csv.zip",
    )
    res = AuditResult(
        period="2023-10",
        raw_rows=31_915_616,
        cube_rows=432_100,
        raw_doses=31_915_616,
        cube_doses=31_915_616,
        status="verified_exact",
        source_fingerprint=fp,
    )
    assert res.period == "2023-10"
    assert res.status == "verified_exact"
    assert res.raw_doses == res.cube_doses
