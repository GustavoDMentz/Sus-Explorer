# Fontes de dados

## Fonte analítica

O produto ativo consulta eventos públicos de vacinação do SI-PNI importados dos ZIPs mensais oficiais do OpenDataSUS. Cada ZIP é nacional; as partições servidas pelo sistema são competência mensal e UF do estabelecimento.

O catálogo oficial é descoberto sem gravar no banco:

```bash
python -m sus_explorer.data.remote.opendatasus_catalog \
  --years 2020 2021 2022 2023 2024 2025 2026 \
  --manifest audit/opendatasus-pni.json
```

Use `--write` somente após revisar as diferenças. `ETag`, tamanho e `Last-Modified` detectam possíveis republicações; SHA-256 do arquivo baixado identifica o snapshot efetivamente importado.

## Escopo semântico

Uma linha representa um evento de dose registrada, não uma pessoa única, atendimento, procedimento ambulatorial, valor financeiro ou cobertura vacinal. A geografia é do estabelecimento de vacinação. Ausência de uma competência completa significa indisponibilidade, nunca zero automático.

Os leitores R2/Parquet permanecem isolados para migração legada e auditoria. Eles não são fallback do serviço normal.

Na observação somente leitura registrada em `audit/opendatasus-pni-2026-11-25.json`, 83 competências mensais estavam listadas e os 83 ZIPs responderam HTTP 200, somando 218.287.675.742 bytes comprimidos. O maior arquivo observado tinha 7.533.194.223 bytes. Isso não comprova linhas por UF, integridade integral ou carga no PostgreSQL.
