"""Run the post-confirmation supplement sequence (audit P0-1..P0-7, frozen order).

Ordering matters and is enforced here:

  generation      advance the smoke generation S02 -> S03 (Plan §9.3 umbrella rule)
  commit_src      commit **all source changes first**, so the run identity can name a
                  commit that really contains the code that runs
  rebuild         rebuild the freeze + run admission under the frozen env with
                  OWTDA_WSTAR_RC set (COMPUTE_SPEC.w_star from the verdict,
                  COMPUTE_FREEZE observing thread env "1", compute_git_commit = the
                  commit from ``commit_src``)
  registries      append-only amendment / invalidation chains incl. the w* verdict
  commit_frozen   commit the rebuilt governance artifacts (documented as a
                  governance-only child of the run revision)
  smoke_s03       sealed S03 blind smoke for both phases, worktree clean
  verify          schema check + raw test evidence (pytest log/xml, ruff log)
  git_identity    git bundle/verify/fsck + zero-byte status/stash + identity_check

Every artifact is written outside the repository so the worktree can stay clean for
the P0-1 cleanliness proof.  ``--from`` resumes at a named stage.

Usage::

    python scripts/run_supplement_sequence.py --evidence-root <AUDIT_EVIDENCE_ROOT> --from commit_src
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "scripts/frozen_env.py"
VENV_PY = REPO / ".venv/Scripts/python.exe"
SCOPE_FILE = REPO / "src/owtda_cal/scope.py"
NEW_TAG = "v1.5-freeze-owtda-cal-r1"
TAG_MESSAGE = (
    "OW-TDA-CAL-R1 R1 freeze amendment (AM_TOOLING_SCOPE: hash only what "
    "determines results; append-only governance chains)"
)
#: Superseded S03 evidence is archived next to the delivered tree as
#: ``S03_superseded_at_<tag>`` (never deleted, never mixed into one chain).
STAGES = (
    "generation",
    "commit_src",
    "rebuild",
    "registries",
    "commit_frozen",
    "register_anchor",
    "smoke_s03",
    "verify",
    "git_identity",
)


def _run(label: str, cmd: list[str], *, env: dict | None = None) -> int:
    print(f"\n=== [{label}] {' '.join(str(c) for c in cmd)}", flush=True)
    code = subprocess.run(cmd, cwd=str(REPO), env=env, check=False).returncode
    print(f"--- [{label}] exit={code}", flush=True)
    return code


def _frozen(
    label: str, out_dir: Path, cmd: list[str], *, log_dir: Path | None = None,
    env: dict | None = None,
) -> int:
    args = [
        sys.executable, str(LAUNCHER), "--out-dir", str(out_dir), "--label", label,
        "--capture", "--python", str(VENV_PY),
    ]
    if log_dir is not None:
        args += ["--log-dir", str(log_dir)]
    return _run(label, [*args, "--cmd", *cmd], env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="post-confirmation supplement sequence")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--from", dest="start", default=STAGES[0], choices=STAGES)
    args = parser.parse_args()
    root = Path(args.evidence_root).expanduser()
    rc_path = root / "wstar/worker_confirmation_RC.json"
    start_at = STAGES.index(args.start)

    def stage(name: str) -> bool:
        return STAGES.index(name) >= start_at

    if not rc_path.exists():
        print(f"BLOCKED: {rc_path} not found - the w* confirmation has not finished")
        return 1
    rc = json.loads(rc_path.read_text(encoding="utf-8"))
    confirmed = bool(rc.get("frozen_w_star_confirmed"))
    # Conservative adoption rule: a new w* is adopted ONLY when the preregistered
    # protocol confirms it for every phase.  A voided confirmation keeps the
    # previous frozen value (the protocol forbids re-running a failed run).
    w_star = int(rc["frozen_w_star"]) if confirmed else 8
    print(
        f"w* verdict: frozen={rc['frozen_w_star']} selected={rc.get('selected_workers')} "
        f"confirmed={confirmed} -> adopted w_star={w_star}"
    )

    child_env = {**os.environ, "OWTDA_WSTAR_RC": str(rc_path)}
    build_dir = root / "build"

    if stage("generation"):
        text = SCOPE_FILE.read_text(encoding="utf-8")
        if 'SMOKE_GENERATION_ID = "S02"' in text:
            text = text.replace('SMOKE_GENERATION_ID = "S02"', 'SMOKE_GENERATION_ID = "S03"')
            text = text.replace(
                'SMOKE_GENERATIONS_SUPERSEDED = ("S01",)',
                'SMOKE_GENERATIONS_SUPERSEDED = ("S01", "S02")',
            )
            SCOPE_FILE.write_bytes(text.encode("utf-8"))
            print("generation advanced to S03")
        elif 'SMOKE_GENERATION_ID = "S03"' in text:
            print("generation already S03")
        else:
            print("BLOCKED: unexpected SMOKE_GENERATION_ID in scope.py")
            return 1

    if stage("commit_src"):
        if _run("git_add_src", ["git", "add", "-A"]) != 0:
            return 1
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=str(REPO), check=False
        ).returncode
        if diff == 1 and _run("git_commit_src", [
            "git", "commit", "-q", "-m",
            "feat(compute): decouple parallelism from the frozen compute identity "
            "(AM_PARALLELISM_DECOUPLING)",
            "-m", "compute_spec now freezes the parallelism *contract* (thread env = 1, "
            "bitwise payload invariance, resource acceptance) instead of a worker "
            "count; the realised parallelism is recorded per run. Also closes a "
            "silent-drift defect: a freeze_id change no longer lets the REAL "
            "disposition chain be reused without an explicit re-anchor. Committed "
            "before the freeze rebuild so RUN_COMPONENT_SET.compute_git_commit names "
            "a revision that really contains the code the runs use.",
        ]) != 0:
            return 1
        print("source revision committed:", subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        ).stdout.strip())

    if stage("rebuild") and (
        _frozen("build_freeze", build_dir, ["audit/build_freeze.py"], env=child_env)
        or _frozen(
            "build_run_admission", build_dir, ["audit/build_run_admission.py"], env=child_env
        )
    ):
        return 1

    if stage("registries") and _run(
        "build_governance_registries",
        [str(VENV_PY), "audit/build_governance_registries.py", "--wstar-rc", str(rc_path)],
    ):
        return 1

    if stage("commit_frozen"):
        if _run("git_add_frozen", ["git", "add", "-A"]) != 0:
            return 1
        if _run("git_commit_frozen", [
            "git", "commit", "-q", "-m",
            "feat(freeze): rebuild freeze/run identity and registries on the committed "
            "source revision (audit supplement R1)",
            "-m", "Governance-only child of the run revision: the delta contains the "
            "rebuilt FREEZE_MANIFEST/COMPUTE_*/registries and nothing under "
            "src/configs/audit, so RUN_COMPONENT_SET.compute_git_commit names a "
            "revision whose frozen scope is byte-identical to the tree the runs used.",
        ]) != 0:
            return 1
        _run("git_tag", ["git", "tag", "-a", NEW_TAG, "-m", TAG_MESSAGE])

    if stage("register_anchor"):
        # The frozen scope gained the fail-closed guard and the H1 review-packet
        # tooling, so source_tree_hash moves: the *run/source anchor* is re-tagged
        # while freeze_id (SCOPE/PROTOCOL/ANALYSIS/COMPUTE hashes) stays unchanged.
        # Recorded append-only; v1.0 is never moved.
        registry_text = (REPO / "governance/INVALIDATION_REGISTRY.jsonl").read_text(
            encoding="utf-8"
        )
        if "INV_V12_SOURCE_ANCHOR" not in registry_text and _run("append_invalidation", [
            str(VENV_PY), "audit/append_invalidation.py",
            "--change-id", "INV_V12_SOURCE_ANCHOR",
            "--target", "freeze tag v1.2-freeze-owtda-cal-r1 as run/source anchor",
            "--replacement", NEW_TAG,
            "--statement",
            "冻结源域新增 fail-closed 守卫（audit/repo_guard.py）与 H1 复审包工具后，"
            "source_tree_hash 随内容变化，故运行/来源锚点由 v1.2 迁移至 v1.3；"
            "四个 spec hash 与 freeze_id、SCOPE_DESIGN 行哈希均未改变（科学冻结身份不变）。"
            "v1.0 未移动；v1.2 保留为历史冻结 revision。",
            "--evidence", "governance/CHANGELOG.md", "governance/AMENDMENT_PROPOSAL_PARALLELISM_DECOUPLING.md",
        ]):
            return 1
        if _run("git_add_anchor", ["git", "add", "-A"]) != 0:
            return 1
        pending = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=str(REPO), check=False
        ).returncode
        if pending == 1 and _run("git_commit_anchor", [
            "git", "commit", "-q", "-m",
            f"docs(governance): record the run/source anchor move to {NEW_TAG}",
        ]) != 0:
            return 1

    if stage("smoke_s03"):
        # AM_PARALLELISM_DECOUPLING: the parallelism of a run comes from the
        # run-level declaration in SMOKE_CONFIG, not from a frozen value.
        smoke_config = json.loads(
            (REPO / "governance/SMOKE_CONFIG_v1.json").read_text(encoding="utf-8")
        )
        workers = int(smoke_config["default_workers"])
        current = root / "smoke/S03"
        archived = root / "smoke" / f"S03_superseded_at_{NEW_TAG}"
        if current.exists() and any(current.iterdir()):
            # The previous S03 evidence belongs to the pre-amendment identity: keep
            # it (never delete evidence) but move it out of the delivered tree so
            # the package cannot mix two identities in one append-only chain.
            if archived.exists():
                raise SystemExit(
                    f"REFUSED: {current} and {archived} both exist; resolve manually"
                )
            print(f"archiving superseded S03 evidence -> {archived}")
            current.rename(archived)
        if _frozen(
            "smoke_s03", current,
            [
                "audit/run_smoke_s03.py", "--root", str(root), "--workers", str(workers),
                "--phase", "both", "--label", "smoke_s03",
            ],
            log_dir=current / "stdout_stderr",
        ):
            return 1

    if stage("verify") and (_run("validate_schemas", [
        str(VENV_PY), "audit/validate_schemas.py", "--out-dir", str(root / "schemas"),
    ]) or _run("collect_verification", [
        str(VENV_PY), "audit/collect_verification.py", "--root", str(root),
        "--python", str(VENV_PY),
    ])):
        return 1

    if stage("git_identity") and _run("collect_git_identity", [
        str(VENV_PY), "audit/collect_git_identity.py", "--root", str(root),
        "--python", str(VENV_PY),
    ]):
        return 1

    print("\nSEQUENCE COMPLETE")
    print(f"evidence root: {root}")
    _run("git_status", ["git", "status", "--porcelain=v1"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
