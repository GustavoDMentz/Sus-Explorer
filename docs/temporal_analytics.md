# TemporalAnalytics v1

Módulo independente em `sus_explorer.analytics`, sem leitura de banco/bucket,
logging próprio ou chamada ao LLM. Consome somente séries mensais já agregadas.
Não está conectado a `QueryPlan`, `PNIRemote`, `SUSExplorer` ou ao frontend;
as operações e respostas existentes permanecem iguais.

## Contrato de entrada

```python
from sus_explorer.analytics import TemporalAnalytics

result = TemporalAnalytics.calculate(
    [
        {"period": "2026-01", "doses": 10},
        {"period": "2026-02", "doses": 12},
        {"period": "2026-03", "doses": 16},
        {"period": "2026-04", "doses": 22},
    ],
    start_period="2026-01",
    end_period="2026-04",
    source_series_ref="query:monthly-rs:version-1",
    source_provenance={"source": "synthetic-example", "filters": {"uf": "RS"}},
    value_key="doses",
    unit="doses",
)
payload = result.model_dump()
```

`period` deve ser `YYYY-MM`, ano 0001–9999 e mês 01–12. As linhas devem estar
estritamente ordenadas, sem duplicatas e dentro dos limites inclusivos
obrigatórios. Não há ordenação, agregação de duplicatas ou correção automática.
Cada linha exige a chave do valor; `None` é uma observação explicitamente
indisponível. Valores são `int` Python ou `Decimal` finito; bool, float,
NaN, infinito e strings numéricas são rejeitados. Uma série vazia é válida e
produz meses indisponíveis em todo o intervalo declarado.

`source_series_ref` é a referência não vazia à série de origem, fornecida pelo
chamador; `source_provenance` é seu objeto JSON, copiado sem alterações. O
módulo não valida autenticidade dessa referência. Ao usar `QueryResult` de
`timeseries`, passar `result.data["rows"]` e `result.provenance` explicitamente,
junto do intervalo e de uma referência reproduzível à consulta. Os limites
explícitos preservam também lacunas no início/fim que não aparecem nas linhas.

## Método e convenção temporal

Diferenças regressivas, alinhadas ao mês mais recente `t`, com passo mensal
constante `h=1 mês`:

| Métrica | Fórmula | Unidade declarada |
|---|---|---|
| `delta_1` | `y(t) - y(t-1)` | unidade de origem/mês |
| `delta_2` | `y(t) - 2*y(t-1) + y(t-2)` | unidade de origem/mês² |
| `delta_3` | `y(t) - 3*y(t-1) + 3*y(t-2) - y(t-3)` | unidade de origem/mês³ |

São diferenças por passo mensal discreto (equivalentes à divisão por `h^k`
com `h=1`), não derivadas contínuas nem taxas por quantidade de dias. Dezembro
e janeiro são meses consecutivos. Não há suavização, interpolação, imputação,
normalização por população ou detecção de anomalias.

Cada ordem exige uma janela de `ordem + 1` meses com valores disponíveis.
Nenhuma diferença atravessa lacunas. Após uma lacuna, cada ordem só retoma
quando sua própria janela está completa. Zero observado participa normalmente;
ausência nunca vira zero.

## Saída e proveniência

O resultado tem `operation`, `data`, `provenance`, `warnings` e `model_dump()`,
seguindo a forma geral de `QueryResult` sem importar o backend remoto. Cada
mês do intervalo possui `value`, `observation_status` e três métricas com
`classification: DERIVED`, `value` e `unavailable_reasons`.

Indisponibilidade usa `None` em Python e `null` no JSON. As razões são objetos
com `code` e `period`:

- `INSUFFICIENT_HISTORY`: dependência anterior ao início declarado;
- `MISSING_MONTH`: mês não fornecido dentro do intervalo;
- `MISSING_VALUE`: linha fornecida com valor `None`.

As razões podem coexistir na mesma janela. Para dependência anterior ao ano
0001, `period` é `null`. Janelas completas têm lista de razões vazia.

Inteiros permanecem inteiros exatos. Janelas com `Decimal` usam escala inteira
comum e produzem `Decimal` exato, independentemente do contexto decimal do
chamador. `model_dump()` representa `Decimal` como string decimal exata para
evitar conversão implícita a float; consumidores devem respeitar
`numeric_encoding`. Inteiros JSON grandes também exigem um leitor que preserve
precisão (por exemplo, JavaScript `Number` não garante isso). Nenhuma nova
dependência foi adicionada.

A proveniência inclui operação, classificação, fórmulas, método/versionamento
`1.0.0`, intervalo, ordens, passo, chave do valor, política de ausência,
alinhamento, unidades e referência/proveniência original. Não há timestamps
gerados: entradas iguais produzem saídas iguais. Os objetos de origem não são
mutados; a saída e sua serialização recebem cópias independentes.

Diferenças finitas descrevem mudança, mudança da mudança e sua terceira
diferença. Não estabelecem causalidade, cobertura vacinal, anomalia estatística
ou ponto de inflexão confirmado. O módulo não envia dados ao LLM.

## Validação desta entrega

Base: `master` em `5d2b806` (inclui o PR documental #7).

Execução local em 2026-10-07:

```text
python -m pytest tests -q
144 passed, 7 skipped in 1.35s
```

Os 45 novos casos validam séries constantes, lineares, quadráticas, cúbicas,
quedas, zeros, lacunas, null explícito, ordem/duplicatas, meses inválidos,
intervalos, séries insuficientes, virada de ano, números exatos, serialização,
metadados e preservação da proveniência. Os sete testes PostgreSQL existentes
foram pulados porque este ambiente não tem runtime PostgreSQL descartável;
o workflow existente do PR executa essas integrações com PostgreSQL/pgvector.
Resultados de CI devem ser consultados no PR; o resultado local acima não é
uma execução de integração PostgreSQL.

Arquivos novos desta etapa: `sus_explorer/analytics/__init__.py`,
`sus_explorer/analytics/temporal.py`, `tests/unit/test_temporal_analytics.py` e
este documento. Logging, publicador de auditoria, artefatos científicos,
migrations e comportamento Parquet/R2 não foram alterados.
