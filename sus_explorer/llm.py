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
  "missing": ["year"],
  "clarification_question": "De qual ano?",
  "operation": "count",
  "year": null,
  "month": 5,
  "uf": "RS",
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

