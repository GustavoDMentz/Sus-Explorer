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

Edite `.env` e coloque sua `GEMINI_API_KEY`. As credenciais R2 do exemplo são públicas e read-only, conforme publicadas pelo mantenedor do dataset.

## Teste sem LLM

```bash
python smoke_test.py
```

Deve contar a partição RS / maio de 2026 diretamente no R2.

## Interface

```bash
streamlit run app.py
```

## CLI

```bash
python demo.py "Quantas doses foram aplicadas em Porto Alegre em maio de 2026?"
```

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
python refresh_terminology.py
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
