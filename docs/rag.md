# Recuperação documental e síntese

## Pipeline

Documentos públicos selecionados pelo operador são divididos em chunks, transformados em embeddings pelo Ollama e persistidos em pgvector. Nome e digest do modelo compõem a identidade do índice; versões diferentes não são misturadas.

```bash
python -m sus_explorer.check_local_ai
python -m sus_explorer.data.persistence.index_knowledge docs \
  docs/architecture.md docs/data-sources.md docs/analytics.md
```

A busca usa cosseno, limiar configurável e orçamento de contexto. Perguntas documentais explícitas podem usar o RAG sem executar consulta analítica. Perguntas híbridas recebem também o agregado já calculado no PostgreSQL.

## Síntese e referências

Chunks são conteúdo não confiável. O prompt impede que instruções encontradas neles substituam regras da aplicação. O modelo retorna JSON estruturado com resposta e IDs selecionados; o backend aceita somente IDs que vieram da recuperação e rejeita síntese sem citação verificável. A interface diferencia fontes consultadas das fontes usadas na síntese.

Essa validação impede IDs inventados, mas não prova pertinência semântica. A avaliação real precisa conferir se cada trecho sustenta as afirmações.

## Avaliação reproduzível

```bash
python -m scripts.evaluate_rag --validate-only
python -m scripts.evaluate_rag --output rag-evaluation.json
```

Os casos em `tests/fixtures/rag_evaluation_cases.json` cobrem fonte oficial, arquitetura, temporal/híbrido, geografia, interpretação, escopo ausente, premissa incorreta, evidência insuficiente, ambiguidade e prompt injection. O relatório registra intenção, referências, termos proibidos, latência e erros. A execução completa exige PostgreSQL/pgvector, documentos indexados e Ollama reais.

`RAG_MIN_SIMILARITY=0.65` é ponto de partida, não limiar cientificamente calibrado. Meça recuperação e fidelidade antes de alterá-lo ou adicionar HNSW/reranking.
