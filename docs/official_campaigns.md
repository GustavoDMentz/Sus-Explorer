# Comparação entre campanhas oficiais — MVP de influenza / RS

## Resultado da verificação prévia (08/10/2026)

**O calendário pode ser exibido; os volumes das campanhas ainda não podem ser
comparados com o backend atual.** A seção Streamlit registra essa indisponibilidade,
em vez de utilizar dados mensais como se fossem totais oficiais de campanhas.
Não há consulta adicional, alteração do intervalo principal ou mudança de método
MoM/YoY. Nenhum gráfico numérico de campanha foi habilitado com dados reais.

O catálogo `sus_explorer/analytics/campaign_catalog.json`, versão
`2026-10-08.1`, contém exclusivamente dois documentos oficiais verificados:

| Campanha aplicável ao RS | Início previsto | Fim previsto | Fonte oficial |
| --- | --- | --- | --- |
| Influenza 2023, nacional | 10/04/2023 | 31/05/2023 | [Informe MS 2023](https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/c/calendario-nacional-de-vacinacao/arquivos/informe-tecnico-operacional-de-vacinacao-contra-a-influenza-2023/view) |
| Influenza 2024, Nordeste/Centro-Oeste/Sul/Sudeste | 25/03/2024 | 31/05/2024 | [Informe MS 2024](https://www.gov.br/saude/pt-br/vacinacao/informes/estrategia-de-vacinacao-influenza-2024/view) |

O PDF de 2023 informa as datas na introdução e, na seção 13/13.1, determina
registro consolidado no módulo específico da campanha. Não há reconciliação
demonstrada desse módulo com os microdados lidos pelo projeto. O documento de
2024 informa seu calendário na seção 3.2. Essas fontes comprovam calendários
previstos, não o cronograma efetivamente adotado em cada município, a atribuição
de cada dose à campanha ou todas as prorrogações posteriores.

Datas de publicação são distintas das datas das campanhas: a página de 2023
mostra atualização de 15/03/2023, sem data explícita de publicação (campo null,
com nota); a de 2024 informa publicação de 16/03/2024 e atualização de
26/03/2026. A edição eletrônica de 2024 é a primeira; a de 2023 não foi identificada
explicitamente. URLs do PDF e dos metadados, localizadores, abrangência real e
escopo de aplicação limitado ao RS estão registrados individualmente.

O catálogo é versionado no Git e validado contra duplicidades, datas invertidas,
escopo e URLs HTTPS do Ministério. A comparação registra versão, verificação e
SHA-256 do catálogo. Não há hash dos PDFs nem cópia binária arquivada: URLs podem
ser atualizadas pelo órgão. Alterações do catálogo exigem nova verificação,
incremento de versão e revisão; `verified_on` não é promessa de atualização contínua.

## Limitações dos dados disponíveis

`PNIRemote.timeseries` soma registros em partições ano/mês/UF e retorna `period`
e `doses`. Não agrega pela coluna `dt_vacina` e não certifica completude por dia,
pertencimento à campanha nem equivalência com o módulo consolidado. O cubo mensal
também perde a resolução diária. Embora `dt_vacina` seja usada na análise de
latência, a presença da coluna não demonstra que os registros da campanha estejam
completos ou em um sistema equivalente.

Neste ambiente não havia credenciais R2 nem cubo local, portanto nenhum volume real
foi consultado ou validado. Isso é diferente da limitação estrutural identificada
no contrato do backend. Não se afirma que dados adequados não existam no MS:
[a página oficial dos painéis](https://www.gov.br/saude/pt-br/composicao/seidigi/demas/campanhas-de-vacinacao/vacinacao-contra-a-influenza)
apresenta dados de campanhas por residência e ocorrência. Não foi obtida nem
auditada uma extração histórica compatível com todas as dimensões para este MVP.
Residência e ocorrência não podem ser misturadas silenciosamente.

Maio é o único mês inteiro comum aos calendários de 2023 e 2024. Abril/2023 e
março/2024 são parciais e não podem ser rateados. Mesmo maio **não habilita a
aproximação mensal**, pois a adequação da fonte de volumes permanece não verificada.
A janela de 60 dias ultrapassa o fim previsto de 2023; não é encurtada silenciosamente.

## Implementação e regras para dados adequados futuros

`analytics/campaigns.py` produz resultado independente `campaign_comparison`;
não acrescenta operação ao planejador nem modifica QueryPlan, consultas, métricas
ou resultados MoM/YoY. O caminho atual da interface fornece `series=None` e recebe
`status=unavailable`, linhas e comparações vazias e razões estruturadas. Não
consome séries inseridas arbitrariamente no payload como evidência verificada.

O mesmo módulo possui cálculo puro, testado com agregados sintéticos, para uma
futura extração auditada (`VerifiedCampaignSeries`). **Não existe adaptador diário
ou de módulo consolidado ativo nesta entrega.** Atestações de completude e escopo
não são inferidas de partições presentes: um adaptador futuro precisa comprovar
sua origem, data de aplicação, sistema de registro, cobertura e geografia, com
fonte oficial de verificação. Flags no contrato não substituem essa auditoria.

Filtros de UF, município, código/texto de imunobiológico, idade e sexo precisam
coincidir integralmente. Dia/agrupamento são rejeitados, não descartados. Filtros
extras futuros exigem extensão explícita do contrato antes de serem suportados.
Códigos isolados não são adivinhados; a interface exige influenza explicitamente.

Para cada dia `d` contado desde o início previsto (dia 1 = início):

`C(d) = sum(y(i), i=1..d)` e `diferença(d) = C_mais_recente(d) - C_anterior(d)`.

Uma dose observada, inclusive um zero explicitamente retornado por fonte adequada,
é DIRECT. Acumulados e diferenças são DERIVED; o calendário documental é ENRICHED.
Dia ausente ou nulo torna seu acumulado e os posteriores indisponíveis; nunca
preencher com zero, reiniciar acumulado após lacuna ou extrapolar. O gráfico puro
mostra somente o prefixo calculável em ambas as campanhas, com tamanho disponível
e flag `window_complete` no resultado. A tabela mantém observações posteriores
à lacuna, mas seus acumulados continuam null. Inteiros preservam precisão exata;
números fora da representação segura do navegador permanecem no resultado e não
geram barras aproximadas.

Uma extração mensal adequada pode comparar exclusivamente meses calendários
inteiros comuns, com rótulo de **aproximação mensal**. Não há eixo de dias, rateio,
curva diária ou afirmação de equivalência aos primeiros 30/60 dias. Os acumulados
mensais referem-se apenas aos meses selecionados, nunca ao total da campanha.

## Interface e validação

`streamlit_campaigns.py` adiciona a seção própria após as análises existentes.
Mostra os dois calendários e links oficiais próximos à área do gráfico; usa a
paleta central de proveniência e mantém rótulos acessíveis. As opções de 30 dias,
60 dias e aproximação mensal expõem as razões de indisponibilidade. O download
contém catálogo, filtros e limitações, sem inventar volumes. Não existe chamada ao
LLM, nova leitura R2 ou troca automática de comparação ao alterar a seleção.

Os testes cobrem calendário, fontes e metadados, limites das janelas, validação
de séries, nulos/lacunas, zeros observados, precisão, filtros/geografia/sistemas
incompatíveis, comparação por dias decorridos e mensal sem rateio, além de
Streamlit AppTest com fontes clicáveis, ausência de consultas e preservação do
resultado original. Valores dos testes de cálculo são sintéticos; não são resultados
das campanhas reais. A suíte existente continua cobrindo Δ1–Δ3, MoM e YoY.

Sem novas dependências, serviços, frontend, alteração de armazenamento ou migrations.
Comparações descritivas não demonstram desempenho, cobertura ou eficácia, nem
atribuem diferenças à campanha ou a qualquer causa específica.

Validação final: `python -m pytest tests -q -rs` — **380 aprovados, 7 PostgreSQL
pulados por ausência de banco descartável, 0 falhos**; 28 novos casos.
`git diff --check` aprovado. Interface validada com AppTest, sem captura de
navegador. Não foram feitas consultas reais Gemini/R2 nem auditoria de doses reais.
