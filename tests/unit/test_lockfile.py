"""requirements-lock.txt must agree with the human-edited requirement files."""
import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).parents[2]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\;]+)")


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock():
    pins, hashes, current = {}, {}, None
    for line in (ROOT / "requirements-lock.txt").read_text("utf-8").splitlines():
        match = PIN.match(line)
        if match:
            current = normalize(match.group(1))
            pins[current] = match.group(2)
            hashes[current] = 0
        elif line.strip().startswith("--hash=sha256:") and current:
            hashes[current] += 1
    return pins, hashes


def requirements(path):
    for raw in (ROOT / path).read_text("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith(("-r", "-c", "--")):
            yield Requirement(line)


PINS, HASHES = parse_lock()


def test_every_locked_package_is_pinned_exactly_and_has_hashes():
    assert PINS, "lock vazio"
    for name in PINS:
        assert HASHES[name] >= 1, f"{name} sem hash"


def test_lock_does_not_redirect_the_package_index():
    text = (ROOT / "requirements-lock.txt").read_text("utf-8")
    assert "--index-url" not in text and "--extra-index-url" not in text and "--find-links" not in text


@pytest.mark.parametrize("path", ["requirements.txt", "requirements-migration.txt", "requirements-dev.txt"])
def test_direct_requirements_are_locked_inside_their_ranges(path):
    for requirement in requirements(path):
        name = normalize(requirement.name)
        assert name in PINS, f"{requirement.name} ({path}) não está no lock"
        assert Version(PINS[name]) in requirement.specifier, (
            f"{requirement.name}=={PINS[name]} no lock viola {requirement.specifier} de {path}")


def test_constraint_pins_equal_the_locked_versions():
    for requirement in requirements("constraints.txt"):
        name = normalize(requirement.name)
        pinned = next(iter(requirement.specifier)).version
        assert PINS.get(name) == pinned, f"{requirement.name}: constraints {pinned} x lock {PINS.get(name)}"


def test_ci_installs_the_lock_with_hash_verification():
    workflow = (ROOT / ".github/workflows/test-postgres.yml").read_text("utf-8")
    assert "--require-hashes -r requirements-lock.txt" in workflow
