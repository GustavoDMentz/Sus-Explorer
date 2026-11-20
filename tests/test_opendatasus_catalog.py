import json
import urllib.error
from pathlib import Path

import pytest

from sus_explorer.data.remote import opendatasus_catalog as cat

FIXTURE = Path(__file__).parent / "fixtures" / "opendatasus_pni_2026_excerpt.html"
GOOD = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_jan_2026_csv.zip"


class Response:
    def __init__(self, body=b"", status=200, headers=None):
        self.body, self.status, self.headers = body, status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body[:size] if size >= 0 else self.body


def page():
    return FIXTURE.read_text("utf-8")


def test_competence_from_url():
    assert cat.competence_from_url(GOOD) == (2026, 1)
    assert cat.competence_from_url(GOOD.replace("jan", "out")) == (2026, 10)
    assert cat.competence_from_url(GOOD.replace("_csv", "_json")) is None
    assert cat.competence_from_url(GOOD.replace("jan", "xxx")) is None


def test_extract_uses_only_monthly_csv_zips_and_url_for_month():
    entries = cat.extract_resources(page(), 2026)
    assert [(e["year"], e["month"]) for e in entries] == [(2026, 1), (2026, 6), (2026, 9), (2026, 10), (2026, 11)]
    jan = entries[0]
    assert jan["resource_id"] == "7a23edf5-0315-48f6-88a3-015ba3ac51af"
    assert jan["listed_last_modified"] == "2026-11-08T18:47:22.936957"
    # "Out 2026" tem nome abreviado: o mês vem do nome do arquivo, não do título
    assert entries[3]["listed_last_modified"] is None


def test_extract_ignores_other_years_and_foreign_hosts():
    data = {"props": {"pageProps": {"resources": [
        {"id": "a", "url": GOOD.replace("2026", "2025")},
        {"id": "b", "url": "https://evil.example/ckan.saude.gov.br/PNI/csv/vacinacao_jan_2026_csv.zip"},
        {"id": "c", "url": GOOD},
    ]}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    assert [e["resource_id"] for e in cat.extract_resources(html, 2026)] == ["c"]


def test_extract_falls_back_to_html_links():
    entries = cat.extract_resources(f'<a href="{GOOD}">x</a>', 2026)
    assert entries[0]["resource_id"] is None and entries[0]["month"] == 1


def test_extract_fails_loudly_when_structure_changes():
    with pytest.raises(cat.CatalogError):
        cat.extract_resources("<html><body>Nova página sem dados</body></html>", 2026)


def test_probe_available_and_unavailable():
    entry = {"year": 2026, "month": 1, "url": GOOD}
    ok = cat.probe(entry, opener=lambda r, timeout: Response(headers={
        "Content-Length": "123", "Last-Modified": "Sun, 08 Nov 2026 18:00:00 GMT", "ETag": '"x"'}))
    assert (ok["state"], ok["content_length"], ok["etag"]) == (cat.STATE_AVAILABLE, 123, '"x"')

    def missing(request, timeout):
        raise urllib.error.HTTPError(GOOD, 404, "nf", {}, None)
    gone = cat.probe(entry, opener=missing)
    assert gone["state"] == cat.STATE_LISTED_UNAVAILABLE and gone["http_status"] == 404

    def down(request, timeout):
        raise urllib.error.URLError("sem rede")
    assert cat.probe(entry, opener=down)["http_status"] is None


def test_probe_refuses_foreign_host():
    with pytest.raises(cat.CatalogError):
        cat.probe({"url": "https://example.org/x.zip"})


def test_discover_records_failed_year_without_inventing_removals():
    def pages(request, timeout):
        if "2025" in request.full_url:
            raise urllib.error.URLError("fora do ar")
        return Response(page().encode())
    current = cat.discover([2025, 2026], check_files=False, page_opener=pages)
    assert "2025" in current["errors"] and len(current["competences"]) == 5

    previous = {"competences": [{"year": 2025, "month": 12, "url": "u"}]}
    changes = cat.compare(previous, current)
    assert changes["removed"] == []          # erro de consulta não é remoção
    assert changes["skipped_years"] == ["2025"]


def test_compare_flags_added_removed_changed_unavailable():
    def item(m, **kw):
        return {"year": 2026, "month": m, "resource_id": "r", "url": "u",
                "content_length": 1, "last_modified": "a", "etag": "e",
                "state": cat.STATE_AVAILABLE, "listed_last_modified": None, **kw}
    old = {"competences": [item(1), item(2), item(3)]}
    new = {"errors": {}, "files_checked": True,
           "competences": [item(1), item(2, etag="novo"), item(4, state=cat.STATE_LISTED_UNAVAILABLE)]}
    result = cat.compare(old, new)
    assert result["added"] == ["2026-04"]
    assert result["removed"] == ["2026-03"]
    assert result["changed"] == {"2026-02": {"etag": ["e", "novo"]}}
    assert result["unchanged"] == ["2026-01"]
    assert result["unavailable"] == ["2026-04"]


def test_cli_refuses_to_write_when_a_year_failed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cat, "discover", lambda years, check_files=True: {
        "errors": {"2026": "x"}, "competences": [], "files_checked": True})
    manifest = tmp_path / "m.json"
    assert cat.main(["--years", "2026", "--manifest", str(manifest), "--write"]) == 2
    assert not manifest.exists()


@pytest.mark.parametrize("url", [
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/../../outro-bucket/vacinacao_jan_2026_csv.zip",
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/%2e%2e/vacinacao_jan_2026_csv.zip",
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_jan_2026_csv.zip?x=1",
    "https://s3.sa-east-1.amazonaws.com:8443/ckan.saude.gov.br/PNI/csv/vacinacao_jan_2026_csv.zip",
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/sub/vacinacao_jan_2026_csv.zip",
])
def test_data_url_must_match_the_exact_official_path(url):
    with pytest.raises(cat.CatalogError):
        cat._check_url(url, cat.DATA_HOST, cat.DATA_PATH_PATTERN)
    if "?" in url:
        return  # o link do HTML sem query é aceito normalmente; só a URL com query é recusada acima
    data = {"props": {"pageProps": {"resources": [{"id": "x", "url": url}]}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    with pytest.raises(cat.CatalogError):      # nenhum ZIP válido: falha estrutural
        cat.extract_resources(html, 2026)


def test_official_data_url_is_accepted():
    cat._check_url(GOOD, cat.DATA_HOST, cat.DATA_PATH_PATTERN)
