from __future__ import annotations

import json
import re
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
  "metric": "doses", "granularity": "monthly", "comparison": "mom"|"yoy"}.
- "interanual", "YoY", "mesmo mês do ano anterior", "em relação ao ano anterior"
  → comparison="yoy", order=1 se nenhuma ordem de diferença finita foi solicitada.
- "mês anterior", "mensal" → comparison="mom". Não troque automaticamente por sazonalidade.
- YoY compara t com t-12 meses de calendário; é independente de delta_1/2/3.
  O backend consultará explicitamente a referência histórica, sem ampliar o período principal.
- "variação mensal", "crescimento mensal" → order=1.
- "acelerando", "aceleração", "desaceleração", "crescimento perdendo força" → order=2.
- "mudança da aceleração", "terceira diferença" → order=3.
- O período usa start_year/start_month/end_year/end_month.
- Intervalos de anos inteiros, como "de 2024 a 2025", "entre 2024 e 2025" ou
  "2024 até 2025", significam janeiro do primeiro ano a dezembro do último,
  inclusive. Não peça meses adicionais: é uma convenção de calendário.
- Meses explicitamente solicitados sempre prevalecem. "Janeiro a junho de
  2024 em relação a 2025" pede comparação dos mesmos meses em anos diferentes,
  não um intervalo contínuo nem anos inteiros. Para a comparação adjacente
  2025 versus 2024, use janeiro-junho/2025 como período principal e comparison="yoy".
  Se a direção da comparação ou os anos de referência forem ambíguos, peça esclarecimento.
  Comparações com anos não adjacentes não são YoY e exigem esclarecimento.
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
- yoy_delta compara doses com o mesmo mês do ano anterior; yoy_pct tem unidade %.
- YoY não é uma derivada mensal e não confirma nem elimina sazonalidade. Não recalcule números.
- delta_3 descreve mudança na segunda diferença, não inflexão confirmada.
- Use interpretation como descrição local daquele mês/janela. Não conclua tendência
  global apenas com um sinal isolado. Respeite ordem, fórmula, unidade e intervalo.
- Não afirme causalidade, anomalia estatística, significância epidemiológica ou
  ponto de inflexão confirmado apenas por diferenças finitas.
- Não suavize nem atravesse lacunas; valores indisponíveis não são zero.
"""


PLANNER_MAX_OUTPUT_TOKENS = 8192
PLANNER_MAX_RESPONSE_BYTES = 16384


def planner_output_schema() -> dict:
    """Inline the small transport schema; domain validation stays in QueryPlan."""
    original = QueryPlan.model_json_schema()
    definitions = original.get("$defs", {})
    def inline(value):
        if isinstance(value, list):
            return [inline(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return inline(definitions[value["$ref"].split("/")[-1]])
        result = {key: inline(item) for key, item in value.items()
                  if key not in ("$defs", "title", "default")}
        if "const" in result:
            result["enum"] = [result.pop("const")]
        return result
    schema = inline(original)
    for name, lower, upper in (
        ("start_year", 2020, 2100), ("end_year", 2020, 2100),
        ("start_month", 1, 12), ("end_month", 1, 12),
    ):
        for option in schema["properties"][name]["anyOf"]:
            if option.get("type") == "integer":
                option.update(minimum=lower, maximum=upper)
    return schema


_MONTH_OR_SUBYEAR = re.compile(
    r"\b(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|"
    r"outubro|novembro|dezembro|mês|mes|meses|trimestre|semestre|dia|dias)\b|"
    r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b|\b\d{4}[-/]\d{1,2}\b", re.IGNORECASE)
_YEAR_RANGE = re.compile(
    r"\b(?:de\s+)?(20\d{2}|2100)\s+(?:a|até)\s+(20\d{2}|2100)\b|"
    r"\bentre\s+(20\d{2}|2100)\s+e\s+(20\d{2}|2100)\b", re.IGNORECASE)


def apply_whole_year_interval(question: str, plan: QueryPlan) -> QueryPlan:
    """Expand an explicit year-only range, never a comparison/monthly subrange."""
    if plan.operation not in ("temporal", "timeseries") or _MONTH_OR_SUBYEAR.search(question):
        return plan
    matches = list(_YEAR_RANGE.finditer(question))
    if len(matches) != 1:
        return plan
    match = matches[0]
    start, end = (int(value) for value in match.groups() if value is not None)
    if not 2020 <= start <= end <= 2100:
        return plan
    payload = plan.model_dump()
    payload.update(start_year=start, start_month=1, end_year=end, end_month=12)
    date_fields = {"period", "year", "month", "start_year", "start_month", "end_year", "end_month"}
    payload['missing'] = [field for field in payload['missing'] if field not in date_fields]
    # Only release a clarification explicitly attributed to missing dates.
    if plan.status == 'needs_clarification' and plan.missing and not payload['missing']:
        payload.update(status='ready', clarification_question=None)
    return QueryPlan.model_validate(payload)


class PlannerResponseError(ValueError):
    """Invalid model output; never include model text or SDK details."""

    code = "INVALID_PLANNER_RESPONSE"

    def __init__(self):
        super().__init__("Não foi possível gerar um plano válido. Tente reformular a pergunta.")


class GeminiAnalyst:
    def __init__(self):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        self.client = genai.Client(
            api_key=settings.gemini_api_key
        )
        self.model = settings.gemini_model

    def plan(self, q: str) -> QueryPlan:
        # A single JSON-mode retry escapes a failing constrained decoder/SDK
        # parse. It receives only the same question and public plan contract,
        # never generated garbage, query results or source data.
        for structured in (True, False):
            try:
                return apply_whole_year_interval(q, self._plan_attempt(q, structured=structured))
            except PlannerResponseError:
                if not structured:
                    raise
        raise PlannerResponseError()

    def _plan_attempt(self, q: str, *, structured: bool) -> QueryPlan:
        schema = planner_output_schema()
        prompt = f"{PLANNER}\n\nPergunta: {q}"
        if not structured:
            prompt += ("\nRetorne somente um objeto JSON compacto conforme este contrato. "
                       "Omita campos não utilizados; nunca repita dígitos ou faça cálculos.\n"
                       + json.dumps(schema, ensure_ascii=False))
        try:
            r = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    thinking_config=(types.ThinkingConfig(thinking_level="LOW")
                                     if self.model.startswith("gemini-3") else None),
                    max_output_tokens=PLANNER_MAX_OUTPUT_TOKENS,
                    response_mime_type="application/json",
                    response_json_schema=schema if structured else None,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            candidates = getattr(r, "candidates", None)
            if isinstance(candidates, list) and any(
                getattr(candidate, "finish_reason", None) not in (None, "STOP")
                for candidate in candidates
            ):
                raise PlannerResponseError()
            text = getattr(r, "text", None)
            if isinstance(text, str) and len(text.encode("utf-8")) > PLANNER_MAX_RESPONSE_BYTES:
                raise PlannerResponseError()
            parsed = getattr(r, "parsed", None)
            if parsed is not None:
                return QueryPlan.model_validate(parsed)
            if not isinstance(text, str) or not text.strip():
                raise PlannerResponseError()
            return QueryPlan.model_validate_json(text)
        except ValueError:
            # Includes SDK json.loads integer-limit failures before r is returned,
            # plus local Pydantic validation. Keep Python's integer guard enabled.
            raise PlannerResponseError() from None

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

