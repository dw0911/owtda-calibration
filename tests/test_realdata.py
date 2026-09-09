"""Tests for PAMAP2 scientific data identity (Plan §13.2)."""


import pytest

from owtda_cal import realdata
from owtda_cal.identity import H

_A = "a" * 64


def _entries():
    return [
        {"path": f"Protocol/{n}", "size": 10 + i, "file_sha256": _A}
        for i, n in enumerate(realdata.SUBJECT_NAMES)
    ]


class TestValidate:
    def test_accepts_nine_sorted(self):
        out = realdata.validate_entries(_entries())
        assert [e["path"] for e in out] == [
            f"Protocol/{n}" for n in realdata.SUBJECT_NAMES
        ]

    def test_order_insensitive(self):
        rev = list(reversed(_entries()))
        assert realdata.validate_entries(rev) == realdata.validate_entries(_entries())

    def test_wrong_count_rejected(self):
        with pytest.raises(ValueError):
            realdata.validate_entries(_entries()[:8])

    def test_bad_path_rejected(self):
        e = _entries()
        e[0]["path"] = "PAMAP2_Dataset/Protocol/subject101.dat"
        with pytest.raises(ValueError):
            realdata.validate_entries(e)

    def test_missing_keys_rejected(self):
        e = _entries()
        del e[3]["file_sha256"]
        with pytest.raises(ValueError):
            realdata.validate_entries(e)


class TestDatasetHash:
    def test_golden_structure(self):
        entries = _entries()
        expected = H(
            "pamap2_protocol_dataset",
            manifest_entries=realdata.validate_entries(entries),
        )
        assert realdata.dataset_hash(entries) == expected
        assert len(expected) == 64

    def test_stable_and_sensitive(self):
        entries = _entries()
        h0 = realdata.dataset_hash(entries)
        assert h0 == realdata.dataset_hash(_entries())
        e2 = _entries()
        e2[5] = {**e2[5], "file_sha256": "b" * 64}
        assert realdata.dataset_hash(e2) != h0
        e3 = _entries()
        e3[0] = {**e3[0], "size": 999}
        assert realdata.dataset_hash(e3) != h0
