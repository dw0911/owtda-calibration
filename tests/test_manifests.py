"""The three manifests (task pack §7): science, execution, validation."""

from __future__ import annotations

import json

import pytest

from owtda_cal.manifests import (
    build_manifest_bundle,
    environment_subset,
    execution_manifest,
    hash_files,
    import_closure,
    scientific_manifest,
    validation_manifest,
)


def _fake_repo(tmp_path):
    src = tmp_path / "src" / "owtda_cal"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "core.py").write_text("import os\n", encoding="utf-8")
    (src / "helpers.py").write_text("from . import core\nimport json\n", encoding="utf-8")
    script = tmp_path / "scripts"
    script.mkdir()
    (script / "entry.py").write_text(
        "import sys\nsys.path.insert(0, 'src')\nfrom owtda_cal import helpers\n",
        encoding="utf-8")
    (script / "frozen_env.py").write_text("THREADS = 1\n", encoding="utf-8")
    return src, script


class TestImportClosure:
    def test_the_closure_follows_imports_not_directories(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        closure = import_closure([script / "entry.py"], roots=[tmp_path / "src"],
                                 prefix="owtda_cal")
        assert any(p.endswith("owtda_cal/helpers.py") for p in closure)
        assert any(p.endswith("owtda_cal/core.py") for p in closure)

    def test_a_non_imported_script_is_not_claimed_as_a_dependency(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        closure = import_closure([script / "entry.py"], roots=[tmp_path / "src"],
                                 prefix="owtda_cal")
        assert not any(p.endswith("frozen_env.py") for p in closure)

    def test_the_entry_itself_is_part_of_its_closure(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        closure = import_closure([script / "entry.py"], roots=[tmp_path / "src"],
                                 prefix="owtda_cal")
        assert any(p.endswith("entry.py") for p in closure)


class TestScientificManifest:
    def test_it_hashes_the_science_files_and_its_configs(self, tmp_path):
        src, _script = _fake_repo(tmp_path)
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        manifest = scientific_manifest(
            files=[src / "core.py", src / "helpers.py"],
            config_files=[tmp_path / "config.json"],
            root=tmp_path,
        )
        assert manifest["kind"] == "SCIENTIFIC_MANIFEST"
        assert set(manifest["files"]) == {"src/owtda_cal/core.py",
                                          "src/owtda_cal/helpers.py"}
        assert manifest["config_files"] == {
            "config.json": manifest["config_files"]["config.json"]}
        assert len(manifest["manifest_hash"]) == 64

    def test_the_hash_changes_when_a_file_changes(self, tmp_path):
        src, _script = _fake_repo(tmp_path)
        before = scientific_manifest(files=[src / "core.py"], root=tmp_path)
        (src / "core.py").write_text("import os\nimport sys\n", encoding="utf-8")
        after = scientific_manifest(files=[src / "core.py"], root=tmp_path)
        assert before["manifest_hash"] != after["manifest_hash"]


class TestExecutionManifest:
    def test_it_records_the_command_environment_and_policy(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        manifest = execution_manifest(
            entries=[script / "entry.py"], command=["python", "scripts/entry.py"],
            environment={"PYTHONHASHSEED": "0"}, policy_sha256="a" * 64,
            roots=[tmp_path / "src"], root=tmp_path,
        )
        assert manifest["kind"] == "EXECUTION_MANIFEST"
        assert manifest["command"] == ["python", "scripts/entry.py"]
        assert manifest["environment"] == {"PYTHONHASHSEED": "0"}
        assert manifest["policy_sha256"] == "a" * 64
        assert manifest["files"]
        assert len(manifest["manifest_hash"]) == 64

    def test_the_closure_files_carry_real_hashes(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        manifest = execution_manifest(
            entries=[script / "entry.py"], command=["x"], environment={},
            policy_sha256="b" * 64, roots=[tmp_path / "src"], root=tmp_path,
        )
        for name, digest in manifest["files"].items():
            assert len(digest) == 64, name
        assert any(name.endswith("owtda_cal/core.py") for name in manifest["files"])


class TestValidationManifest:
    def _junit(self, cases) -> str:
        body = ""
        for classname, name, skipped in cases:
            body += f'<testcase classname="{classname}" name="{name}"'
            body += "><skipped/></testcase>" if skipped else "/>"
        return f"<testsuite>{body}</testsuite>"

    def test_it_binds_the_test_identity_set_and_the_skip_set(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        collected = [{"classname": "tests.test_x", "name": "test_a"},
                     {"classname": "tests.test_x", "name": "test_b"}]
        manifest = validation_manifest(
            test_files=[script / "entry.py"], collected_nodeids=collected,
            junit_xml=self._junit([("tests.test_x", "test_a", False),
                                   ("tests.test_x", "test_b", False)]),
            approved_skips=[], exit_code=0, stdout=b"ok", stderr=b"",
            root=tmp_path,
        )
        assert manifest["kind"] == "VALIDATION_MANIFEST"
        assert manifest["junit"]["identities"] == ["tests.test_x::test_a",
                                                   "tests.test_x::test_b"]
        assert manifest["junit"]["issues"] == []
        assert manifest["exit_code"] == 0
        assert manifest["stdout_sha256"] != manifest["stderr_sha256"]

    def test_an_unapproved_skip_is_listed(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        collected = [{"classname": "tests.test_x", "name": "test_a"}]
        manifest = validation_manifest(
            test_files=[script / "entry.py"], collected_nodeids=collected,
            junit_xml=self._junit([("tests.test_x", "test_a", True)]),
            approved_skips=[], root=tmp_path,
        )
        assert manifest["unapproved_skips"] == ["junit"]

    def test_an_approved_skip_is_accepted(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        collected = [{"classname": "tests.test_x", "name": "test_a"}]
        manifest = validation_manifest(
            test_files=[script / "entry.py"], collected_nodeids=collected,
            junit_xml=self._junit([("tests.test_x", "test_a", True)]),
            approved_skips=["tests.test_x::test_a"], root=tmp_path,
        )
        assert manifest["unapproved_skips"] == []
        assert manifest["junit"]["skipped"] == ["tests.test_x::test_a"]

    def test_a_missing_testcase_is_reported(self, tmp_path):
        _src, script = _fake_repo(tmp_path)
        collected = [{"classname": "tests.test_x", "name": "test_a"},
                     {"classname": "tests.test_x", "name": "test_missing"}]
        manifest = validation_manifest(
            test_files=[script / "entry.py"], collected_nodeids=collected,
            junit_xml=self._junit([("tests.test_x", "test_a", False)]), root=tmp_path,
        )
        codes = {issue["code"] for issue in manifest["junit"]["issues"]}
        assert "JUNIT_MISSING_TESTCASE" in codes


class TestBundle:
    def test_the_bundle_writes_three_manifests_and_binds_the_plan(self, tmp_path):

        src, script = _fake_repo(tmp_path)
        plan = tmp_path / "PLAN_SUMMARY.json"
        plan.write_text(json.dumps({"formal_scale": True, "totals": {"evaluation_rows": 8},
                                    "phases": {"NULL": {"index_hashes": {
                                        "evaluation": "a" * 64}}}}), encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_x.py").write_text("def test_x(): assert True\n")
        bundle = build_manifest_bundle(
            root=tmp_path, out_dir=tmp_path / "manifests",
            entries=[script / "entry.py"], command=["python", "x"],
            policy_sha256="f" * 64, science_files=[src / "core.py"],
            test_files=[tmp_path / "tests" / "test_x.py"],
            roots=[tmp_path / "src"], plan_summary_path=plan,
        )
        out = tmp_path / "manifests"
        for name in ("SCIENTIFIC_MANIFEST.json", "EXECUTION_MANIFEST.json",
                     "VALIDATION_MANIFEST.json", "MANIFEST_BUNDLE.json"):
            assert (out / name).is_file(), name
        assert bundle["plan_binding"]["formal_scale"] is True
        assert bundle["plan_binding"]["evaluation_index_hashes"] == {"NULL": "a" * 64}
        assert len(bundle["bundle_hash"]) == 64
        assert bundle["bundle_hash"] == json.loads(
            (out / "MANIFEST_BUNDLE.json").read_text(encoding="utf-8"))["bundle_hash"]

    def test_the_bundle_hash_changes_with_the_plan_binding(self, tmp_path):

        src, script = _fake_repo(tmp_path)
        kwargs = {"root": tmp_path, "entries": [script / "entry.py"], "command": ["x"],
                  "policy_sha256": "f" * 64, "science_files": [src / "core.py"],
                  "roots": [tmp_path / "src"]}
        first = build_manifest_bundle(out_dir=tmp_path / "m1", **kwargs)
        plan = tmp_path / "PLAN_SUMMARY.json"
        plan.write_text(json.dumps({"formal_scale": False, "phases": {}}), encoding="utf-8")
        second = build_manifest_bundle(out_dir=tmp_path / "m2",
                                       plan_summary_path=plan, **kwargs)
        assert first["bundle_hash"] != second["bundle_hash"]


class TestHelpers:
    def test_hash_files_refuses_missing_paths(self, tmp_path):
        present = tmp_path / "a.txt"
        present.write_text("x", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            hash_files([present, tmp_path / "gone.txt"], root=tmp_path)

    def test_environment_subset_is_explicit(self, monkeypatch):
        monkeypatch.setenv("OWTDA_TEST_VAR", "1")
        assert environment_subset(["OWTDA_TEST_VAR", "NOT_SET_ANYWHERE"]) == {
            "OWTDA_TEST_VAR": "1"}
