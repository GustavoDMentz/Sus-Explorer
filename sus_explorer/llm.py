from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from .config import settings
from .schemas import QueryPlan


PLANNER = """
Você é o planner de um explorador de dados públicos do SI-PNI.

REGRA CRÍTICA:
NUNCA invente ano, mês, dia, UF, município, vacina ou período.

Se uma informação necessária estiver ausente, use:

status = "needs_clarification"

e preencha:
- missing
- clarification_question

Exemplos:

Pergunta:
"Quantas doses foram aplicadas em Canoas em maio?"

Resposta esperada:
{
  "status": "needs_clarification",
  "missing": ["year", "uf"],
  "clarification_question": "De qual ano e UF?",
  "operation": "count",
  "year": null,
  "month": 5,
  "uf": null,
  "municipality_name": "Canoas"
}

Pergunta:
"Quantas doses foram aplicadas em Canoas em 2026?"

Isso NÃO significa mês ausente.
O usuário pediu o ano inteiro.

Pergunta:
"Quantas doses foram aplicadas em Canoas?"

Resposta:
{
  "status": "needs_clarification",
  "missing": ["period"],
  "clarification_question": "Qual período você deseja consultar?"
}

Nunca escolha um ano por conta própria.
Nunca complete informação ausente por inferência ou conveniência.

ANÁLISE TEMPORAL DERIVADA:
- Use operation="temporal" e temporal_analysis={"order": 1|2|3,
  "metric": "doses", "granularity": "monthly"}.
- "variação mensal", "crescimento mensal" → order=1.
- "acelerando", "aceleração", "desaceleração", "crescimento perdendo força" → order=2.
- "mudança da aceleração", "terceira diferença" → order=3.
- O período usa start_year/start_month/end_year/end_month, todos explícitos.
  "ao longo de 2026" representa janeiro a dezembro de 2026, sem observações extras.
  "está acelerando?" sem período exige esclarecimento; nunca escolha meses recentes.
- UF é obrigatória, mesmo se município foi citado. Não deduza UF por geografia.
- Vacina textual explícita usa vaccine_text; não invente vaccine_code.
- Sem ordem identificável, período ou UF, peça esclarecimento com missing.
- Somente doses/registros mensais; cobertura, taxas populacionais, granularidade
  diária/anual, smoothing e anomalias não são suportados nesta operação.
- Não faça cálculos, não gere SQL nem corrija resultados. Python calculará diferenças.
- Operações count/group/timeseries/latency continuam com seus contratos anteriores.

Exemplo temporal completo:
"Como mudou a aceleração da vacinação no RS ao longo de 2026?"
{"status":"ready","operation":"temporal","uf":"RS","start_year":2026,
 "start_month":1,"end_year":2026,"end_month":12,
 "temporal_analysis":{"order":2,"metric":"doses","granularity":"monthly"}}

"A vacinação contra influenza no RS está acelerando?"
{"status":"needs_clarification","operation":"temporal","uf":"RS",
 "vaccine_text":"influenza","missing":["start_year","start_month","end_year","end_month"],
 "clarification_question":"Qual intervalo mensal você deseja analisar?",
 "temporal_analysis":{"order":2,"metric":"doses","granularity":"monthly"}}

"Qual foi a variação mensal das doses em Porto Alegre?"
{"status":"needs_clarification","operation":"temporal","municipality_name":"Porto Alegre",
 "missing":["uf","start_year","start_month","end_year","end_month"],
 "clarification_question":"Qual UF e intervalo mensal você deseja analisar?",
 "temporal_analysis":{"order":1,"metric":"doses","granularity":"monthly"}}
"""


ANSWER = """
Explique em português claro usando SOMENTE o resultado calculado.

Regras:
- não invente números, causalidade, cobertura vacinal ou conclusões clínicas;
- diga "doses/registros", não "pessoas", salvo se houver contagem explícita;
- microdados não foram enviados ao modelo;
- para imunobiológicos, preserve a sigla oficial;
- quando "definition" estiver preenchida, apresente-a junto à sigla;
- formato preferido: "INF3 — Vacina influenza trivalente";
- nunca expanda uma sigla por memória própria;
- se terminology_conflict=true, não use a definição conflitante;
- não acrescente contexto epidemiológico que não esteja presente no resultado;
- não estime nem complete valores ausentes.

RESULTADOS TEMPORAIS:
- Observações DIRECT são doses/registros mensais; métricas DERIVED são diferenças
  calculadas pelo backend. ENRICHED é informação adicionada de fonte externa,
  não uma observação nem uma diferença; não invente enriquecimento.
- Nunca recalcule, corrija ou substitua números do backend. Preserve null e suas razões.
- delta_1 positiva: volume mensal aumentou; negativa: volume mensal diminuiu.
- delta_2 positiva: variação mensal aumentando; negativa: variação mensal diminuindo.
  Uma segunda diferença negativa NÃO implica necessariamente queda nas doses:
  pode haver crescimento positivo, porém desacelerando.
- delta_3 descreve mudança na segunda diferença, não inflexão confirmada.
- Use interpretation como descrição local daquele mês/janela. Não conclua tendência
  global apenas com um sinal isolado. Respeite ordem, fórmula, unidade e intervalo.
- Não afirme causalidade, anomalia estatística, significância epidemiológica ou
  ponto de inflexão confirmado apenas por diferenças finitas.
- Não suavize nem atravesse lacunas; valores indisponíveis não são zero.
"""


class GeminiAnalyst:
    def __init__(self):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        self.client = genai.Client(
            api_key=settings.gemini_api_key
        )
        self.model = settings.gemini_model

    def plan(self, q: str) -> QueryPlan:
        r = self.client.models.generate_content(
            model=self.model,
            contents=f"{PLANNER}\n\nPergunta: {q}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=QueryPlan,
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                ),
            ),
        )

        if getattr(r, "parsed", None) is not None:
            if isinstance(r.parsed, QueryPlan):
                return r.parsed

            return QueryPlan.model_validate(r.parsed)

        return QueryPlan.model_validate_json(r.text)

    def answer(
        self,
        q: str,
        p: QueryPlan,
        res: Any,
    ) -> str:
        if p.operation == "temporal":
            from .analytics.temporal_query import temporal_answer_payload

            # The public aggregate result carries the full intent/provenance.
            # Free user text and arbitrary metadata are not needed by the explainer.
            payload = temporal_answer_payload(p, res)
        else:
            payload = {
                "question": q,
                "plan": p.model_dump(),
                "result": res.model_dump(),
            }

        r = self.client.models.generate_content(
            model=self.model,
            contents=(
                f"{ANSWER}\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
            config=types.GenerateContentConfig(
                temperature=0.1,
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                ),
            ),
        )

        return r.text

