# Recuperação documental e síntese

## Pipeline

Documentos públicos selecionados pelo operador são divididos em chunks, transformados em embeddings pelo Ollama e persistidos em pgvector. Nome e digest do modelo compõem a identidade do índice; versões diferentes não são misturadas.

```bash
python -m sus_explorer.check_local_ai
python -m sus_explorer.data.persistence.index_knowledge docs \
  docs/architecture.md docs/data-sources.md docs/analytics.md
```

A busca usa distância cosseno (`<=>`), convertida em similaridade por `1 - distância`, limiar configurável e orçamento de contexto. A consulta recebe a instrução de recuperação recomendada pelo Qwen3 Embedding; os documentos continuam embedados sem instrução. Perguntas documentais explícitas podem usar o RAG sem executar consulta analítica. Perguntas híbridas recebem também o agregado já calculado no PostgreSQL.

## Síntese e referências

Chunks são conteúdo não confiável. Para perguntas documentais sem resultado analítico, o modelo seleciona até três trechos literais; o backend confere a correspondência exata com o conteúdo persistido e a aderência lexical à pergunta. Se a seleção falhar, um fallback determinístico pode escolher frases literais que correspondam à pergunta. Para perguntas híbridas, a síntese pode interpretar o agregado calculado e citar documentos com os IDs selecionados; os valores continuam sujeitos ao contrato analítico. A interface diferencia fontes consultadas das fontes usadas na resposta.

Essa validação impede IDs inventados, mas não prova pertinência semântica. A avaliação real precisa conferir se cada trecho sustenta as afirmações.

## Avaliação reproduzível

```bash
python -m scripts.evaluate_rag --validate-only
python -m scripts.evaluate_rag --output rag-evaluation.json
```

Os casos em `tests/fixtures/rag_evaluation_cases.json` cobrem fonte oficial, arquitetura, temporal/híbrido, geografia, interpretação, escopo ausente, premissa incorreta, evidência insuficiente, ambiguidade e prompt injection. O relatório registra intenção, referências, termos proibidos, latência e erros. A execução completa exige PostgreSQL/pgvector, documentos indexados e Ollama reais.

O corte padrão `RAG_MIN_SIMILARITY=0.50` foi calibrado contra os chunks reais dos três documentos operacionais e as perguntas da avaliação em 2026-11-25. Ele é uma configuração de recuperação para esse corpus, não uma garantia universal de relevância. Diagnósticos por consulta registram os candidatos do top-K, scores e descartes; confira as citações antes de ampliar o corpus ou alterar esse corte.
