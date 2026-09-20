"""The seven verifier mutations of the re-audit (2026-09-13), pinned as rules.

Each mutation below was applied to an independent copy of the package -- with the
outer hashes updated -- and the self-check still reported "76/80, no new
failure".  These tests assert the opposite: every mutation must now produce an
attributable, coded failure.
"""

from __future__ import annotations

import hashlib

import pytest

from owtda_cal.oracles import (
    check_junit,
    check_p_arithmetic,
    compare_identity_sets,
    disclosure_consistency,
    verify_file_ref,
)


class TestPArithmetic:
    def test_a_grid_value_passes(self):
        assert check_p_arithmetic({"K": 49, "p": 0.05, "reject": True}) == []
        assert check_p_arithmetic({"K": 50, "p": 0.051, "reject": False}) == []

    def test_p_nudged_off_the_grid_is_detected(self):
        """The probe: p + 0.0001 leaves the legal grid."""
        issues = check_p_arithmetic({"K": 49, "p": 0.0501, "reject": True})
        assert [i["code"] for i in issues] == ["P_OFF_GRID"]

    def test_reject_stored_as_an_integer_is_detected(self):
        issues = check_p_arithmetic({"K": 49, "p": 0.05, "reject": 1})
        assert [i["code"] for i in issues] == ["REJECT_NOT_BOOL"]

    def test_reject_inconsistent_with_k_is_detected(self):
        issues = check_p_arithmetic({"K": 400, "p": 0.401, "reject": True})
        assert [i["code"] for i in issues] == ["REJECT_INCONSISTENT"]

    def test_k_is_never_rounded_back_from_p(self):
        """p must be checked against K, not the other way round."""
        issues = check_p_arithmetic({"K": 12, "p": 0.5, "reject": False})
        assert "P_OFF_GRID" in [i["code"] for i in issues]

    def test_non_finite_p_and_bad_k_are_attributable(self):
        assert check_p_arithmetic({"K": 5, "p": float("nan"), "reject": False})[0]["code"] == "P_NOT_FINITE"
        assert check_p_arithmetic({"K": 1000, "p": 1.0, "reject": False})[0]["code"] == "K_OUT_OF_RANGE"
        assert check_p_arithmetic({"K": 5.0, "p": 0.006, "reject": False})[0]["code"] == "K_NOT_INT"

    def test_exceed_is_accepted_as_the_k_alias(self):
        assert check_p_arithmetic({"exceed": 0, "p": 0.001, "reject": True}) == []


class TestUniquenessBeforeSets:
    def test_identical_unique_sets_pass(self):
        expected = [{"id": "a", "up": 1}, {"id": "b", "up": 2}]
        actual = [{"id": "b", "up": 2}, {"id": "a", "up": 1}]
        result = compare_identity_sets(expected, actual, key_field="id",
                                       identity_fields=["up"])
        assert result["equal"] is True

    def test_duplicate_expected_is_detected(self):
        """A set comparison alone would not see this."""
        expected = [{"id": "a"}, {"id": "a"}]
        actual = [{"id": "a"}]
        result = compare_identity_sets(expected, actual, key_field="id")
        assert "DUPLICATE_ENTRY" in {i["code"] for i in result["issues"]}
        assert result["equal"] is False

    def test_duplicate_actual_is_detected(self):
        result = compare_identity_sets([{"id": "a"}], [{"id": "a"}, {"id": "a"}],
                                       key_field="id")
        assert "DUPLICATE_ENTRY" in {i["code"] for i in result["issues"]}

    def test_missing_and_extra_are_named(self):
        result = compare_identity_sets([{"id": "a"}, {"id": "b"}], [{"id": "a"}, {"id": "c"}],
                                       key_field="id")
        codes = {i["code"] for i in result["issues"]}
        assert codes == {"MISSING_FROM_ACTUAL", "EXTRA_IN_ACTUAL"}
        assert result["missing"] == ["b"] and result["extra"] == ["c"]

    def test_matched_key_with_a_different_upstream_id_is_detected(self):
        expected = [{"id": "a", "source_run_seal": "X"}]
        actual = [{"id": "a", "source_run_seal": "Y"}]
        result = compare_identity_sets(expected, actual, key_field="id",
                                       identity_fields=["source_run_seal"])
        assert result["identity_mismatches"][0]["field"] == "source_run_seal"
        assert result["equal"] is False


class TestFileRef:
    def test_a_real_reference_passes(self, tmp_path):
        target = tmp_path / "evidence" / "ledger.jsonl"
        target.parent.mkdir()
        target.write_bytes(b"row\n")
        ref = {"path": str(target), "sha256": hashlib.sha256(b"row\n").hexdigest()}
        assert verify_file_ref(ref, evidence_root=str(tmp_path)) == []

    def test_a_deleted_file_is_detected(self, tmp_path):
        ref = {"path": str(tmp_path / "gone.jsonl"), "sha256": "a" * 64}
        assert verify_file_ref(ref, evidence_root=str(tmp_path))[0]["code"] == "FILE_REF_MISSING"

    def test_a_path_outside_the_root_is_detected(self, tmp_path):
        outside = tmp_path.parent / "outside.bin"
        outside.write_bytes(b"x")
        ref = {"path": str(outside), "sha256": hashlib.sha256(b"x").hexdigest()}
        assert verify_file_ref(ref, evidence_root=str(tmp_path / "evidence"))[0]["code"] == (
            "FILE_REF_OUTSIDE_ROOT"
        )

    def test_a_hash_that_does_not_match_the_bytes_is_detected(self, tmp_path):
        target = tmp_path / "evidence" / "seal.json"
        target.parent.mkdir()
        target.write_bytes(b"real bytes")
        ref = {"path": str(target), "sha256": hashlib.sha256(b"other bytes").hexdigest()}
        assert verify_file_ref(ref, evidence_root=str(tmp_path))[0]["code"] == (
            "FILE_REF_HASH_MISMATCH"
        )


class TestJUnit:
    def _xml(self, cases: list[tuple[str, bool]]) -> str:
        body = ""
        for identity, skipped in cases:
            cls, _sep, name = identity.partition("::")
            body += f'<testcase classname="{cls}" name="{name}"'
            body += '><skipped message="x"/></testcase>' if skipped else "/>"
        return f"<testsuite>{body}</testsuite>"

    def test_exact_identity_set_passes(self):
        expected = {"tests::one", "tests::two"}
        result = check_junit(self._xml([("tests::one", False), ("tests::two", False)]),
                             expected_identities=expected)
        assert result["issues"] == []

    def test_duplicate_identity_with_an_unchanged_total_is_detected(self):
        """The probe: the count stayed the same, one identity appeared twice."""
        xml = self._xml([("tests::one", False), ("tests::one", False), ("tests::two", False)])
        result = check_junit(xml, expected_identities={"tests::one", "tests::two"})
        assert "JUNIT_DUPLICATE_TESTCASE" in {i["code"] for i in result["issues"]}

    def test_missing_and_extra_identities_are_named(self):
        xml = self._xml([("tests::one", False)])
        result = check_junit(xml, expected_identities={"tests::one", "tests::gone"})
        codes = {i["code"] for i in result["issues"]}
        assert codes == {"JUNIT_MISSING_TESTCASE"}

    def test_an_unapproved_skip_is_detected(self):
        xml = self._xml([("tests::one", True)])
        result = check_junit(xml, expected_identities={"tests::one"}, approved_skips=set())
        assert "JUNIT_UNAPPROVED_SKIP" in {i["code"] for i in result["issues"]}

    def test_an_approved_skip_is_allowed(self):
        xml = self._xml([("tests::one", True)])
        result = check_junit(xml, expected_identities={"tests::one"},
                             approved_skips={"tests::one"})
        assert result["issues"] == []


class TestDisclosureVersusAdmission:
    def test_an_honest_failure_is_disclosed_not_hidden(self):
        outcome = disclosure_consistency("FAIL", "FAIL")
        assert outcome["disclosed_consistently"] is True
        assert outcome["admissible"] is False
        assert "not a disclosure defect" in outcome["note"]

    def test_a_mismatch_is_a_disclosure_defect(self):
        outcome = disclosure_consistency("PASS", "FAIL")
        assert outcome["disclosed_consistently"] is False
        assert outcome["admissible"] is False

    def test_agreement_and_green_admit(self):
        outcome = disclosure_consistency("pass", "PASS")
        assert outcome["disclosed_consistently"] is True
        assert outcome["admissible"] is True


@pytest.mark.parametrize("row", [
    {"K": 49, "p": 0.05, "reject": True},
    {"K": 0, "p": 0.001, "reject": True},
    {"K": 999, "p": 1.0, "reject": False},
])
def test_the_frozen_rule_holds_on_the_whole_grid(row):
    assert check_p_arithmetic(row) == []
