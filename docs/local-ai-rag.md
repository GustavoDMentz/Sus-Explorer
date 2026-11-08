# IA local e RAG

O Streamlit usa Ollama para planejar consultas e explicar agregados calculados pelo Python e PostgreSQL. Documentos locais selecionados pelo operador são indexados no PostgreSQL/pgvector. Para perguntas documentais, a resposta apresenta excertos recuperados literalmente com referência `arquivo#chunk-N`; o modelo generativo não parafraseia esses excertos. Se nenhum trecho recuperado puder ser referenciado, a resposta declara que o contexto é insuficiente. O acesso R2/Parquet permanece apenas nas ferramentas explícitas de migração legada; o serviço normal lê exclusivamente PostgreSQL. Apenas documentação pública do projeto deve entrar no índice: a interface não oferece upload nem autorização por organização.

## Inicialização

1. Copie `.env.example` para `.env` e configure `POSTGRES_PASSWORD`. Não publique o arquivo.
2. Inicie PostgreSQL e Ollama: `docker compose up -d postgres ollama`. A porta Ollama fica restrita a `127.0.0.1`.
3. Baixe os modelos: `docker compose exec ollama ollama pull qwen3:4b-instruct-2507-q4_K_M` e `docker compose exec ollama ollama pull qwen3-embedding:0.6b`.
4. Execute `python -m sus_explorer.check_local_ai`. O comando faz um embedding real e exige 1024 dimensões. **Faça esta verificação antes da migration 007**; se o modelo configurado produzir dimensão diferente, não aplique a migration nem misture vetores. A migration fixa `vector(1024)` para o modelo configurado.
5. Execute `python -m sus_explorer.data.persistence.migrate` com as credenciais PostgreSQL configuradas.
6. Indexe somente arquivos públicos escolhidos pelo operador: `python -m sus_explorer.data.persistence.index_knowledge docs docs/local-ai-rag.md docs/architecture.md`. Revise o conteúdo antes de adicionar outros arquivos; parte da documentação histórica descreve a integração antiga. O hash SHA-256 evita embeddings repetidos para arquivos inalterados. Reexecutar o comando faz a reindexação incremental. A troca dos chunks de um documento ocorre em uma única transação após obter todos os embeddings.
7. Inicie `streamlit run app.py`.

Para validar ingestão → recuperação → resposta documental com serviços reais, configure um banco descartável cujo nome termina em `_test`, defina `SUS_EXPLORER_TEST_DB=1` e `SUS_EXPLORER_RAG_E2E=1`, e execute `python -m pytest tests/e2e/test_local_rag.py -q -m external`. O teste cria e remove apenas seu próprio schema. Sem esses serviços, a suíte padrão valida contratos locais, mas não prova o fluxo fim a fim.

Se Ollama estiver instalado no host, use `ollama serve`, `ollama pull ...` e mantenha `OLLAMA_BASE_URL=http://localhost:11434`; não precisa do serviço Ollama do Compose. PostgreSQL permanece no Compose ou pode ser uma instância existente com pgvector instalado. O operador deve aplicar migrations com papel autorizado; o aplicativo usa papel com leitura da base documental e permissões operacionais já exigidas pelo projeto.

`OLLAMA_CHAT_MODEL` e `OLLAMA_EMBEDDING_MODEL` escolhem modelos separados. `OLLAMA_KEEP_ALIVE=0`, `OLLAMA_MAX_CONCURRENT=1`, `OLLAMA_NUM_CTX=4096` e o serviço Compose com um modelo carregado por vez reduzem pressão de memória. A variante 4B Q4 tem pesos de aproximadamente 2,5 GB, mas a RAM real inclui contexto, runtime, PostgreSQL, Python e sistema. Para um host de 4 GB, copie `.env.economy.example` para `.env`: ele seleciona `qwen3:1.7b-q4_K_M`, contexto de 1024 tokens, uma inferência por vez e descarregamento ao fim. A alternativa reduz capacidade de planejamento e qualidade de linguagem; valide as perguntas do seu uso. Alterar o modelo de embeddings exige reindexar todos os documentos; a busca filtra por nome e digest do modelo e não mistura versões distintas.

`RAG_MIN_SIMILARITY=0.65` é um ponto de partida, sem calibração para perguntas reais. O banco usa busca exata por cosseno, apropriada ao pequeno conjunto de documentos curados; avaliar HNSW se o volume e a latência justificarem. A resposta documental é montada pelo backend a partir de texto literal dos chunks e da referência persistida. Ela não afirma que o score vetorial comprova relevância semântica; limiar e fontes precisam ser avaliados com perguntas representativas.

Não indexe microdados, perguntas de usuários, documentos privados ou material sujeito a permissões diferentes. O RAG deste projeto tem somente o escopo `project_docs`, sem upload pela interface. A pergunta vai ao modelo de embeddings local e os agregados calculados vão ao modelo de geração local; documentos e microdados não saem para provedores externos de IA.
