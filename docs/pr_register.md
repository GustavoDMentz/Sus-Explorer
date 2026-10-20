# Registro de PRs — SUS Explorer (corte: 2026-10-20)

Este índice separa **integrado à master**, **fechado sem merge** e **aberto**. O título/corpo original de um PR é evidência histórica, não necessariamente a descrição do código final. Consulte o diff, os commits e os testes do PR antes de afirmar que uma funcionalidade foi entregue. O diário técnico guarda a cronologia; o README descreve a operação atual.

| PR | Assunto | Estado em 20/10/2026 | Observação |
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
| [#17](https://github.com/GustavoDMentz/Sus-Explorer/pull/17) | Catálogo de campanhas | Aberto | Não integrado |
| [#18](https://github.com/GustavoDMentz/Sus-Explorer/pull/18) | Integração limpa do #11 | Integrado | Sem web abandonada |
| [#19](https://github.com/GustavoDMentz/Sus-Explorer/pull/19) | Integração limpa do #12 | Integrado | Streamlit |
| [#20](https://github.com/GustavoDMentz/Sus-Explorer/pull/20) | Integração limpa do #13 | Integrado | MoM |
| [#21](https://github.com/GustavoDMentz/Sus-Explorer/pull/21) | Integração limpa do #14 | Integrado | Gráficos |
| [#22](https://github.com/GustavoDMentz/Sus-Explorer/pull/22) | Integração limpa do #15 | Integrado | Proveniência |
| [#23](https://github.com/GustavoDMentz/Sus-Explorer/pull/23) | Integração limpa do #16 | Integrado | YoY |
| [#24](https://github.com/GustavoDMentz/Sus-Explorer/pull/24) | google-genai 2.29.0 | Integrado | 20/10 |
| [#25](https://github.com/GustavoDMentz/Sus-Explorer/pull/25) | Pydantic 2.14.1 | Integrado | 20/10 |
| [#26](https://github.com/GustavoDMentz/Sus-Explorer/pull/26) | PyArrow 26 | Aberto | Não integrado; constraints em 25.0.1 |
| [#27](https://github.com/GustavoDMentz/Sus-Explorer/pull/27) | NumPy 2.5.4 | Integrado | 20/10 |
| [#28](https://github.com/GustavoDMentz/Sus-Explorer/pull/28) | README operacional | Integrado | 14/10; anterior a #29–#32 |
| [#29](https://github.com/GustavoDMentz/Sus-Explorer/pull/29) | Feature/g | Integrado | Mudança ampla; descrição original vazia: conferir diff |
| [#30](https://github.com/GustavoDMentz/Sus-Explorer/pull/30) | Planner determinístico | Integrado | Experimental; flag opt-in |
| [#31](https://github.com/GustavoDMentz/Sus-Explorer/pull/31) | BYOK por sessão | Integrado | UI Gemini apenas; R2 compartilhado, apesar do título original |
| [#32](https://github.com/GustavoDMentz/Sus-Explorer/pull/32) | Histórico versionado | Integrado | Checklist inicial do PR ficou desatualizado |
| [#33](https://github.com/GustavoDMentz/Sus-Explorer/pull/33) | Limite de pergunta | Aberto, draft | Testes adicionados; não integrados nem reexecutados aqui |
| [#34](https://github.com/GustavoDMentz/Sus-Explorer/pull/34) | Histórico visual por sessão | Aberto, draft | Não fornece isolamento no banco |

## Convenções para os próximos PRs

1. **Estado:** declarar explicitamente `proposta`, `implementado na branch`, `validado` ou `integrado à master`. Nunca marcar checklist inicial como atual sem revisão.
2. **Motivação e ameaça:** descrever o comportamento que muda e, para segurança, o que um atacante com a capacidade relevante conseguiria fazer.
3. **Escopo:** listar arquivos/camadas alterados e invariantes científicos preservados; separar UI, serviço, dados e administração.
4. **Evidência:** informar comandos, ambiente, número de testes e skips, CI ou ausência de execução. Diferenciar mocks, PostgreSQL descartável e serviços reais.
5. **Risco residual:** dizer o que o PR **não** protege, sobretudo credenciais, sessões, privilégios e dados brutos.
6. **Integração:** PR draft não é entrega. Atualizar README e diário quando uma mudança altera operação; não apagar documentação histórica.
