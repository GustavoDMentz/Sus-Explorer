"""Temporal provenance preserves only validated metadata fingerprints."""
import pytest

from sus_explorer.analytics.temporal_query import safe_source_provenance
from sus_explorer.data.persistence.result_versions import _fingerprint
from types import SimpleNamespace


def test_valid_fingerprint_survives_temporal_sanitization_and_history():
    digest = "a" * 64
    source = {
        "source": "SI-PNI / healthbr-data / OpenDATASUS",
        "uf_partition": "RS",
        "source_metadata_sha256": digest,
        "microdata_sent_to_llm": False,
        "untrusted_extra": "must not survive",
    }
    safe = safe_source_provenance(source)
    assert safe["source_metadata_sha256"] == digest
    assert "untrusted_extra" not in safe
    result = SimpleNamespace(provenance={"source_provenance": safe})
    assert _fingerprint(result) == digest


@pytest.mark.parametrize("bad", [
    "abc", "A" * 64, "g" * 64, "a" * 63, 42, ["a" * 64],
])
def test_invalid_fingerprint_rejected(bad):
    with pytest.raises(ValueError, match="fingerprint"):
        safe_source_provenance({"source_metadata_sha256": bad})


def test_absent_fingerprint_stays_absent():
    assert "source_metadata_sha256" not in safe_source_provenance({})
