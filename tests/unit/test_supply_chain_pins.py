"""Container images must be pinned by digest, and CI must not keep the token."""
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
IMAGE = re.compile(r"^\s*image:\s*(\S+)\s*$", re.M)
DIGEST = re.compile(r"^[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}$")


def images(path):
    return IMAGE.findall((ROOT / path).read_text("utf-8"))


def test_compose_images_are_pinned_by_digest():
    found = images("compose.yaml")
    assert found, "nenhuma imagem encontrada"
    for image in found:
        assert DIGEST.match(image), f"imagem sem digest: {image}"
        assert not image.split("@")[0].endswith(":latest")


def test_ci_service_images_are_pinned_by_digest():
    for image in images(".github/workflows/test-postgres.yml"):
        assert DIGEST.match(image), f"imagem sem digest: {image}"


def test_all_pinned_images_agree_between_compose_and_ci():
    pgvector = {i for f in ("compose.yaml", ".github/workflows/test-postgres.yml")
                for i in images(f) if i.startswith("pgvector/")}
    assert len(pgvector) == 1, "compose e CI devem usar a mesma imagem do PostgreSQL"


def test_checkout_does_not_persist_credentials():
    workflow = (ROOT / ".github/workflows/test-postgres.yml").read_text("utf-8")
    assert "persist-credentials: false" in workflow


def test_dependabot_covers_compose_images():
    assert "docker-compose" in (ROOT / ".github/dependabot.yml").read_text("utf-8")
