"""Test levels are assigned by directory without importing application modules."""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "e2e" in item.path.parts:
            item.add_marker(pytest.mark.external)
        elif "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)
