from unittest.mock import Mock

import pytest

from sus_explorer.scope import unsupported_scope
from sus_explorer.service import SUSExplorer


@pytest.mark.parametrize("question,label", [
    ("Qual foi a produção ambulatorial no RS?", "produção"),
    ("Quantos pacientes únicos foram vacinados?", "pacientes"),
    ("Qual foi o valor financeiro dos procedimentos?", "financeiros"),
    ("Qual é a cobertura vacinal?", "cobertura"),
])
def test_unsupported_semantics_are_detected(question, label):
    assert label in unsupported_scope(question)


def test_dose_event_question_stays_in_scope():
    assert unsupported_scope("Quantas doses foram registradas no RS em maio de 2026?") is None


def test_scope_guard_runs_before_planner_and_database():
    explorer = SUSExplorer.__new__(SUSExplorer)
    explorer.llm = Mock()
    explorer.executor = Mock()
    response = explorer.ask("Quantos pacientes únicos foram vacinados no RS em 2026?")
    assert response["needs_clarification"] is True
    assert "eventos de doses" in response["clarification_question"]
    explorer.llm.plan.assert_not_called()
    explorer.executor.execute.assert_not_called()
