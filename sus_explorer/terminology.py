
from __future__ import annotations

import json
import time
import unicodedata
from pathlib import Path

import requests


MS_VALUESET_URL = (
    "https://terminologia.saude.gov.br/fhir/"
    "ValueSet-BRImunobiologico.json"
)
MS_SYSTEM = (
    "https://terminologia.saude.gov.br/fhir/"
    "CodeSystem/BRImunobiologico"
)

GO_CODESYSTEM_URL = (
    "https://fhir.saude.go.gov.br/r4/reds-go/"
    "CodeSystem-BRImunobiologico.json"
)

CACHE_DIR = Path.home() / ".cache" / "sus_explorer"
CACHE_FILE = CACHE_DIR / "BRImunobiologico_ms_go.json"
CACHE_TTL_SECONDS = 7 * 24 * 3600


def _norm(text: str | None) -> str | None:
    """Normalização só para comparar displays, não para exibir."""
    if text is None:
        return None
    value = unicodedata.normalize("NFKC", str(text))
    return " ".join(value.strip().casefold().split())


def _request_json(url: str) -> dict:
    r = requests.get(
        url,
        timeout=30,
        headers={"Accept": "application/fhir+json, application/json"},
    )
    r.raise_for_status()
    return r.json()


def _flatten_go_concepts(items: list[dict]) -> list[dict]:
    """FHIR CodeSystem pode ter conceitos aninhados."""
    out = []
    for item in items:
        out.append(item)
        children = item.get("concept", [])
        if children:
            out.extend(_flatten_go_concepts(children))
    return out


class ImmunobiologicalTerminology:
    """
    Merge com proveniência explícita:

    - Ministério da Saúde:
        autoridade para code + official_display.
    - SES-GO:
        fornece definition quando o mesmo code/display é compatível.
    - Em conflito:
        definition = None e conflict = True.
    """

    def __init__(self, cache_file: Path = CACHE_FILE):
        self.cache_file = cache_file
        self._payload: dict | None = None

    def _cache_is_fresh(self) -> bool:
        if not self.cache_file.exists():
            return False
        return (
            time.time() - self.cache_file.stat().st_mtime
            < CACHE_TTL_SECONDS
        )

    def _load_ms(self) -> tuple[dict, dict[str, dict]]:
        resource = _request_json(MS_VALUESET_URL)

        concepts: dict[str, dict] = {}

        # A expansão do ValueSet nacional é a fonte preferida.
        for item in resource.get("expansion", {}).get("contains", []):
            if item.get("system") == MS_SYSTEM and item.get("code"):
                concepts[str(item["code"])] = {
                    "code": str(item["code"]),
                    "display": item.get("display"),
                }

        # Fallback caso a expansão futura venha ausente.
        if not concepts:
            for include in resource.get("compose", {}).get("include", []):
                if include.get("system") != MS_SYSTEM:
                    continue
                for item in include.get("concept", []):
                    if item.get("code"):
                        concepts[str(item["code"])] = {
                            "code": str(item["code"]),
                            "display": item.get("display"),
                        }

        meta = {
            "url": resource.get("url"),
            "version": resource.get("version"),
            "status": resource.get("status"),
            "concept_count": len(concepts),
        }
        return meta, concepts

    def _load_go(self) -> tuple[dict, dict[str, dict]]:
        resource = _request_json(GO_CODESYSTEM_URL)

        concepts: dict[str, dict] = {}
        for item in _flatten_go_concepts(resource.get("concept", [])):
            if not item.get("code"):
                continue

            code = str(item["code"])
            concepts[code] = {
                "code": code,
                "display": item.get("display"),
                "definition": item.get("definition"),
            }

        meta = {
            "url": resource.get("url"),
            "version": resource.get("version"),
            "status": resource.get("status"),
            "concept_count": len(concepts),
        }
        return meta, concepts

    def _download_and_merge(self) -> dict:
        ms_meta, ms = self._load_ms()
        go_meta, go = self._load_go()

        merged: dict[str, dict] = {}
        conflicts = 0
        enriched = 0

        # MS define o universo canônico.
        for code, ms_item in ms.items():
            ms_display = ms_item.get("display")
            go_item = go.get(code)

            definition = None
            definition_source = None
            conflict = False
            conflict_detail = None

            if go_item:
                go_display = go_item.get("display")
                go_definition = go_item.get("definition")

                # Aceita a definição de GO apenas se o display oficial
                # do mesmo código for compatível.
                displays_match = (
                    _norm(ms_display) == _norm(go_display)
                    if ms_display is not None and go_display is not None
                    else False
                )

                if displays_match:
                    definition = go_definition
                    if definition:
                        enriched += 1
                        definition_source = (
                            "SES-GO / BRImunobiologico"
                        )
                else:
                    conflict = True
                    conflicts += 1
                    conflict_detail = {
                        "ms_display": ms_display,
                        "go_display": go_display,
                    }

            merged[code] = {
                "code": code,
                "official_display": ms_display,
                "definition": definition,
                "definition_source": definition_source,
                "conflict": conflict,
                "conflict_detail": conflict_detail,
            }

        payload = {
            "source": "MS + SES-GO",
            "retrieved_at_unix": time.time(),
            "ms": {
                "role": "canonical_code_display",
                **ms_meta,
                "endpoint": MS_VALUESET_URL,
                "canonical_system": MS_SYSTEM,
            },
            "ses_go": {
                "role": "definition_enrichment",
                **go_meta,
                "endpoint": GO_CODESYSTEM_URL,
            },
            "merged_concept_count": len(merged),
            "definitions_enriched": enriched,
            "conflicts": conflicts,
            "concepts": merged,
        }

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def load(self, force_refresh: bool = False) -> dict:
        if self._payload is not None and not force_refresh:
            return self._payload

        if not force_refresh and self._cache_is_fresh():
            self._payload = json.loads(
                self.cache_file.read_text(encoding="utf-8")
            )
            return self._payload

        try:
            self._payload = self._download_and_merge()
        except Exception:
            # Fallback para cache velho; nunca inventa terminologia.
            if not self.cache_file.exists():
                raise
            self._payload = json.loads(
                self.cache_file.read_text(encoding="utf-8")
            )

        return self._payload

    def lookup(self, code: str | None) -> dict | None:
        if code is None:
            return None
        return self.load()["concepts"].get(str(code))

    def resolve_text(self, text: str) -> list[str]:
        """Resolve public codes using canonical labels and non-conflicting definitions.

        No guessed codes or acronym expansion. Short queries match labels exactly
        to avoid incidental substrings in full definitions.
        """
        def normalize(value):
            value = unicodedata.normalize("NFKD", str(value or ""))
            return " ".join("".join(c for c in value if not unicodedata.combining(c)).casefold().split())
        term = normalize(text)
        if not term:
            return []
        codes = []
        for code, concept in self.load()["concepts"].items():
            label = normalize(concept.get("official_display"))
            definition = normalize(concept.get("definition")) if not concept.get("conflict") else ""
            if label == term or (len(term) >= 4 and (term in label or term in definition)):
                codes.append(str(code))
        return sorted(set(codes))

    def metadata(self) -> dict:
        p = self.load()
        return {
            "source": p["source"],
            "merged_concept_count": p["merged_concept_count"],
            "definitions_enriched": p["definitions_enriched"],
            "conflicts": p["conflicts"],
            "ms": p["ms"],
            "ses_go": p["ses_go"],
        }


terminology = ImmunobiologicalTerminology()
