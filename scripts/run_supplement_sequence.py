"""Run the post-confirmation supplement sequence (audit P0-1..P0-7, frozen order).

Executed only after the preregistered ``w*`` confirmation finishes.  Steps are
fail-fast and each writes its evidence outside the repository, so the worktree can
stay clean for the P0-1 cleanliness proof:

  1. read the ``w*`` verdict (protocol RC)
  2. advance the smoke generation ``S02 -> S03`` (Plan §9.3 umbrella rule)
  3. rebuild the freeze under the frozen env with ``OWTDA_WSTAR_RC`` set
     (COMPUTE_SPEC.w_star from the verdict, COMPUTE_FREEZE observed thread env = "1")
  4. rebuild run admission (RUN_COMPONENT_SET / bindings / SCOPE_DESIGN)
  5. build the amendment/invalidation chains including the w* adoption event
  6. named commit + annotated freeze tag ``v1.1-freeze-owtda-cal-r1``
  7. run the sealed S03 smoke (both phases) through the frozen-env launcher
  8. schema check + raw test evidence (pytest log/xml, ruff) on the frozen commit
  9. git freeze-identity evidence (bundle/verify/fsck/clean status/identity_check)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "scripts/frozen_env.py"
VENV_PY = REPO / ".venv/Scripts/python.exe"
SCOPE_FILE = REPO / "src/owtda_cal/scope.py"
NEW_TAG = "v1.1-freeze-owtda-cal-r1"


def _run(label: str, cmd: list[str], *, env: dict | None = None, capture: Path | None = None) -> int:
    print(f"\n=== [{label}] {' '.join(str(c) for c in cmd)}", flush=True)
    if capture is not None:
        capture.parent.mkdir(parents=True, exist_ok=True)
        with capture.open("wb") as fh:
            code = subprocess.run(cmd, cwd=str(REPO), env=env, stdout=fh,
                                  stderr=subprocess.STDOUT, check=False).returncode
    else:
        code = subprocess.run(cmd, cwd=str(REPO), env=env, check=False).returncode
    print(f"--- [{label}] exit={code}", flush=True)
    return code


def _frozen(label: str, out_dir: Path, cmd: list[str], *, log_dir: Path | None = None,
            env: dict | None = None) -> int:
    args = [
        sys.executable, str(LAUNCHER), "--out-dir", str(out_dir), "--label", label,
        "--capture", "--python", str(VENV_PY),
    ]
    if log_dir is not None:
        args += ["--log-dir", str(log_dir)]
    args += ["--cmd", *cmd]
    return _run(label, args, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="post-confirmation supplement sequence")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--start-at", type=int, default=1)
    args = parser.parse_args()
    root = Path(args.evidence_root).expanduser()
    rc_path = root / "wstar/worker_confirmation_RC.json"

    def step(number: int) -> bool:
        return number >= args.start_at

    if not rc_path.exists():
        print(f"BLOCKED: {rc_path} not found - the w* confirmation has not finished")
        return 1
    rc = json.loads(rc_path.read_text(encoding="utf-8"))
    w_star = (
        rc["frozen_w_star"]
        if rc.get("frozen_w_star_confirmed")
        else (rc.get("selected_workers") or [8])[0]
    )
    print(f"w* verdict: frozen={rc['frozen_w_star']} selected={rc.get('selected_workers')} "
          f"confirmed={rc.get('frozen_w_star_confirmed')} -> adopted w_star={w_star}")

    # 2. advance the smoke generation
    if step(2):
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

    env = {"OWTDA_WSTAR_RC": str(rc_path)}
    import os

    child_env = {**os.environ, **env}

    # 3. rebuild the freeze (frozen env so COMPUTE_FREEZE observes thread env = 1)
    if step(3):
        if _frozen("build_freeze", root / "build", ["audit/build_freeze.py"], env=child_env):
            return 1
        if _frozen("build_run_admission", root / "build", ["audit/build_run_admission.py"], env=child_env):
            return 1

    # 5. governance chains (needs the w* verdict)
    if step(5):
        if _run("build_governance_registries",
                [str(VENV_PY), "audit/build_governance_registries.py", "--wstar-rc", str(rc_path)]):
            return 1

    # 6. commit + annotated tag
    if step(6):
        if _run("git_add", ["git", "add", "-A"]):
            return 1
        body = (
            f"w* verdict: frozen={rc['frozen_w_star']} "
            f"selected={rc.get('selected_workers')} "
            f"confirmed={rc.get('frozen_w_star_confirmed')}; adopted w_star={w_star}. "
            "Freeze rebuilt under the real environment lock (uv.lock + observed thread env)."
        )
        if _run("git_commit", [
            "git", "commit", "-q", "-m",
            "feat(freeze): adopt confirmed w*, rebuild freeze under the real environment lock, "
            "advance smoke generation to S03 (audit supplement R1)",
            "-m", body,
        ]):
            return 1
        _run("git_tag", ["git", "tag", "-a", NEW_TAG, "-m",
                         f"OW-TDA-CAL-R1 R1 freeze amendment (w*={w_star}, real environment lock)"])

    # 7. sealed S03 smoke
    if step(7):
        if _frozen(
            "smoke_s03", root / "smoke/S03", [
                "audit/run_smoke_s03.py", "--root", str(root), "--workers", str(w_star),
                "--phase", "both", "--label", "smoke_s03",
            ],
            log_dir=root / "smoke/S03/stdout_stderr",
        ):
            return 1

    # 8. schemas + raw verification evidence
    if step(8):
        if _run("validate_schemas", [
            str(VENV_PY), "audit/validate_schemas.py", "--out-dir", str(root / "schemas"),
        ]):
            return 1
        if _run("collect_verification", [
            str(VENV_PY), "audit/collect_verification.py", "--root", str(root),
            "--python", str(VENV_PY),
        ]):
            return 1

    # 9. git freeze identity (must be last: it asserts a clean worktree)
    if step(9):
        if _run("collect_git_identity", [
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
