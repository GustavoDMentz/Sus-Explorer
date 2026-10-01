# SUS Explorer — MVP

Protótipo para consultar microdados públicos do SI-PNI diretamente de Parquet remoto (Cloudflare R2), usando um LLM apenas para planejar consultas e explicar resultados agregados. **Microdados individuais não são enviados ao LLM.**

## Fluxo

Pergunta → Gemini (plano JSON) → Pydantic → PyArrow/R2 → agregado + proveniência → Gemini → resposta.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Para executar a suíte localmente, instale também `pip install -r requirements-dev.txt`.

Edite `.env` e informe sua `GEMINI_API_KEY` e a configuração R2 que você utiliza. O arquivo de exemplo não contém credenciais.

## Teste sem LLM

```bash
python -m scripts.smoke_pni
```

Deve contar a partição RS / maio de 2026 diretamente no R2.

## Interface

```bash
streamlit run app.py
```

## CLI

```bash
python -m scripts.demo "Quantas doses foram aplicadas em Porto Alegre em maio de 2026?"
```

Os comandos manuais ficam em `scripts/`. O builder e o auditor R2 são módulos do pacote (`python -m sus_explorer.build_cache --help` e `python -m sus_explorer.cli.audit_ms --help`). A [arquitetura atual](docs/architecture.md) mostra os dois pipelines; a [auditoria do repositório](docs/repository_audit.md) classifica scripts, caches e dados locais.

## Operações do MVP

- `count`: contagem de doses/registros;
- `group`: agrupamento por vacina, município, sexo, idade, dose, CNES, sistema de origem ou raça/cor;
- `timeseries`: série mensal;
- `latency`: mediana/P90/P95 entre vacinação e entrada na RNDS.

## Limites

- A partição `uf=` é a UF do estabelecimento.
- Tudo no SI-PNI remoto é tratado como dado público, mas nenhum registro individual é enviado ao Gemini.
- O LLM não escreve SQL e não acessa o bucket diretamente: ele só produz um `QueryPlan` validado.
- O MVP não calcula cobertura vacinal; isso entra depois com denominadores IBGE.

## Fundação PostgreSQL (opt-in)

O caminho de consulta atual continua em Parquet/R2. PostgreSQL guarda futuros registros de ingestão e dados normalizados; nenhuma importação ou troca automática da fonte de consulta foi adicionada. Veja [docs/persistence.md](docs/persistence.md) para modelo, segurança e operação.

Para criar um banco local, defina `POSTGRES_DB`, `POSTGRES_USER` e `POSTGRES_PASSWORD` no ambiente ou num `.env` local (use `.env.example` como referência). Depois:

```bash
docker compose up -d postgres
python -m sus_explorer.data.persistence.migrate
```

O comando de migration requer também `POSTGRES_HOST` e `POSTGRES_PORT`. O banco não é inicializado por import da aplicação. Para o teste de integração, use **somente um banco descartável** e defina `SUS_EXPLORER_TEST_DB=1` antes de rodar `python -m pytest tests/integration`.


## Merge de terminologia MS + SES-GO

A versão atual usa:

- **Ministério da Saúde / BRImunobiologico** como autoridade para `code` e
  `official_display`.
- **SES-GO / BRImunobiologico** para `definition`.

A definição da SES-GO só é incorporada se o `display` do mesmo código for
compatível com o display canônico do MS. Em divergência:

```json
{
  "definition": null,
  "terminology_conflict": true
}
```

O LLM é instruído a nunca completar a descrição por memória própria.

O cache fica em:

```text
~/.cache/sus_explorer/BRImunobiologico_ms_go.json
```

Para atualizar e testar o merge:

```bash
python -m scripts.refresh_terminology
```

Uma linha de agrupamento por vacina passa a ter a forma:

```json
{
  "code": "33",
  "display": "INF3",
  "official_display": "INF3",
  "definition": "Vacina influenza trivalente",
  "definition_source": "SES-GO / BRImunobiologico",
  "terminology_conflict": false,
  "count": 616927
}
```
