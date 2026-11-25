import pytest

from sus_explorer.diagnose import StorageBudget


def test_storage_budget_separates_operational_categories():
    budget = StorageBudget(temporary_gib=8, postgres_gib=100, indexes_gib=20,
                           wal_gib=25, margin_gib=30)
    assert budget.total_gib == 183
    assert budget.complete is True
    budget.validate()


def test_storage_budget_rejects_negative_estimates():
    with pytest.raises(ValueError, match="negativas"):
        StorageBudget(wal_gib=-1).validate()


def test_storage_budget_marks_unknown_categories_incomplete():
    budget = StorageBudget(temporary_gib=7.1)
    assert budget.total_gib == 7.1
    assert budget.complete is False
