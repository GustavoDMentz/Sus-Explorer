# #32 — Histórico versionado de resultados analíticos

> **Estado em 2026-10-20:** o PR [#32](https://github.com/GustavoDMentz/Sus-Explorer/pull/32) foi integrado à `master`. Esta página começou como **especificação anterior à implementação**: os itens de “Modelo sugerido”, “Testes obrigatórios” e o plano de validação abaixo são requisitos e roteiro histórico, **não uma lista de funcionalidades necessariamente implementadas ou testes executados**. Para o comportamento atual, consultar `sus_explorer/data/persistence/result_versions.py`, migration `005_analytical_result_versions.sql` e `app.py`.
>
> **Implementado:** snapshots agregados com AES-GCM e HMAC, chave `ANALYTICAL_HISTORY_KEY`, opt-in `ANALYTICAL_HISTORY_ENABLED=1`, versões por consulta canônica e deduplicação do resultado consecutivo idêntico; leitura de versões da consulta atual na UI. **Não demonstrado/pendente:** isolamento por proprietário no PostgreSQL, política de rotação/retenção, integridade autenticada de `source_fingerprint`, teste adversarial completo e aprovação dos PRs #33/#34. O fingerprint de origem não é parte do MAC de `get_versions`.
>
 **Base histórica da proposta:** merge do PR #31 (`83a2d8d5eccc4682f139ccafa3967ea211067609`).

## Objetivo
Persistir de modo compacto, seguro e auditável **mudanças de resultados** de consultas determinísticas do SUS Explorer. Não registrar perguntas livres, chaves BYOK, respostas narrativas do Gemini ou microdados pessoais.

## Semântica
1. Identificar consultas equivalentes por um QueryPlan **validado e canônico**, não pela redação da pergunta. Incluir operação, todos os filtros relevantes, intervalo, agrupamento, ordem temporal, versão da semântica e versão do executor; não confundir parâmetros ausentes com valores padrão.
2. Após execução bem-sucedida, canonizar o **resultado analítico integral** (dados estruturados, cobertura, partições ausentes, avisos semanticamente relevantes). Excluir latência, run_id e texto narrativo. Gerar SHA-256 de ambos os documentos canônicos.
3. Primeira observação: criar versão 1. Mesmo plano e mesmo resultado: **não criar nova versão**, atualizar `last_seen_at` e `observations` transacionalmente. Mesmo plano e resultado diferente: criar versão imutável N+1, preservando todas as anteriores, inclusive reversões A→B→A.
4. Distinguir **mudança de resultado** de **mudança de fonte**. Identidade de fragmentos, tamanho, ETag/version-id quando disponíveis devem compor fingerprint de origem separado; mudança de fingerprint com resultado igual é evento de proveniência, não necessariamente nova versão numérica. Sem fingerprint, registrar `unverified`, nunca presumir fonte estável.
5. Falhas, esclarecimentos e consultas canceladas não geram versões de resultado; registrar somente eventos operacionais redigidos.

## Modelo sugerido
- `analytical_queries`: `query_key` único, plano canônico seguro, versão da semântica, created_at.
- `analytical_result_versions`: `query_key`, `version`, `result_hash`, resultado agregado seguro, first_seen_at, last_seen_at, observations, provenance_digest, integridade. Restrição única `(query_key, version)`; imutabilidade dos dados versionados.
- `analytical_source_observations` (opcional): mudanças de fingerprint com resultado idêntico; sem duplicação dos resultados.
- Transações com serialização por chave de consulta (lock/UPSERT) para evitar versões duplicadas em sessões concorrentes.

## Segurança e privacidade
- Permitir somente valores analíticos agregados validados, códigos e parâmetros tipados; bloquear perguntas, payloads de microdados, CPF/CNS, tokens e segredos. Avaliar risco de pequenas células antes de persistir grupos.
- Hash SHA-256 **não é criptografia**. Para integridade autenticada, usar HMAC ou assinatura com gestão de chaves; para confidencialidade, criptografia autenticada em repouso com chaves fora do banco. Definir política de rotação, retenção e backup.
- Não expor histórico de outras sessões/usuários sem autorização explícita. Não reutilizar `recent_queries()` global como interface pública multiusuário.

## Integração
- Integrar após `executor.execute(plan)` e antes/independentemente da narrativa Gemini, para que uma falha da resposta textual não destrua a observação analítica.
- Histórico de versões separado de `query_history` operacional existente.
- Persistência opcional com falha explícita/observável, sem falsamente alegar auditoria quando o banco estiver indisponível.
- Mostrar ao usuário versão atual, número de versões, última alteração e diferença para a versão anterior, quando aplicável.

## Testes obrigatórios
- Mesmo plano, mesmo resultado, perguntas diferentes → 1 versão; `observations=2`.
- Mesmo plano, resultado diferente → 2 versões com ambas recuperáveis.
- Reversão A→B→A → 3 versões; jamais sobrescrever histórico.
- Mesmo resultado com origem alterada → proveniência atualizada, sem versão numérica redundante.
- Planos com filtros, períodos ou semânticas diferentes → chaves diferentes.
- Concorrência de sessões → sem versões duplicadas.
- Falha de persistência, reinício, indisponibilidade PostgreSQL e migração → comportamento verificável.
- Não vazamento de BYOK, perguntas livres ou dados pessoais.
- Consultas RS maio/2026 com 1.179.648 e 1.223.529 como fixtures sintéticas; não atribuir causa da diferença sem evidência.

## Fora do escopo
Auditoria abrangente de cibersegurança reservada ao #33. Nenhum merge automático deste PR.


## Plano de validação independente (obrigatório antes do merge)

**Pré-condições:** executar em PostgreSQL descartável (`*_test`), com chave de 32 bytes exclusiva do teste. Nunca aplicar migrations de teste na base de produção. O recurso fica desligado por padrão.

1. **Revisão estática:** verificar diff do PR, permissões SQL, ausência de segredos e de campos pessoais nos snapshots. Inspecionar a migration 005 antes de executá-la.
2. **Testes automatizados:** `python -m pytest -q tests/test_analytical_result_versions.py`; depois `python -m pytest -q`. Rodar a suíte de integração PostgreSQL com Docker conforme README/CI.
3. **Teste real controlado:** após migrations e configuração de `ANALYTICAL_HISTORY_ENABLED=1` e `ANALYTICAL_HISTORY_KEY`, consultar RS/05/2026 duas vezes; confirmar mesma versão e contador 2. Repetir com duas perguntas equivalentes e conferir o mesmo `query_key`.
4. **Mudança simulada, sem alterar dados públicos:** executar fixture controlada A→B→A usando a mesma consulta e resultados sintéticos; conferir versões 1, 2 e 3 e que todas são legíveis e verificadas por AES-GCM/HMAC.
5. **Teste adversarial:** adulterar uma cópia do ciphertext no banco de testes, verificar que a leitura falha sem revelar conteúdo; testar chave incorreta e indisponibilidade do PostgreSQL.
6. **Concorrência:** disparar pelo menos 10 observações simultâneas do mesmo plano, com mesma contagem, e verificar apenas uma versão com 10 observações; repetir com dois resultados diferentes. O teste de concorrência precisa usar PostgreSQL real.
7. **Fonte:** observar fingerprint dos fragmentos R2 em duas execuções e verificar estabilidade; lembrar que fingerprint de metadados (caminho/tamanho/mtime) não equivale a hash de conteúdo.
8. **UI/BYOK:** testar duas sessões independentes, uma sem chave Gemini; conferir que a interface só mostra histórico da consulta corrente e que limpar credenciais apaga o estado exibido.
9. **Revisão científica:** distinguir doses/registros de pessoas únicas; conferir intervalos, filtros, partições ausentes, percentuais e revisões retrospectivas. Não atribuir diferenças à atualização do MS sem evidência.

**Comandos de preparação (ambiente de teste):**

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
export ANALYTICAL_HISTORY_ENABLED=1
export ANALYTICAL_HISTORY_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m sus_explorer.data.persistence.migrate
python -m pytest -q tests/test_analytical_result_versions.py
python -m pytest -q
```

O exemplo usa chave efêmera: **não a utilize para dados que precisem continuar legíveis após reinício**. Configurar a chave estável via gerenciador de segredos no ambiente real. Não copiar segredos ou dumps para issues.

## Limitações conhecidas nesta etapa

- `ANALYTICAL_HISTORY_ENABLED` é opt-in; PostgreSQL e chave são obrigatórios.
- O snapshot agregado é cifrado com AES-256-GCM e autenticado com HMAC-SHA-256, mas rotação de chave, isolamento multiusuário no banco, política de retenção e auditoria de pequenas células exigem avaliação adicional antes de produção.
- A impressão digital R2 atual é derivada de metadados de fragmentos; não prova igualdade byte a byte.
- A observação do resultado é independente do texto Gemini. Se a persistência falhar, a consulta segue com aviso explícito.
- Não existe reconstrução retrospectiva das observações anteriores à ativação.
