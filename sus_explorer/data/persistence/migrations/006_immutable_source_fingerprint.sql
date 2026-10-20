-- Preserve integrity of historical source fingerprints.
-- Migration 005 remains immutable; do not alter existing migration checksums.
REVOKE UPDATE (source_fingerprint) ON analytical_result_versions
    FROM sus_explorer_runtime;
-- Only last_seen_at and observations remain updateable by runtime.
-- This does not defend against compromised owner/migrator credentials.
