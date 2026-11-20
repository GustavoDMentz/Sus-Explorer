import pytest

from sus_explorer.service import SUSExplorer


class StopHere(Exception):
    pass


class FakeLLM:
    def __init__(self):
        self.seen = None

    def plan(self, question):
        self.seen = question
        raise StopHere


def explorer():
    ex = SUSExplorer.__new__(SUSExplorer)
    ex.llm = FakeLLM()
    return ex


def test_zero_width_and_control_characters_are_removed_before_planning():
    ex = explorer()
    with pytest.raises(StopHere):
        ex.ask("Quantas​ doses\x00 no RS?")
    assert ex.llm.seen == "Quantas doses no RS?"


def test_nfkc_folds_lookalikes():
    ex = explorer()
    with pytest.raises(StopHere):
        ex.ask("ＲＳ")  # fullwidth
    assert ex.llm.seen == "RS"


@pytest.mark.parametrize("question", ["", "   ", "​​", "\x00"])
def test_questions_that_are_empty_after_cleaning_are_rejected(question):
    with pytest.raises(ValueError, match="non-empty"):
        explorer().ask(question)
