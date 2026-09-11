"""Fail-closed frozen-scope guard (audit supplement R1, recommendation D).

The guard exists because two real defects were silent omissions rather than wrong
values: a freeze rebuilt before the source commit (S02) and a ``source_tree_hash``
that omitted a module nobody had ``git add``-ed (F-B15c-4).  These tests pin the
refusal semantics on a throwaway repository, so they never depend on the state of
the working tree they are run in.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "audit"))

import repo_guard


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        # Identity is supplied per call: the global git config is never touched.
        env=None,
    )


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    assert _git(repo, "init", "-q").returncode == 0
    for key, value in (("user.email", "t@example.invalid"), ("user.name", "t")):
        assert _git(repo, "config", key, value).returncode == 0
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src/mod.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs/note.md").write_text("n\n", encoding="utf-8")
    assert _git(repo, "add", "-A").returncode == 0
    assert _git(repo, "commit", "-q", "-m", "init").returncode == 0


class TestFrozenScopeViolations:
    def test_clean_scope_has_no_violation(self, tmp_path: Path):
        repo = tmp_path / "r"
        _init(repo)
        assert repo_guard.frozen_scope_violations(repo) == []

    def test_modified_scoped_file_is_a_violation(self, tmp_path: Path):
        repo = tmp_path / "r"
        _init(repo)
        (repo / "src/mod.py").write_text("x = 2\n", encoding="utf-8")
        violations = repo_guard.frozen_scope_violations(repo)
        assert len(violations) == 1 and "src/mod.py" in violations[0]

    def test_untracked_scoped_file_is_a_violation(self, tmp_path: Path):
        """The F-B15c-4 case: written but never `git add`-ed."""
        repo = tmp_path / "r"
        _init(repo)
        (repo / "src/new_module.py").write_text("y = 1\n", encoding="utf-8")
        violations = repo_guard.frozen_scope_violations(repo)
        assert len(violations) == 1 and "src/new_module.py" in violations[0]

    def test_staged_but_uncommitted_is_a_violation(self, tmp_path: Path):
        repo = tmp_path / "r"
        _init(repo)
        (repo / "src/new_module.py").write_text("y = 1\n", encoding="utf-8")
        assert _git(repo, "add", "src/new_module.py").returncode == 0
        violations = repo_guard.frozen_scope_violations(repo)
        assert len(violations) == 1 and "src/new_module.py" in violations[0]

    def test_ignored_files_do_not_trip_the_guard(self, tmp_path: Path):
        repo = tmp_path / "r"
        _init(repo)
        cache = repo / "src/__pycache__"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "mod.cpython-312.pyc").write_bytes(b"\x00")
        assert repo_guard.frozen_scope_violations(repo) == []

    def test_changes_outside_the_frozen_scope_are_ignored(self, tmp_path: Path):
        repo = tmp_path / "r"
        _init(repo)
        (repo / "docs/note.md").write_text("edited\n", encoding="utf-8")
        (repo / "docs/new.md").write_text("new\n", encoding="utf-8")
        assert repo_guard.frozen_scope_violations(repo) == []


class TestAssertCleanFrozenScope:
    def test_clean_scope_returns_normally(self, tmp_path: Path):
        repo = tmp_path / "r"
        _init(repo)
        repo_guard.assert_clean_frozen_scope(repo, context="unit")

    def test_refusal_names_the_offending_path_and_context(self, tmp_path: Path):
        repo = tmp_path / "r"
        _init(repo)
        (repo / "configs").mkdir(exist_ok=True)
        (repo / "configs/new.json").write_text("{}\n", encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            repo_guard.assert_clean_frozen_scope(repo, context="build_freeze")
        message = str(excinfo.value)
        assert "build_freeze" in message
        assert "configs/new.json" in message

    def test_unverifiable_repository_is_refused(self, tmp_path: Path):
        """`cannot prove clean` must be treated as `not clean`."""
        plain = tmp_path / "not_a_repo"
        plain.mkdir()
        with pytest.raises(SystemExit) as excinfo:
            repo_guard.assert_clean_frozen_scope(plain, context="unit")
        assert "REFUSED" in str(excinfo.value)


class TestGuardIsWiredAndConsistent:
    def test_hashed_and_guarded_scopes_are_distinct_and_nested(self):
        """AM_TOOLING_SCOPE: hash what determines results, guard what must commit.

        ``audit/`` holds evidence-assembly tooling: it must be committed before a
        build or run (so ``compute_git_commit`` covers the code that produced the
        evidence) but it must NOT move ``source_tree_hash``, or every tooling
        improvement would force a re-freeze.
        """
        import build_freeze

        hashed = tuple(f"{p}/" for p in repo_guard.HASHED_SOURCE_PATHS)
        guarded = tuple(f"{p}/" for p in repo_guard.GUARDED_SCOPE_PATHS)
        assert build_freeze.SOURCE_TREE_PREFIXES == hashed
        assert hashed == ("src/", "configs/")
        assert guarded == ("src/", "configs/", "audit/", "scripts/")
        assert set(hashed) < set(guarded)
        assert "audit/" not in hashed and "audit/" in guarded
        # F-R1-6: the thread-env launcher materially affects results and must be
        # committed before a run, even though it is not part of the hashed scope.
        assert "scripts/" in guarded and "scripts/" not in hashed

    @pytest.mark.parametrize("name", ["build_freeze.py", "build_run_admission.py"])
    def test_builders_call_the_guard(self, name: str):
        text = (REPO / "audit" / name).read_text(encoding="utf-8")
        assert "repo_guard.assert_clean_frozen_scope(" in text
