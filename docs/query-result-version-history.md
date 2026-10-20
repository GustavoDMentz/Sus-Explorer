# #32 — Histórico versionado de resultados analíticos

Status: especificação inicial; implementação pendente. Base: merge do PR #31 (`83a2d8d5eccc4682f139ccafa3967ea211067609`).

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
