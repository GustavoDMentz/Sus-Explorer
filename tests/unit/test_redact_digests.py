import hashlib
import random

from sus_explorer.operational_logging import redact, sanitize_text


def test_sha256_with_eleven_consecutive_digits_is_not_treated_as_cpf():
    digest = "ec69a3f5fe637fb520108c8919f57717835231da53ffa490f6097932abe3dc8c"
    assert redact(digest) == digest
    assert redact({"source_metadata_sha256": digest}) == {"source_metadata_sha256": digest}


def test_random_sha256_digests_survive_redaction():
    # ~4% dos SHA-256 contêm 11 dígitos seguidos; semente fixa mantém o teste determinístico.
    rng = random.Random(1)
    digests = [hashlib.sha256(str(rng.random()).encode()).hexdigest() for _ in range(3000)]
    assert sum(1 for d in digests if "".join(c if c.isdigit() else " " for c in d).split() and
               max(len(x) for x in "".join(c if c.isdigit() else " " for c in d).split()) >= 11) > 50
    assert all(redact(d) == d for d in digests)


def test_cpf_is_still_redacted_alone_and_inside_text():
    assert redact("12345678901") == "[REDACTED]"
    assert redact("123.456.789-01") == "[REDACTED]"
    assert sanitize_text("paciente CPF 123.456.789-01 vacinado") == "paciente CPF [REDACTED] vacinado"


def test_cpf_next_to_a_digest_is_redacted_but_digest_is_kept():
    digest = "a" * 64
    assert sanitize_text(f"{digest} 12345678901") == f"{digest} [REDACTED]"
