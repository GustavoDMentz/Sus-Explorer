# Testes e níveis de validação

## Suíte padrão

```bash
python -m pytest tests -q
```

O `pytest.ini` desmarca `external` por padrão. Os níveis são:

| Nível | Marcador/área | O que comprova | Limite |
| --- | --- | --- | --- |
| Unitário | `tests/unit` | regras puras, validação, SQL construído, RAG isolado e AppTest com fronteiras substituídas | não prova serviços reais |
| Integração local | `tests/integration` | componentes locais e, quando habilitado, PostgreSQL descartável | depende de `SUS_EXPLORER_TEST_DB=1` e banco `*_test` |
| E2E externo | `external`, `tests/e2e` | PostgreSQL/pgvector, Ollama e fontes configuradas | opt-in para evitar tocar base persistente ou consumir modelos sem intenção |

## Execução dos gates externos

```bash
export SUS_EXPLORER_TEST_DB=1
export POSTGRES_DB=sus_explorer_test
python -m pytest tests/integration -q

export SUS_EXPLORER_RAG_E2E=1
python -m pytest tests/e2e/test_local_rag.py -q -m external
```

`test_external_query.py` exige ainda configuração do canário e valores independentes. Mocks validam contratos isolados; relatórios devem classificá-los separadamente de integração real.

## Avaliações auxiliares

- `python scripts/semantic_benchmark_100.py`: roteamento determinístico; `--ollama` executa planner real.
- `python -m scripts.evaluate_rag --validate-only`: valida o catálogo qualitativo sem serviços.
- `python -m scripts.evaluate_rag`: executa casos reais e produz JSON auditável.
- `python -m sus_explorer.data.persistence.semantic_audit`: integridade semântica no banco ativo.

O alvo reproduzível é Linux/Python 3.12 com `requirements-lock.txt`. Windows/Python 3.13 é compatibilidade exercitada, não alvo do lock.
