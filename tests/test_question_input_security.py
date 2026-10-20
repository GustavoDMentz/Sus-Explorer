"""Reject malformed or oversized input before LLM or remote access."""
import pytest

from sus_explorer.service import SUSExplorer


@pytest.mark.parametrize("question", ["", "  ", None, 123])
def test_reject_empty_or_non_string_without_llm(question):
    explorer = object.__new__(SUSExplorer)
    with pytest.raises(ValueError):
        explorer.ask(question)


@pytest.mark.parametrize("question", ["x" * 4097, "á" * 2049])
def test_reject_oversized_input_without_llm(question):
    explorer = object.__new__(SUSExplorer)
    with pytest.raises(ValueError, match="4096-byte"):
        explorer.ask(question)


def test_accept_boundary_size_before_planning():
    class PlannerReached(Exception):
        pass

    class FakeLLM:
        def plan(self, question):
            assert len(question.encode("utf-8")) == 4096
            raise PlannerReached

    explorer = object.__new__(SUSExplorer)
    explorer.llm = FakeLLM()
    with pytest.raises(PlannerReached):
        explorer.ask("x" * 4096)
