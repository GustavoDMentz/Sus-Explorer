"""Refresh the local FHIR terminology cache explicitly."""

from sus_explorer.terminology import terminology


def main() -> None:
    payload = terminology.load(force_refresh=True)
    print("Fonte:", payload["source"])
    print("MS versão:", payload["ms"].get("version"))
    print("MS conceitos:", payload["ms"].get("concept_count"))
    print("SES-GO versão:", payload["ses_go"].get("version"))
    print("SES-GO conceitos:", payload["ses_go"].get("concept_count"))
    print("Definições enriquecidas:", payload["definitions_enriched"])
    print("Conflitos:", payload["conflicts"])
    for code in ("33", "77", "9", "22", "104"):
        print(code, "->", payload["concepts"].get(code))
    print("Cache atualizado:", terminology.cache_file)


if __name__ == "__main__":
    main()
