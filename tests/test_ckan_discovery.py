import io
import json
from unittest.mock import patch

import pytest

from sus_explorer.data.persistence.ckan_discovery import CatalogError, compare, discover, ckan_action


class Response:
    status = 200
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.body[:size]


def test_discover_sorts_and_restricts_metadata():
    payload = {"success": True, "result": {"resources": [
        {"id": "b", "url": "https://example.org/b", "format": "ZIP", "unexpected": "private"},
        {"id": "a", "url": "https://example.org/a", "format": "CSV"},
        {"id": "invalid"},
    ]}}
    opener = lambda request, timeout: Response(json.dumps(payload).encode())
    result = discover("pni-2026", opener=opener)
    assert [r["resource_id"] for r in result] == ["a", "b"]
    assert "unexpected" not in result[1]


def test_compare_flags_revision_and_removal():
    old = {"resources": [{"resource_id": "a", "hash": "old"}, {"resource_id": "b"}]}
    new = {"resources": [{"resource_id": "a", "hash": "new"}, {"resource_id": "c"}]}
    assert compare(old, new)["metadata_changed"] == ["a"]
    assert compare(old, new)["removed"] == ["b"]
    assert compare(old, new)["added"] == ["c"]


def test_rejects_non_https_catalog():
    with pytest.raises(CatalogError):
        ckan_action("package_show", {"id": "pni"}, base="http://example.org/api/3/action")


def test_rejects_failed_catalog_response():
    opener = lambda request, timeout: Response(b'{"success": false, "error": {}}')
    with pytest.raises(CatalogError):
        discover("pni-2026", opener=opener)
