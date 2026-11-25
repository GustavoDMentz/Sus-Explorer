# Auditoria direcionada de segurança e qualidade — 25/11/2026

## Verificações executadas

- busca por credenciais atribuídas em arquivos rastreados, excluindo fixtures e exemplos: nenhuma ocorrência;
- busca por `.env`, ZIP, dump, virtualenv e caches rastreados: nenhuma ocorrência;
- links Markdown relativos: nenhum link quebrado após a reorganização;
- `pip check`: dependências instaladas sem conflito;
- testes de lockfile, hashes, imagens fixadas e defaults de rede: 25 aprovados;
- demonstração offline de redação, limites do plano, divulgação, minimização, ZIP e imagens remotas: aprovada;
- benchmark determinístico: 100/100 casos, 60 rotas REGEX, zero falso positivo de rota.

## Achados e correções

1. O endpoint `/api/tags` seguia redirecionamentos enquanto `/api/chat` e `/api/embed` já recusavam. `OllamaClient.model_digest`, diagnóstico e canário local agora usam `allow_redirects=False`; foi adicionado teste de regressão.
2. O downloader incremental poderia seguir redirecionamento fora da origem oficial. Ele agora reutiliza o opener sem redirects e a allowlist de host/path do catálogo.
3. Retomada HTTP precisava confirmar identidade do snapshot. O job valida URL, tamanho, ETag, status 206 e `Content-Range`, calcula SHA-256 e preserva parcial incompatível para decisão manual.
4. Referências geradas pelo modelo não eram selecionadas de forma estruturada. O RAG agora aceita somente IDs recuperados, exige pelo menos uma citação e retorna contexto insuficiente para ID inventado.
5. Métricas fora da base poderiam ser interpretadas como contagem de doses. Uma guarda de escopo recusa pacientes únicos, atendimentos, produção ambulatorial, valores financeiros e cobertura vacinal antes do planner/banco.
6. `sus_explorer.domain.provenance` declarava modelos futuros e era importado somente pelos próprios dois testes. O módulo e os testes foram removidos como código morto. `smoke_test.py`, hardcoded para uma partição histórica, foi substituído pelo diagnóstico configurável e removido.

## SQL e exceções

O executor usa valores parametrizados. Os trechos interpolados são expressões internas de uma allowlist e operações validadas; `group_by` arbitrário é recusado. Não foi encontrada geração de SQL livre pelo modelo.

Os `except Exception` da UI evitam expor detalhes de infraestrutura ao usuário e limpam resultado obsoleto. Importadores registram apenas o tipo do erro e fazem rollback. Essa generalidade é deliberada nas fronteiras; os testes verificam ausência de credenciais nas mensagens. Medições reais de consultas e inferência continuam dependentes da infraestrutura.
