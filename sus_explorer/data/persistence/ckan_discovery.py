"""Conservative CKAN resource discovery and manifest generation.

This module does not mutate PostgreSQL or download files. Use it to verify
the official catalog before wiring resource URLs to ingest_csv.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CKAN_BASE = "https://dadosabertos.saude.gov.br/api/3/action"
MAX_RESPONSE_BYTES = 8_000_000


class CatalogError(RuntimeError):
    pass


def _endpoint(base: str, action: str) -> str:
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        raise CatalogError("CKAN base URL must be HTTPS with no credentials")
    if action not in {"package_show", "package_search"}:
        raise CatalogError("Unsupported CKAN action")
    return base.rstrip("/") + "/" + action


def ckan_action(action: str, params: dict[str, str], *, base: str = DEFAULT_CKAN_BASE,
                opener=None) -> dict:
    url = _endpoint(base, action) + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "sus-explorer-catalog-sync/1.0"
    })
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=30) as response:
            if response.status != 200:
                raise CatalogError(f"Catalog HTTP status {response.status}")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CatalogError("Could not reach CKAN catalog") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise CatalogError("CKAN response too large")
    try:
        document = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CatalogError("Invalid CKAN JSON") from exc
    if not isinstance(document, dict) or document.get("success") is not True or not isinstance(document.get("result"), dict):
        raise CatalogError("Unexpected CKAN response")
    return document["result"]


def discover(dataset: str, *, base: str = DEFAULT_CKAN_BASE, opener=None) -> list[dict]:
    if not dataset or len(dataset) > 200:
        raise ValueError("Invalid dataset identifier")
    result = ckan_action("package_show", {"id": dataset}, base=base, opener=opener)
    resources = result.get("resources")
    if not isinstance(resources, list):
        raise CatalogError("Dataset has no resource list")
    entries = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        resource_id = resource.get("id")
        url = resource.get("url")
        if not isinstance(resource_id, str) or not resource_id or not isinstance(url, str):
            continue
        # URLs are discovery metadata only; this module never fetches them.
        entries.append({
            "resource_id": resource_id,
            "name": resource.get("name"),
            "url": url,
            "format": resource.get("format"),
            "created": resource.get("created"),
            "last_modified": resource.get("last_modified"),
            "size": resource.get("size"),
            "hash": resource.get("hash"),
        })
    return sorted(entries, key=lambda item: item["resource_id"])


def compare(previous: dict | None, current: dict) -> dict:
    old = {item["resource_id"]: item for item in (previous or {}).get("resources", [])}
    new = {item["resource_id"]: item for item in current["resources"]}
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "metadata_changed": sorted(k for k in set(old) & set(new) if old[k] != new[k]),
        "unchanged": sorted(k for k in set(old) & set(new) if old[k] == new[k]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only OpenDataSUS CKAN discovery")
    parser.add_argument("--dataset", required=True, help="Official CKAN dataset ID or slug")
    parser.add_argument("--base-url", default=os.getenv("OPENDATASUS_CKAN_BASE", DEFAULT_CKAN_BASE))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="Persist the manifest after reviewing changes")
    args = parser.parse_args(argv)
    prior = json.loads(args.manifest.read_text("utf-8")) if args.manifest.exists() else None
    current = {
        "dataset": args.dataset,
        "catalog": args.base_url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "resources": discover(args.dataset, base=args.base_url),
    }
    changes = compare(prior, current)
    print(json.dumps({"changes": changes, "resources": current["resources"]}, ensure_ascii=False, indent=2))
    if args.write:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.manifest.with_suffix(args.manifest.suffix + ".tmp")
        temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", "utf-8")
        temporary.replace(args.manifest)


if __name__ == "__main__":
    main()
