# Registro de PRs — SUS Explorer (corte: 2026-11-20)

Este índice separa **integrado à master**, **fechado sem merge** e **aberto**. Datas em UTC, como o GitHub as registra. Em 14/11/2026 a história da `master` foi reescrita para uniformizar a autoria (ver o diário): os números dos PRs permanecem, mas os hashes de commits anteriores a essa data mudaram. O título/corpo original de um PR é evidência histórica, não necessariamente a descrição do código final. Consulte o diff, os commits e os testes do PR antes de afirmar que uma funcionalidade foi entregue. O diário técnico guarda a cronologia; o README descreve a operação atual.

| PR | Assunto | Estado em 20/11/2026 | Observação |
| --- | --- | --- | --- |
| [#1](https://github.com/GustavoDMentz/Sus-Explorer/pull/1) | PostgreSQL opcional | Integrado | Fundação operacional, Parquet/R2 preservado |
| [#2](https://github.com/GustavoDMentz/Sus-Explorer/pull/2) | Hardening PostgreSQL | Integrado | Roles, conexões, validações, testes |
| [#3](https://github.com/GustavoDMentz/Sus-Explorer/pull/3) | setup-python 7 | Integrado | Actions |
| [#4](https://github.com/GustavoDMentz/Sus-Explorer/pull/4) | checkout 7 | Integrado | Actions |
| [#5](https://github.com/GustavoDMentz/Sus-Explorer/pull/5) | NumPy 2.5.3 | Integrado | Posteriormente #27 |
| [#6](https://github.com/GustavoDMentz/Sus-Explorer/pull/6) | pandas 3.0.6 | Integrado | Dependências |
| [#7](https://github.com/GustavoDMentz/Sus-Explorer/pull/7) | Diário até 07/10 | Integrado | Histórico anterior preservado |
| [#8](https://github.com/GustavoDMentz/Sus-Explorer/pull/8) | TemporalAnalytics v1 | Integrado | Δ1–Δ3 |
| [#9](https://github.com/GustavoDMentz/Sus-Explorer/pull/9) | Temporal QueryPlan | Integrado | Planner tipado e execução Python |
| [#10](https://github.com/GustavoDMentz/Sus-Explorer/pull/10) | Protótipo Next.js/FastAPI | Fechado sem merge | Arquitetura não adotada na interface principal |
| [#11](https://github.com/GustavoDMentz/Sus-Explorer/pull/11) | Schema nativo Gemini | Fechado sem merge | Conteúdo selecionado via #18 |
| [#12](https://github.com/GustavoDMentz/Sus-Explorer/pull/12) | Streamlit principal | Fechado sem merge | Conteúdo selecionado via #19 |
| [#13](https://github.com/GustavoDMentz/Sus-Explorer/pull/13) | Percentuais mensais | Fechado sem merge | Conteúdo selecionado via #20 |
| [#14](https://github.com/GustavoDMentz/Sus-Explorer/pull/14) | Volume e extremos | Fechado sem merge | Conteúdo selecionado via #21 |
| [#15](https://github.com/GustavoDMentz/Sus-Explorer/pull/15) | Cores de proveniência | Fechado sem merge | Conteúdo selecionado via #22 |
| [#16](https://github.com/GustavoDMentz/Sus-Explorer/pull/16) | YoY e barras interrompidas | Fechado sem merge | Conteúdo selecionado via #23 |
| [#17](https://github.com/GustavoDMentz/Sus-Explorer/pull/17) | Catálogo de campanhas | Fechado sem merge | Fechado em 20/10; nada do catálogo está na `master` |
| [#18](https://github.com/GustavoDMentz/Sus-Explorer/pull/18) | Integração limpa do #11 | Integrado | Sem web abandonada |
| [#19](https://github.com/GustavoDMentz/Sus-Explorer/pull/19) | Integração limpa do #12 | Integrado | Streamlit |
| [#20](https://github.com/GustavoDMentz/Sus-Explorer/pull/20) | Integração limpa do #13 | Integrado | MoM |
| [#21](https://github.com/GustavoDMentz/Sus-Explorer/pull/21) | Integração limpa do #14 | Integrado | Gráficos |
| [#22](https://github.com/GustavoDMentz/Sus-Explorer/pull/22) | Integração limpa do #15 | Integrado | Proveniência |
| [#23](https://github.com/GustavoDMentz/Sus-Explorer/pull/23) | Integração limpa do #16 | Integrado | YoY |
| [#24](https://github.com/GustavoDMentz/Sus-Explorer/pull/24) | google-genai 2.29.0 | Integrado | 20/10 |
| [#25](https://github.com/GustavoDMentz/Sus-Explorer/pull/25) | Pydantic 2.14.1 | Integrado | 20/10 |
| [#26](https://github.com/GustavoDMentz/Sus-Explorer/pull/26) | PyArrow 26.0.0 | Fechado sem merge | Fechado em 20/10; PyArrow 26.0.1 entrou depois pelo #65 |
| [#27](https://github.com/GustavoDMentz/Sus-Explorer/pull/27) | NumPy 2.5.4 | Integrado | 20/10 |
| [#28](https://github.com/GustavoDMentz/Sus-Explorer/pull/28) | README operacional | Integrado | 14/10; anterior a #29–#32 |
| [#29](https://github.com/GustavoDMentz/Sus-Explorer/pull/29) | Feature/g | Integrado | Mudança ampla; descrição original vazia: conferir diff |
| [#30](https://github.com/GustavoDMentz/Sus-Explorer/pull/30) | Planner determinístico | Integrado | Experimental; flag opt-in |
| [#31](https://github.com/GustavoDMentz/Sus-Explorer/pull/31) | BYOK por sessão | Integrado | UI Gemini apenas; R2 compartilhado, apesar do título original |
| [#32](https://github.com/GustavoDMentz/Sus-Explorer/pull/32) | Histórico versionado | Integrado | Checklist inicial do PR ficou desatualizado |
| [#33](https://github.com/GustavoDMentz/Sus-Explorer/pull/33) | Limite de pergunta | Fechado sem merge | Draft; reaplicado pelo #45 |
| [#34](https://github.com/GustavoDMentz/Sus-Explorer/pull/34) | Histórico visual por sessão | Fechado sem merge | Draft; superado pelo #39 (histórico em `st.session_state`) |
| [#35](https://github.com/GustavoDMentz/Sus-Explorer/pull/35) | Reconciliação do histórico de PRs | Integrado | Documentação, 20/10 |
| [#36](https://github.com/GustavoDMentz/Sus-Explorer/pull/36) | README para profissionais de saúde | Integrado | 20/10 |
| [#37](https://github.com/GustavoDMentz/Sus-Explorer/pull/37) | Revogar mutação de `source_fingerprint` | Fechado sem merge | Draft; reaplicado pelo #45 (migration 006) |
| [#38](https://github.com/GustavoDMentz/Sus-Explorer/pull/38) | Instalação para iniciantes | Integrado | 20/10 |
| [#39](https://github.com/GustavoDMentz/Sus-Explorer/pull/39) | Histórico de sessão no Streamlit | Integrado | 20/10 |
| [#40](https://github.com/GustavoDMentz/Sus-Explorer/pull/40) | Planejador REGEX no Streamlit | Integrado | 20/10; fallback Gemini à época |
| [#41](https://github.com/GustavoDMentz/Sus-Explorer/pull/41) | Catálogo de disponibilidade de competências | Integrado | 20/10 |
| [#42](https://github.com/GustavoDMentz/Sus-Explorer/pull/42) | Tamanho e última modificação no catálogo R2 | Integrado | 20/10 |
| [#43](https://github.com/GustavoDMentz/Sus-Explorer/pull/43) | Comparar verificações do catálogo na sessão | Integrado | 20/10 |
| [#44](https://github.com/GustavoDMentz/Sus-Explorer/pull/44) | Integração arquitetural do Streamlit | Integrado | 20/10; testes e documentação |
| [#45](https://github.com/GustavoDMentz/Sus-Explorer/pull/45) | Limites de consulta e integridade do histórico | Integrado | 20/10; encerra #33, #34 e #37 |
| [#46](https://github.com/GustavoDMentz/Sus-Explorer/pull/46) | google-genai 2.31.0 | Integrado | 25/10; o pacote saiu da `master` com o #66 |
| [#47](https://github.com/GustavoDMentz/Sus-Explorer/pull/47) | Streamlit 1.66.1 | Integrado | 25/10; posteriormente #72 |
| [#48](https://github.com/GustavoDMentz/Sus-Explorer/pull/48) | cryptography ≥ 50.0.2, < 51 | Integrado | 25/10 |
| [#49](https://github.com/GustavoDMentz/Sus-Explorer/pull/49) | setup-python 7.1.0 | Integrado | 28/10 |
| [#50](https://github.com/GustavoDMentz/Sus-Explorer/pull/50) | pandas 3.1.0 | Integrado | 28/10; posteriormente #64 |
| [#51](https://github.com/GustavoDMentz/Sus-Explorer/pull/51) | google-genai 2.33.0 | Integrado | 28/10; o pacote saiu da `master` com o #66 |
| [#52](https://github.com/GustavoDMentz/Sus-Explorer/pull/52) | Diagnósticos de tempo de consulta | Fechado sem merge | 14/11; otimizava a leitura R2/Parquet, que saiu do fluxo de consulta com o #66, e tinha conflito em `service.py` |
| [#53](https://github.com/GustavoDMentz/Sus-Explorer/pull/53) | LLM configurável (Gemini, Groq, OpenRouter, Mistral, OpenAI) | Fechado sem merge | Draft; fechado em 14/11. A parte de `llm.py` e `app.py` entrou pelo #54 e foi depois substituída por Ollama no #66 |
| [#54](https://github.com/GustavoDMentz/Sus-Explorer/pull/54) | LLM independente de provedor e BYOK no Streamlit | Integrado | 28/10; validação por CI; substituído pelo Ollama no #66 |
| [#55](https://github.com/GustavoDMentz/Sus-Explorer/pull/55) | Compatibilidade de testes do planejador legado | Integrado | 28/10; correção de CI do #54 |
| [#56](https://github.com/GustavoDMentz/Sus-Explorer/pull/56) | pytest 9.2.0 | Integrado | 06/11 |
| [#57](https://github.com/GustavoDMentz/Sus-Explorer/pull/57) | google-genai 2.34.0 | Integrado | 06/11; o pacote saiu da `master` com o #66 |
| [#58](https://github.com/GustavoDMentz/Sus-Explorer/pull/58) | Pydantic 2.14.2 | Integrado | 06/11; posteriormente #73 |
| [#59](https://github.com/GustavoDMentz/Sus-Explorer/pull/59) | Descoberta de ZIPs mensais do OpenDataSUS | Integrado | 14/11; página do portal + HEAD no S3, somente leitura. A versão inicial usava a API CKAN, que o portal não expõe mais |
| [#60](https://github.com/GustavoDMentz/Sus-Explorer/pull/60) | Teste temporal legado para o fluxo RAG | Integrado | 08/11, na branch de revisão da migração; chegou à `master` pelo #66 |
| [#61](https://github.com/GustavoDMentz/Sus-Explorer/pull/61) | psycopg-binary 3.3.8 | Fechado sem merge | 14/11; falhava no CI isolado (o binary fixa o psycopg); substituído pelo #67 |
| [#62](https://github.com/GustavoDMentz/Sus-Explorer/pull/62) | google-genai 3.0.0 | Fechado sem merge | 14/11; dependência removida de `requirements.txt` pelo #66 |
| [#63](https://github.com/GustavoDMentz/Sus-Explorer/pull/63) | psycopg 3.3.8 | Fechado sem merge | 14/11; mesmo problema do #61; substituído pelo #67 |
| [#64](https://github.com/GustavoDMentz/Sus-Explorer/pull/64) | pandas 3.1.1 | Integrado | 14/11 |
| [#65](https://github.com/GustavoDMentz/Sus-Explorer/pull/65) | PyArrow 26.0.1 | Integrado | 14/11; usado apenas pelas ferramentas de migração |
| [#66](https://github.com/GustavoDMentz/Sus-Explorer/pull/66) | Migração para PostgreSQL, Ollama e RAG verificável | Integrado | 14/11; reaplica o trabalho de Gabriel Andrade revertido em 08/11. Migração incompleta: ver diário |
| [#67](https://github.com/GustavoDMentz/Sus-Explorer/pull/67) | psycopg e psycopg-binary 3.3.8 | Integrado | 14/11; junta #61 e #63 |
| [#68](https://github.com/GustavoDMentz/Sus-Explorer/pull/68) | SHA-256 não é CPF na redação | Integrado | 14/11; corrige falha intermitente (~4,4% dos hashes) na proveniência |
| [#69](https://github.com/GustavoDMentz/Sus-Explorer/pull/69) | README com PostgreSQL, Ollama e descoberta | Integrado | 15/11 |
| [#70](https://github.com/GustavoDMentz/Sus-Explorer/pull/70) | psycopg 3.3.9 | Fechado sem merge | 20/11; substituído pelo #74 |
| [#71](https://github.com/GustavoDMentz/Sus-Explorer/pull/71) | psycopg-binary 3.3.9 | Fechado sem merge | 20/11; substituído pelo #74 |
| [#72](https://github.com/GustavoDMentz/Sus-Explorer/pull/72) | Streamlit 1.67.0 | Integrado | 20/11 |
| [#73](https://github.com/GustavoDMentz/Sus-Explorer/pull/73) | Pydantic 2.14.3 | Integrado | 20/11 |
| [#74](https://github.com/GustavoDMentz/Sus-Explorer/pull/74) | psycopg e psycopg-binary 3.3.9 | Integrado | 20/11; junta #70 e #71 |

## Convenções para os próximos PRs

1. **Estado:** declarar explicitamente `proposta`, `implementado na branch`, `validado` ou `integrado à master`. Nunca marcar checklist inicial como atual sem revisão.
2. **Motivação e ameaça:** descrever o comportamento que muda e, para segurança, o que um atacante com a capacidade relevante conseguiria fazer.
3. **Escopo:** listar arquivos/camadas alterados e invariantes científicos preservados; separar UI, serviço, dados e administração.
4. **Evidência:** informar comandos, ambiente, número de testes e skips, CI ou ausência de execução. Diferenciar mocks, PostgreSQL descartável e serviços reais.
5. **Risco residual:** dizer o que o PR **não** protege, sobretudo credenciais, sessões, privilégios e dados brutos.
6. **Integração:** PR draft não é entrega. Atualizar README e diário quando uma mudança altera operação; não apagar documentação histórica.
