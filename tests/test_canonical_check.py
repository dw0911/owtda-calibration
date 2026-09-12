"""P6: the recursive canonical check (governance / identity / seal objects)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from owtda_cal.canonical import (
    CanonicalizationError,
    assert_canonical,
    non_canonical_nodes,
)


class TestRecursion:
    def test_a_clean_tree_has_no_findings(self):
        assert non_canonical_nodes({
            "int": 1, "text": "x", "flag": True, "nothing": None,
            "list": [1, "a", {"nested": [2]}],
            "decimal": Decimal("0.05"),
        }) == []

    def test_a_float_nested_three_levels_down_is_found(self):
        issues = non_canonical_nodes({"a": {"b": {"c": [1, 2, 0.5]}}})
        assert [i["code"] for i in issues] == ["BARE_FLOAT"]
        assert issues[0]["path"] == "$.a.b.c[2]"

    def test_a_non_finite_decimal_is_found(self):
        issues = non_canonical_nodes({"rho": Decimal("NaN")})
        assert issues[0]["code"] == "NON_FINITE_DECIMAL"

    def test_raw_bytes_are_found(self):
        assert non_canonical_nodes({"blob": b"x"})[0]["code"] == "RAW_BYTES"

    def test_a_non_string_key_is_found(self):
        assert non_canonical_nodes({1: "x"})[0]["code"] == "NON_STRING_KEY"

    def test_an_unsupported_type_is_found(self):
        assert non_canonical_nodes({"x": object()})[0]["code"] == "UNSUPPORTED_TYPE"

    def test_integers_are_not_mistaken_for_floats(self):
        assert non_canonical_nodes({"a": 1, "b": [0, -3, 10 ** 20]}) == []

    def test_assert_canonical_refuses_and_names_the_first_node(self):
        with pytest.raises(CanonicalizationError, match=r"\$\.a\.b"):
            assert_canonical({"a": {"b": 1.5}}, what="registry entry")


class TestRunnerScript:
    def test_the_cli_reports_and_fails_on_a_dirty_object(self, tmp_path, monkeypatch):
        import importlib.util
        import json

        spec = importlib.util.spec_from_file_location(
            "check_canonical",
            __import__("pathlib").Path(__file__).resolve().parents[1]
            / "scripts" / "check_canonical.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        clean = tmp_path / "clean.json"
        clean.write_text(json.dumps({"a": 1}), encoding="utf-8")
        dirty = tmp_path / "dirty.json"
        dirty.write_text(json.dumps({"a": {"b": 0.1}}), encoding="utf-8")

        assert module.check_file(clean) == []
        issues = module.check_file(dirty)
        assert issues[0]["code"] == "BARE_FLOAT"

    def test_ledgers_are_exempt_from_the_governance_rule(self, tmp_path):
        import importlib.util
        import json

        spec = importlib.util.spec_from_file_location(
            "check_canonical",
            __import__("pathlib").Path(__file__).resolve().parents[1]
            / "scripts" / "check_canonical.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        ledger = tmp_path / "evaluation_ledger.jsonl"
        ledger.write_text(json.dumps({"p_value": 0.05}) + "\n", encoding="utf-8")
        assert module.check_file(ledger) == []
