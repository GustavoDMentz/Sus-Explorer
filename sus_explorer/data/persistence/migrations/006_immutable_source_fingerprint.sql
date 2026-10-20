-- Limit damage from a compromised runtime database credential.
-- Existing analytical source fingerprints must not be rewritten after insertion.
-- The original 005 migration is immutable and MUST NOT be edited.
REVOKE UPDATE (source_fingerprint) ON analytical_result_versions
    FROM sus_explorer_runtime;

-- The application only updates last_seen_at and observations on deduplication.
-- Retain these narrow privileges for compatibility with observe_result().
-- This migration does not make a compromised runtime or application process
-- trustworthy: it can still INSERT new snapshots, and last_seen_at/observations
-- remain mutable. A separate trust domain is needed for stronger attestation.
