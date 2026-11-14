# Descoberta de ZIPs mensais do OpenDataSUS (fase 1)

Esta fase é **somente descoberta**. Ela não baixa ZIPs, não escreve em PostgreSQL, não agenda tarefas e não promove versões.

## Por que não CKAN

Em 2026-11-14 `https://dadosabertos.saude.gov.br/api/3/action/*` responde 404: o portal é um frontend Next.js que consulta o CKAN no servidor e não expõe a API ao público. A descoberta usa duas fontes:

1. **Página do dataset anual** (`.../dataset/doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-AAAA`). O JSON embutido (`__NEXT_DATA__`) lista os recursos; se ele desaparecer, há contingência por links `.zip` no HTML. A competência vem do **nome do arquivo** (`vacinacao_<mes>_<ano>_csv.zip`), não do título, porque os títulos variam ("Janeiro 2026", "Out 2026").
2. **`HEAD` no ZIP** (`s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/`), que informa `Content-Length`, `Last-Modified` e `ETag`. O portal devolve `hash` vazio e `size` nulo, então esses cabeçalhos são os metadados úteis.

## Uso

```bash
python -m sus_explorer.data.remote.opendatasus_catalog \
  --years 2025 2026 --manifest audit/opendatasus-pni.json
```

Sem `--write`, apenas imprime as diferenças. Com `--write`, grava o manifesto de forma atômica, e só se **nenhum ano** falhou. `--no-head` usa só o catálogo, sem consultar os ZIPs.

Estados por competência: `available` (HEAD 200) e `listed_unavailable` (listada, mas o HEAD não respondeu 200; hoje out e nov/2026 respondem 403).
A comparação devolve `added`, `removed`, `changed` (com os campos antes/depois), `unchanged`, `unavailable` e `skipped_years`.

## Garantias

- Somente HTTPS e somente os hosts `dadosabertos.saude.gov.br` e `s3.sa-east-1.amazonaws.com` (sem redirecionamentos); timeout de 30 s e limite de 5 MB por página.
- Página sem nenhum ZIP mensal é **erro**, não "tudo removido": uma mudança do portal não pode apagar o manifesto.
- Ano cuja consulta falhou entra em `skipped_years`; suas competências nunca são reportadas como `removed`.
- Competência ausente nunca é tratada como zero doses.

## Limites e próximas fases

`ETag`, `Last-Modified` e tamanho são indícios de mudança, não prova de conteúdo. Fases seguintes, cada uma em PR próprio: plano de sincronização a partir do manifesto; download com staging, retomada por `Range` e SHA-256; ingestão multi-UF em uma só leitura do ZIP com troca atômica da partição; lock, retries, auditoria e agendador.

Os testes usam um trecho real da página de 2026 (`tests/fixtures/opendatasus_pni_2026_excerpt.html`); se o portal mudar de formato, atualize o fixture a partir da página real.
