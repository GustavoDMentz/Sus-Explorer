"""Probe official monthly SI-PNI ZIP URLs implied by the checked partition manifest."""
from __future__ import annotations

import argparse
import hashlib
import html
import concurrent.futures
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun",
          "jul", "ago", "set", "out", "nov", "dez")
BASE = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv"
PORTAL = "https://dadosabertos.saude.gov.br/dataset/doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-{year}"


def catalog_year(year: int) -> dict:
    url = PORTAL.format(year=year)
    response = requests.get(url, timeout=(5, 30))
    response.raise_for_status()
    body = html.unescape(response.text).replace("\\/", "/")
    pattern = re.compile(r"https://s3\.sa-east-1\.amazonaws\.com/ckan\.saude\.gov\.br/PNI/csv/vacinacao_([a-z]{3})_(20[0-9]{2})_csv\.zip")
    links = {}
    reverse_months = {name: i + 1 for i, name in enumerate(MONTHS)}
    for month_name, source_year in pattern.findall(body):
        month = reverse_months.get(month_name)
        if month and int(source_year) == year:
            links[(year, month)] = f"{BASE}/vacinacao_{month_name}_{year}_csv.zip"
    return {"year": year, "url": url, "status_code": response.status_code,
            "page_sha256": hashlib.sha256(response.content).hexdigest(),
            "monthly_resources": links}


def probe(item: tuple[int, int, str | None, str | None]) -> dict:
    year, month, url, catalog_page = item
    if url is None:
        return {"year": year, "month": month, "url": None,
                "catalog_page": catalog_page, "catalog_verified": False,
                "status_code": None, "content_length": None,
                "last_modified": None, "available": False,
                "availability_reason": "URL mensal não encontrada na página oficial consultada."}
    try:
        response = requests.head(url, timeout=(5, 20), allow_redirects=True)
        return {"year": year, "month": month, "url": url,
                "catalog_page": catalog_page, "catalog_verified": True,
                "status_code": response.status_code,
                "content_length": int(response.headers["Content-Length"])
                if response.headers.get("Content-Length", "").isdigit() else None,
                "last_modified": response.headers.get("Last-Modified"),
                "available": response.status_code == 200,
                "availability_reason": "URL exata listada no catálogo oficial e HEAD respondeu HTTP 200."
                if response.status_code == 200 else "URL listada no catálogo, mas não acessível no momento da checagem."}
    except requests.RequestException as exc:
        return {"year": year, "month": month, "url": url,
                "catalog_page": catalog_page, "catalog_verified": True,
                "status_code": None, "content_length": None,
                "last_modified": None, "available": False,
                "availability_reason": "Falha ao verificar URL listada no catálogo oficial.",
                "error_type": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.manifest.read_text(encoding="utf-8"))
    years = sorted({int(item["partition"][4:8]) for item in inventory["partitions"]})
    catalog_pages = {year: catalog_year(year) for year in years}
    unique = sorted({(int(item["partition"][4:8]), int(item["partition"][13:15]))
                     for item in inventory["partitions"]})
    requests_to_probe = [(year, month,
                          catalog_pages[year]["monthly_resources"].get((year, month)),
                          catalog_pages[year]["url"]) for year, month in unique]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        resources = sorted(pool.map(probe, requests_to_probe), key=lambda row: (row["year"], row["month"]))
    by_period = {(row["year"], row["month"]): row for row in resources}
    partitions = []
    for item in inventory["partitions"]:
        label = item["partition"]
        year, month, uf = int(label[4:8]), int(label[13:15]), label[-2:]
        resource = by_period[(year, month)]
        partitions.append({"partition": label,
                           "official_month_catalog_verified": resource["catalog_verified"],
                           "official_month_resource_available": resource["available"],
                           "official_month_url": resource["url"],
                           "records_in_uf": None,
                           "records_in_uf_reason": "Not counted; only URL availability was probed."})
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "catalog_resource_example": "https://dadosabertos.saude.gov.br/dataset/doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-2026/resource/7a23edf5-0315-48f6-88a3-015ba3ac51af",
        "inventory_source": inventory.get("source"),
        "catalog_pages": [{key: value for key, value in page.items() if key != "monthly_resources"}
                          for page in catalog_pages.values()],
        "partition_count": len(partitions),
        "resource_summary": {"months_probed": len(resources),
                             "available": sum(row["available"] for row in resources),
                             "unavailable": sum(not row["available"] for row in resources),
                             "compressed_bytes_available": sum(row["content_length"] or 0 for row in resources if row["available"])},
        "monthly_resources": resources,
        "partitions": partitions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["resource_summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
