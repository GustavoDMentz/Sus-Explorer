from scripts.evaluate_rag import DEFAULT_CASES, classify_payload, load_cases, objective_checks


def test_rag_evaluation_covers_required_routing_classes():
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) >= 10
    intents = {case["expected_intent"] for case in cases}
    assert {"document", "hybrid", "clarification", "out_of_scope",
            "insufficient_evidence"} <= intents


def test_objective_rag_checks_reject_forbidden_claims_and_bad_citations():
    case = load_cases(DEFAULT_CASES)[0]
    payload = {"plan": {"operation": "document"}, "answer": "DataSUS privado",
               "sources": [{"citationId": "sem-trecho"}]}
    checks = objective_checks(case, payload, 0.1)
    assert checks["forbidden_terms_absent"] is False
    assert checks["citations_verifiable"] is False
    assert checks["required_terms_in_cited_evidence"] is False


def test_rag_payload_classification_distinguishes_scope_and_missing_evidence():
    assert classify_payload({"planner_source": "scope_guard"}) == "out_of_scope"
    assert classify_payload({"plan": {"operation": "document"},
                             "answer": "Não encontrei trechos documentais suficientes para responder a essa parte. O resultado analítico, quando disponível, está separado e foi calculado no PostgreSQL."}) == "insufficient_evidence"
