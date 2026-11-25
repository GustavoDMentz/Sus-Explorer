# Consultas analíticas e semântica

## Métrica suportada

O sistema conta eventos de doses/registros do SI-PNI. Não há identidade de pessoa persistida, denominador populacional, produção ambulatorial, atendimento, procedimento ou valor financeiro. Perguntas sobre esses conceitos são recusadas antes do planner para impedir uma contagem semanticamente incorreta.

Filtros disponíveis incluem competência, UF do estabelecimento, município do estabelecimento, vacina, sexo e faixa etária. Idade é apresentada em faixas de cinco anos; células pequenas são suprimidas conforme [privacy.md](privacy.md).

## Integridade da contagem

- `co_documento` é a identidade dentro da origem/partição;
- duplicidade dentro do mesmo arquivo impede `SUCCESS`;
- o executor atravessa uma única observação por registro e run;
- somente snapshots completos e reconciliados entram na consulta;
- registro removido em republicação não permanece na contagem atual;
- partição ausente permanece `null`/indisponível, nunca zero presumido;
- a data de aplicação deve pertencer à competência importada;
- geografia representa o estabelecimento, não residência.

Reutilização do mesmo `co_documento` em competências diferentes é sinalizada pela auditoria semântica e precisa ser investigada contra a fonte antes de qualquer deduplicação transversal.

## Séries e comparações

O intervalo mensal é inclusivo e limitado a 36 meses. MoM compara meses adjacentes; YoY compara o mesmo mês do ano anterior. Diferenças não atravessam lacunas e o modelo não recalcula resultados.

- primeira diferença: mudança do volume mensal;
- segunda diferença: mudança da primeira diferença;
- terceira diferença: mudança da segunda diferença;
- YoY: comparação separada com `t-12`, não derivada mensal.

Essas métricas não comprovam causalidade, sazonalidade, significância epidemiológica ou cobertura vacinal. Latência mede dias entre aplicação e entrada no RNDS quando a data é válida; não mede qualidade clínica.
