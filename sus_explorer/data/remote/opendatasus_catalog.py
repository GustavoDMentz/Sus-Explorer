"""Descoberta somente leitura dos ZIPs mensais do SI-PNI no OpenDataSUS.

O portal oficial deixou de expor a API CKAN (``/api/3/action`` responde 404).
A descoberta agora combina duas fontes:

1. a página pública de cada dataset anual, cujo JSON embutido (``__NEXT_DATA__``)
   lista os recursos, com a competência (ano/mês) derivada do nome do arquivo;
2. um ``HEAD`` em cada ZIP no S3 oficial, que informa ``Content-Length``,
   ``Last-Modified`` e ``ETag``.

Este módulo não baixa ZIPs, não escreve em PostgreSQL e não promove versões.
Metadados e ETag são indícios de mudança, não prova de identidade de conteúdo:
só o SHA-256 do arquivo baixado (etapa futura) confirma.

Uma competência ausente do catálogo nunca é tratada como zero doses.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

PORTAL_HOST = "dadosabertos.saude.gov.br"
DATA_HOST = "s3.sa-east-1.amazonaws.com"
# Full-path patterns, not prefixes: a prefix check let "../" and "%2e%2e" segments
# walk out of the official folder while still passing the allowlist.
DATA_PATH_PATTERN = re.compile(
    r"/ckan\.saude\.gov\.br/PNI/csv/vacinacao_[a-z]{3}_\d{4}_csv\.zip"
)
PORTAL_PATH_PATTERN = re.compile(r"/dataset/[a-z0-9-]{1,200}")
DATASET_URL = (
    f"https://{PORTAL_HOST}/dataset/"
    "doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-{year}"
)

MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun",
          "jul", "ago", "set", "out", "nov", "dez")
_MONTH_NUMBER = {name: i + 1 for i, name in enumerate(MONTHS)}
_ZIP_NAME = re.compile(r"^vacinacao_([a-z]{3})_(\d{4})_csv\.zip$")
_NEXT_DATA = re.compile(
    r'<script[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_ZIP_LINK = re.compile(
    r"https://s3\.sa-east-1\.amazonaws\.com/ckan\.saude\.gov\.br/PNI/csv/"
    r"vacinacao_[a-z]{3}_\d{4}_csv\.zip")

MAX_PAGE_BYTES = 5_000_000
TIMEOUT_SECONDS = 30
USER_AGENT = "sus-explorer-catalog/1.0"

STATE_AVAILABLE = "available"
STATE_LISTED_UNAVAILABLE = "listed_unavailable"


class CatalogError(RuntimeError):
    """Falha ao consultar ou interpretar o catálogo."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_default_opener = urllib.request.build_opener(_NoRedirect)


def _default_open(request, timeout):
    return _default_opener.open(request, timeout=timeout)


Opener = Callable[..., object]


def _check_url(url: str, host: str, path_pattern: re.Pattern) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != host
            or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)
            or not path_pattern.fullmatch(parsed.path)):
        raise CatalogError("URL fora da lista de origens oficiais permitidas")


def competence_from_url(url: str) -> tuple[int, int] | None:
    """Extrai (ano, mês) de ``.../vacinacao_<mes>_<ano>_csv.zip``."""
    match = _ZIP_NAME.match(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
    if not match or match.group(1) not in _MONTH_NUMBER:
        return None
    return int(match.group(2)), _MONTH_NUMBER[match.group(1)]


def fetch_dataset_page(year: int, *, opener: Opener | None = None) -> str:
    if not 2000 <= year <= 2100:
        raise ValueError("Ano inválido")
    url = DATASET_URL.format(year=year)
    _check_url(url, PORTAL_HOST, PORTAL_PATH_PATTERN)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with (opener or _default_open)(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise CatalogError(f"Página do dataset {year}: HTTP {response.status}")
            body = response.read(MAX_PAGE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise CatalogError(f"Página do dataset {year}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CatalogError(f"Página do dataset {year} inacessível") from exc
    if len(body) > MAX_PAGE_BYTES:
        raise CatalogError("Página do dataset grande demais")
    return body.decode("utf-8", errors="replace")


def extract_resources(page: str, year: int) -> list[dict]:
    """Lista os ZIPs CSV mensais de ``year`` presentes na página.

    Usa o JSON embutido; se ele sumir, recorre aos links ``.zip`` do HTML.
    Se nenhum recurso for encontrado, falha: isso indica mudança estrutural do
    portal e jamais deve virar "todas as competências removidas".
    """
    entries: dict[tuple[int, int], dict] = {}
    match = _NEXT_DATA.search(page)
    if match:
        try:
            props = json.loads(match.group(1))["props"]["pageProps"]
            raw = props["resources"]
        except (ValueError, KeyError, TypeError):
            raw = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            _add(entries, item["url"], year, item.get("id"), item.get("name"),
                 item.get("last_modified"))
    if not entries:  # contingência: links no HTML, sem resource_id
        for link in _ZIP_LINK.findall(html_lib.unescape(page).replace("\\/", "/")):
            _add(entries, link, year, None, None, None)
    if not entries:
        raise CatalogError(
            f"Nenhum ZIP mensal encontrado na página de {year}; "
            "a estrutura do portal pode ter mudado")
    return [entries[key] for key in sorted(entries)]


def _add(entries, url, year, resource_id, name, listed_last_modified) -> None:
    competence = competence_from_url(url)
    if competence is None or competence[0] != year:
        return
    try:
        _check_url(url, DATA_HOST, DATA_PATH_PATTERN)
    except CatalogError:
        return
    entries[competence] = {
        "year": competence[0],
        "month": competence[1],
        "resource_id": resource_id if isinstance(resource_id, str) else None,
        "name": name if isinstance(name, str) else None,
        "url": url,
        "listed_last_modified": listed_last_modified
        if isinstance(listed_last_modified, str) else None,
    }


def probe(entry: dict, *, opener: Opener | None = None) -> dict:
    """``HEAD`` no ZIP; acrescenta estado e cabeçalhos observados."""
    _check_url(entry["url"], DATA_HOST, DATA_PATH_PATTERN)
    request = urllib.request.Request(
        entry["url"], method="HEAD", headers={"User-Agent": USER_AGENT})
    result = dict(entry, content_length=None, last_modified=None, etag=None,
                  http_status=None, state=STATE_LISTED_UNAVAILABLE)
    try:
        with (opener or _default_open)(request, timeout=TIMEOUT_SECONDS) as response:
            result["http_status"] = response.status
            headers = response.headers
    except urllib.error.HTTPError as exc:
        result["http_status"] = exc.code
        return result
    except (urllib.error.URLError, TimeoutError, OSError):
        return result
    length = headers.get("Content-Length", "")
    result["content_length"] = int(length) if length.isdigit() else None
    result["last_modified"] = headers.get("Last-Modified")
    result["etag"] = headers.get("ETag")
    if result["http_status"] == 200:
        result["state"] = STATE_AVAILABLE
    return result


def discover(years: list[int], *, check_files: bool = True,
             page_opener: Opener | None = None,
             head_opener: Opener | None = None) -> dict:
    """Monta o manifesto. Anos cuja página falhou vão em ``errors``."""
    competences: list[dict] = []
    errors: dict[str, str] = {}
    for year in sorted(set(years)):
        try:
            entries = extract_resources(fetch_dataset_page(year, opener=page_opener), year)
        except CatalogError as exc:
            errors[str(year)] = str(exc)
            continue
        competences.extend(probe(e, opener=head_opener) if check_files else e
                           for e in entries)
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "portal": f"https://{PORTAL_HOST}",
        "years_requested": sorted(set(years)),
        "files_checked": check_files,
        "errors": errors,
        "competences": competences,
    }


_COMPARED = ("resource_id", "url", "content_length", "last_modified", "etag",
             "state", "listed_last_modified")


def _key(item: dict) -> str:
    return f"{item['year']:04d}-{item['month']:02d}"


def compare(previous: dict | None, current: dict) -> dict:
    """Diferenças entre manifestos.

    Competências de anos que falharam na consulta atual não entram em
    ``removed``: erro de consulta não é remoção.
    """
    failed = set(current.get("errors", {}))
    old = {_key(i): i for i in (previous or {}).get("competences", [])}
    new = {_key(i): i for i in current["competences"]}
    removed = sorted(k for k in set(old) - set(new) if k[:4] not in failed)
    changed = {}
    for key in sorted(set(old) & set(new)):
        diff = {f: [old[key].get(f), new[key].get(f)] for f in _COMPARED
                if old[key].get(f) != new[key].get(f)
                and not (current.get("files_checked") is False
                         and f in ("content_length", "last_modified", "etag", "state"))}
        if diff:
            changed[key] = diff
    return {
        "added": sorted(set(new) - set(old)),
        "removed": removed,
        "changed": changed,
        "unchanged": sorted(k for k in set(old) & set(new) if k not in changed),
        "unavailable": sorted(k for k, v in new.items()
                              if v.get("state") == STATE_LISTED_UNAVAILABLE),
        "skipped_years": sorted(failed),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Descoberta somente leitura dos ZIPs mensais SI-PNI (OpenDataSUS)")
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--no-head", action="store_true",
                        help="não consulta os ZIPs; usa só o catálogo do portal")
    parser.add_argument("--write", action="store_true",
                        help="grava o manifesto depois de conferir as diferenças")
    args = parser.parse_args(argv)
    previous = (json.loads(args.manifest.read_text("utf-8"))
                if args.manifest.exists() else None)
    current = discover(args.years, check_files=not args.no_head)
    changes = compare(previous, current)
    print(json.dumps({"errors": current["errors"], "changes": changes},
                     ensure_ascii=False, indent=2))
    if current["errors"] and args.write:
        print("Recusando gravar: houve anos com erro de consulta.")
        return 2
    if args.write:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.manifest.with_suffix(args.manifest.suffix + ".tmp")
        temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", "utf-8")
        temporary.replace(args.manifest)
    return 1 if current["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
