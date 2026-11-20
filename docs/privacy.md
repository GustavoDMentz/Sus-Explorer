# Privacidade e controle de divulgação

Os dados de origem (SI-PNI/OpenDATASUS) são públicos, mas combinar município, idade, sexo, vacina e mês pode isolar uma única pessoa. O SUS Explorer aplica o controle abaixo a **todo número mostrado ao usuário** (implementação em `sus_explorer/disclosure.py`, aplicada em `PostgresQueryExecutor.execute`).

## Regras

| Regra | Efeito |
|---|---|
| **Limiar 5** | Uma contagem positiva menor que 5 não é mostrada; aparece como "menos de 5". Zero é mostrado: não identifica ninguém. |
| **Supressão complementar** | Um total nunca é mostrado se a subtração dos valores visíveis revelaria uma célula suprimida. Em agrupamentos, se o que fica oculto (células suprimidas ou cortadas pelo `top_n`) soma de 1 a 4, o total também é ocultado. |
| **Latência** | Com menos de 5 registros válidos, mediana, P90 e P95 são suprimidos (um percentil de poucos registros é um valor individual). |
| **Faixas etárias** | O filtro de idade é ampliado para faixas de 5 anos (por exemplo, 87 vira 85–89) e o agrupamento por idade usa faixas, nunca idades exatas. Um aviso informa o ajuste. |
| **Séries mensais** | Um mês suprimido vira observação indisponível. A regra existente de não calcular diferenças atravessando lacunas impede reconstruí-lo pelos deltas. |

O limiar pode ser **aumentado** com `SUS_MIN_CELL_COUNT` (valor inteiro, mínimo 5), nunca reduzido. Cada resposta registra em `provenance.disclosure_control` o limiar e quantas células foram suprimidas, e a interface exibe um aviso.

## Risco residual

- **Consultas sucessivas.** Duas consultas diferentes podem ser combinadas: o total de um município menos o total do mesmo município sem uma faixa etária revela a diferença. As faixas de 5 anos e a supressão tornam isso mais caro, mas não impossível. Quem expõe o app a terceiros deve limitar a taxa de consultas por usuário (hoje não há autenticação nem limite).
- **Contexto externo.** Quem sabe que uma pessoa se vacinou em certo lugar e mês pode usar um total grande para confirmar a informação que já tem. O controle protege contra a descoberta, não contra a confirmação.
- **Resultados históricos** (`analytical_result_versions`) guardam os agregados já com a supressão aplicada.

## Quando relaxar o controle

Não relaxe sem decisão registrada. Para análises que exijam contagens pequenas, use os dados oficiais diretamente, sob as regras do órgão de origem.
