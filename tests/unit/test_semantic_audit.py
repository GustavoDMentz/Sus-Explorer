from sus_explorer.data.persistence.semantic_audit import CHECKS, audit


class FakeDatabase:
    def __init__(self, counts):
        self.counts = iter(counts)
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        value = next(self.counts)
        return type("Result", (), {"fetchone": lambda self: {"n": value}})()


def test_semantic_audit_classifies_errors_and_cross_partition_warning():
    db = FakeDatabase([0, 1, 0, 0, 0, 2])
    result = audit(db)
    assert result["errors"] == 1
    assert result["warnings"] == 1
    assert "not unique patients" in result["metric"]
    assert len(db.statements) == len(CHECKS)


def test_semantic_audit_uses_current_reconciled_successful_snapshots():
    for _name, _severity, statement in CHECKS:
        assert "status='SUCCESS'" in statement
        assert "source_rows" in statement
        assert "datasus_raw_record_observations" in statement
