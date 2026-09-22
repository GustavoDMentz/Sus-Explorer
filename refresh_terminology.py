from sus_explorer.terminology import terminology

p = terminology.load(force_refresh=True)

print("Fonte:", p["source"])
print("MS versão:", p["ms"].get("version"))
print("MS conceitos:", p["ms"].get("concept_count"))
print("SES-GO versão:", p["ses_go"].get("version"))
print("SES-GO conceitos:", p["ses_go"].get("concept_count"))
print("Definições enriquecidas:", p["definitions_enriched"])
print("Conflitos:", p["conflicts"])

for code in ("33", "77", "9", "22", "104"):
    print(code, "->", p["concepts"].get(code))

print("Cache atualizado:", terminology.cache_file)
