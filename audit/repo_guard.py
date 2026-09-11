"""Fail-closed guard for the freeze / run-identity builders.

The same defect class has now appeared twice, both times as a **silent omission**:

  * B15c/S02 — the freeze was rebuilt *before* the source revision was committed,
    so ``RUN_COMPONENT_SET.compute_git_commit`` named a revision that did not
    contain the code the runs actually used;
  * F-B15c-4 — ``source_tree_hash`` is derived from ``git ls-files``, so a module
    that was written but never ``git add``-ed is silently missing from the frozen
    manifest.

Neither can be detected from the produced file alone, so the builders must refuse
to produce one: if anything under the frozen scope is modified, staged but not
committed, or untracked, the build stops *before writing a single byte*.

Ignored paths (``__pycache__``, ``.pytest_cache``, …) are deliberately not
violations: they are build noise, not unbound content.  If the repository state
cannot be verified at all (not a git repo, git unavailable) the guard refuses as
well — "cannot prove clean" is treated as "not clean".
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

#: Paths whose *content* is anchored by ``source_tree_hash`` / component manifests.
FROZEN_SCOPE_PATHS: tuple[str, ...] = ("src", "configs", "audit")


def _porcelain_lines(
    repo_root: Path, scope_paths: Sequence[str]
) -> list[str]:
    cmd = [
        "git", "status", "--porcelain=v1", "--untracked-files=all", "--",
        *scope_paths,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "cannot verify the frozen scope state: "
            f"`{' '.join(cmd)}` exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def frozen_scope_violations(
    repo_root: Path | str,
    scope_paths: Iterable[str] = FROZEN_SCOPE_PATHS,
) -> list[str]:
    """Return the ``git status --porcelain`` lines inside the frozen scope."""
    return _porcelain_lines(Path(repo_root), list(scope_paths))


def assert_clean_frozen_scope(
    repo_root: Path | str,
    *,
    context: str,
    scope_paths: Iterable[str] = FROZEN_SCOPE_PATHS,
) -> None:
    """Refuse to build unless the frozen scope is clean and fully committed.

    Raises ``SystemExit`` (a deliberate, non-retryable refusal) so a build
    script aborts before writing outputs that would silently mis-bind the run
    identity to the wrong revision.
    """
    paths = list(scope_paths)
    try:
        violations = frozen_scope_violations(repo_root, paths)
    except RuntimeError as exc:
        raise SystemExit(
            f"REFUSED ({context}): {exc}\n"
            "The frozen scope must be verifiable and clean; a build that cannot "
            "prove this would produce an unbound identity."
        ) from exc
    if not violations:
        return
    listed = "\n".join(f"  {line}" for line in violations)
    raise SystemExit(
        f"REFUSED ({context}): the frozen scope {'/'.join(paths)} is not clean:\n"
        f"{listed}\n"
        "Commit the frozen-scope changes first, then rebuild.  Two defects came "
        "from skipping this: a compute_git_commit that did not contain the code "
        "that ran (S02) and a source_tree_hash that silently omitted new modules "
        "(F-B15c-4).  If the intent was to add a new module, `git add` it first."
    )


if __name__ == "__main__":  # pragma: no cover - manual probe
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    print(f"frozen scope violations in {root}:")
    for line in frozen_scope_violations(root) or ["  (none)"]:
        print(line)
