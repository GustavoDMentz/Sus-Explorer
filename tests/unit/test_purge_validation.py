import pytest

from sus_explorer.data.persistence.purge import PurgeError, purge

GOOD = "motivo com tamanho suficiente"


class NoDb:
    def __getattr__(self, name):
        raise AssertionError("o banco não deve ser acessado com argumentos inválidos")


@pytest.mark.parametrize("kwargs", [
    {"scope": "partition", "partition": "ano=2026/mes=05/uf=RS", "reason": "curto"},
    {"scope": "partition", "partition": "ano=2026/mes=05/uf=RS", "reason": "x" * 501},
    {"scope": "partition", "partition": "2026-05-RS", "reason": GOOD},
    {"scope": "partition", "partition": "ano=2026/mes=13/uf=RS", "reason": GOOD},
    {"scope": "partition", "partition": "ano=2026/mes=05/uf=rs", "reason": GOOD},
    {"scope": "partition", "partition": "ano=2026/mes=05/uf=RS'; DROP TABLE x;--", "reason": GOOD},
    {"scope": "partition", "partition": None, "reason": GOOD},
    {"scope": "partition", "partition": "ano=2026/mes=05/uf=RS", "older_than_days": 5, "reason": GOOD},
    {"scope": "old_revisions", "older_than_days": 0, "reason": GOOD},
    {"scope": "old_revisions", "older_than_days": None, "reason": GOOD},
    {"scope": "old_revisions", "older_than_days": 30, "partition": "ano=2026/mes=05/uf=RS", "reason": GOOD},
    {"scope": "everything", "reason": GOOD},
])
def test_invalid_arguments_are_rejected_before_touching_the_database(kwargs):
    with pytest.raises(PurgeError):
        purge(NoDb(), **kwargs)
