"""The UI must not promise more privacy than the code guarantees."""
from pathlib import Path

APP = (Path(__file__).parents[2] / "app.py").read_text("utf-8")


def test_ui_does_not_claim_that_no_microdata_is_ever_sent():
    assert "Nenhum microdado individual é enviado" not in APP


def test_ui_states_that_only_aggregates_reach_the_model_and_warns_about_small_counts():
    assert "apenas resultados agregados" in APP
    assert "Contagens muito pequenas" in APP
