"""Regression tests for timeseries source metadata fingerprints."""
from types import SimpleNamespace

from sus_explorer.pni import PNIRemote
from sus_explorer.schemas import QueryPlan


class FakeDataset:
    def __init__(self, doses):
        self.doses = doses

    def count_rows(self, filter=None):
        return self.doses

    def get_fragments(self):
        return iter((object(),))


def _remote(datasets, fingerprint):
    remote = object.__new__(PNIRemote)
    remote.dataset = lambda year, month, uf: datasets[(year, month)]
    remote.base_filter = lambda ds, plan: None
    remote.post_cols = lambda ds, plan: []
    remote.source_fingerprint = lambda observed: fingerprint(observed)
    return remote


def _plan():
    return QueryPlan(operation="timeseries", uf="RS", start_year=2026,
                     start_month=1, end_year=2026, end_month=3)


def test_timeseries_fingerprint_tracks_only_consulted_datasets():
    jan, mar = FakeDataset(10), FakeDataset(30)
    seen = []

    def fingerprint(observed):
        seen.extend(observed)
        return "a" * 64

    remote = _remote({(2026, 1): jan, (2026, 3): mar}, fingerprint)

    def dataset(year, month, uf):
        if month == 2:
            raise FileNotFoundError("missing")
        return {(2026, 1): jan, (2026, 3): mar}[(year, month)]

    remote.dataset = dataset
    result = remote.timeseries(_plan())

    assert result.data["rows"] == [
        {"period": "2026-01", "doses": 10},
        {"period": "2026-03", "doses": 30},
    ]
    assert [(y, m) for y, m, _ in seen] == [(2026, 1), (2026, 3)]
    assert result.provenance["source_metadata_sha256"] == "a" * 64
    assert result.provenance["missing_partitions"] == ["ano=2026/mes=02/uf=RS"]


def test_timeseries_unavailable_fingerprint_is_omitted():
    remote = _remote({(2026, 1): FakeDataset(1),
                      (2026, 2): FakeDataset(2),
                      (2026, 3): FakeDataset(3)}, lambda observed: None)
    result = remote.timeseries(_plan())
    assert "source_metadata_sha256" not in result.provenance
    assert result.provenance["missing_partitions"] == []
    assert len(result.data["rows"]) == 3
