"""Promote one smoke attempt's evidence into the repository slots (step 9).

``audit/validate_admission.py`` reads the G3 evidence from fixed in-repo paths
(``artifacts/audit/smoke_RC.json``, ``artifacts/audit/smoke_alt_RC.json``) and
resolves each RC's ``ledger_file`` **relative to the repository**, so a smoke
attempt that lives outside the repo is not visible to it.  Historically the
promotion was done by hand, which is how the repository came to carry S02-era
evidence while the freeze had moved on -- ``validate_admission`` then failed its
identity-closure and provenance checks against a *stale* ledger rather than
against a real defect.

This tool makes the promotion explicit and fail-closed:

* the attempt's own ``provenance_manifest.json`` must bind the run to the
  **current** freeze (source tree, environment lock, component set, smoke
  config); a mismatch refuses the promotion instead of promoting foreign bytes;
* the ledger is copied only after its content hash recomputes to the RC's;
* the RC copy gets the ``provenance`` block and the measured 32-replicate wall
  times (``budget``) that the admission checks read, taken from the run itself;
* the in-repo ledger path in the RC copy is the one ``validate_admission``
  resolves (``artifacts/smoke/<PHASE>/evaluation_rows_w8_r32.jsonl``).

Usage::

    python scripts/promote_smoke_evidence.py --evidence-root <ATTEMPT> [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import scope

GOV = REPO / "governance"
PHASE_SLOT = {
    scope.PHASE_SMOKE_NULL: {
        "rc_out": REPO / "artifacts/audit/smoke_RC.json",
        "ledger_out": REPO / "artifacts/smoke/SMOKE_NULL/evaluation_rows_w4_r32.jsonl",
        "rc_name": "smoke_null_RC.json",
        "ledger_name": "evaluation_rows.jsonl",
    },
    scope.PHASE_SMOKE_ALT: {
        "rc_out": REPO / "artifacts/audit/smoke_alt_RC.json",
        "ledger_out": REPO / "artifacts/smoke/SMOKE_ALT/evaluation_rows_w4_r32.jsonl",
        "rc_name": "smoke_alt_RC.json",
        "ledger_name": "evaluation_rows.jsonl",
    },
}


class PromotionRefused(RuntimeError):
    """The attempt may not be promoted; nothing was written."""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ledger_hashes(ledger: Path) -> dict[str, str]:
    """Row-content hash: the defined ledger identity is its canonical JSON lines."""
    digest = hashlib.sha256()
    rows = 0
    with ledger.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            digest.update(line.rstrip("\n").encode("utf-8"))
            digest.update(b"\n")
            rows += 1
    return {"sha256": digest.hexdigest(), "rows": rows}


def _wall_seconds(rc: dict) -> float:
    report = rc.get("report") or {}
    for key in ("wall_seconds", "wall_time_seconds"):
        value = report.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    raise PromotionRefused(
        "the run reported no wall time at the frozen scale; the §9.4 wall gate "
        "needs a measured t_32 from this very run (never a copied number)"
    )


def promote(evidence_root: Path, *, dry_run: bool = False) -> dict:
    generation = scope.SMOKE_GENERATION_ID
    attempt = evidence_root / "smoke" / generation
    provenance_path = attempt / "provenance_manifest.json"
    if not provenance_path.is_file():
        raise PromotionRefused(f"no provenance manifest at {provenance_path}")
    provenance = _load(provenance_path)

    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    admission = manifest["run_admission"]

    bound = {
        "source_tree_hash": provenance.get("source_tree_hash"),
        "environment_lock_hash": provenance.get("environment_lock_hash"),
        "smoke_config_hash": provenance.get("smoke_config_hash"),
    }
    current = {
        "source_tree_hash": manifest["source_tree_hash"],
        "environment_lock_hash": manifest["environment_lock_hash"],
        "smoke_config_hash": manifest["smoke_config_hash"],
    }
    if bound != current:
        raise PromotionRefused(
            "the attempt is not bound to the current freeze "
            f"(attempt={bound}, freeze={current}); it may not be promoted"
        )
    verdict = provenance.get("verdict")
    if isinstance(verdict, dict):
        # the run's own verdict object: admission must have passed, the evidence must
        # be sealed, and every named check must be true -- no check may be missing
        checks = verdict.get("checks") or {}
        verdict_ok = (
            verdict.get("admission_passed") is True
            and verdict.get("evidence_sealed") is True
            and bool(checks)
            and all(value is True for value in checks.values())
        )
    else:
        verdict_ok = verdict in ("PASS", "COMPLETE")
    if not verdict_ok:
        raise PromotionRefused(
            f"the attempt's own verdict is {verdict!r} "
            "(admission_passed / evidence_sealed / every check must be true); "
            "failed evidence is archived, never promoted"
        )

    # the measured wall time of *this* attempt, at the frozen 32-replicate scale
    wall = {
        scope.PHASE_SMOKE_NULL: _wall_seconds(_load(attempt / PHASE_SLOT[
            scope.PHASE_SMOKE_NULL]["rc_name"])),
        scope.PHASE_SMOKE_ALT: _wall_seconds(_load(attempt / PHASE_SLOT[
            scope.PHASE_SMOKE_ALT]["rc_name"])),
    }

    promoted: list[dict] = []
    for phase, slot in PHASE_SLOT.items():
        # Re-audit 2026-09-15: the smoke dispatcher runs one phase per subprocess, and
        # ``audit/run_smoke_s03.py`` rewrites ``provenance_manifest.json`` on every
        # invocation -- so the combined manifest only describes the *last* phase
        # (attempt 11c's manifest lists SMOKE_ALT alone).  The promotion therefore
        # verifies each phase from that phase's own seal and run record instead of
        # trusting a manifest that cannot see both, and says so in the promoted
        # provenance block.
        seal_path = attempt / f"SMOKE_SEAL_{phase}.json"
        if not seal_path.is_file():
            raise PromotionRefused(f"the attempt carries no seal for {phase}: {seal_path}")
        seal = _load(seal_path)
        if seal.get("terminal_state") != "RUN_SEALED":
            raise PromotionRefused(
                f"{phase}: terminal_state {seal.get('terminal_state')!r}, not RUN_SEALED"
            )
        entry = {
            "run_id": seal.get("run_id"),
            "run_component_set_hash": seal.get("run_component_set_hash"),
            "run_input_bindings_hash": seal.get("run_input_bindings_hash"),
            "scope_design_hash": seal.get("scope_design_hash"),
            "smoke_seal_hash": seal.get("smoke_seal_hash"),
            "seal_file": seal_path.name,
        }
        for field in ("run_input_bindings_hash", "scope_design_hash"):
            if seal.get(field) != admission[phase].get(field):
                raise PromotionRefused(
                    f"{phase}: {field} {str(seal.get(field))[:12]} != the frozen "
                    f"admission's {str(admission[phase].get(field))[:12]}"
                )
        rc = _load(attempt / slot["rc_name"])
        ledger_src = attempt / phase / slot["ledger_name"]
        if not ledger_src.is_file():
            raise PromotionRefused(f"missing ledger for {phase}: {ledger_src}")
        hashes = _ledger_hashes(ledger_src)
        if hashes["sha256"] != rc.get("ledger_content_hash"):
            raise PromotionRefused(
                f"{phase}: ledger hash {hashes['sha256'][:12]} != RC "
                f"{str(rc.get('ledger_content_hash'))[:12]}"
            )
        if rc.get("counts_match_contract") is not True:
            raise PromotionRefused(f"{phase}: counts_match_contract is not true")
        if rc.get("unexplained_errors") != 0:
            raise PromotionRefused(f"{phase}: unexplained_errors != 0")
        if (rc.get("identity_closure") or {}).get("passed") is not True:
            raise PromotionRefused(f"{phase}: identity closure did not pass")

        component_set = entry.get("run_component_set_hash")
        if component_set != admission[phase]["run_component_set_hash"]:
            raise PromotionRefused(
                f"{phase}: the run used component set {str(component_set)[:12]} but the "
                f"current admission declares {admission[phase]['run_component_set_hash'][:12]}"
            )

        promoted_rc = {
            **rc,
            # the path the admission checker resolves, relative to the repository
            "ledger_file": str(slot["ledger_out"].relative_to(REPO)).replace("\\", "/"),
            "provenance": {
                "run_component_set_hash": component_set,
                "scope_design_hash": admission[phase]["scope_design_hash"],
                "source_tree_hash": provenance["source_tree_hash"],
                "environment_lock_hash": provenance["environment_lock_hash"],
                "run_id": entry.get("run_id"),
                "run_input_bindings_hash": entry.get("run_input_bindings_hash"),
                "smoke_seal_hash": entry.get("smoke_seal_hash"),
                "seal_file": entry.get("seal_file"),
                "verification_source": (
                    "this phase's own RUN seal + RC; the combined "
                    "provenance_manifest.json describes only the last dispatched phase"
                ),
            },
            "budget": {
                "t_0_32_seconds": (wall[scope.PHASE_SMOKE_NULL]
                                   if phase == scope.PHASE_SMOKE_NULL else None),
                "t_1_32_seconds": (wall[scope.PHASE_SMOKE_ALT]
                                   if phase == scope.PHASE_SMOKE_ALT else None),
                "measured_at_replicates": rc.get("replicates_per_cell"),
                "measured_workers": rc.get("workers"),
            },
        }
        promoted.append({
            "phase": phase, "rc_out": str(slot["rc_out"]),
            "ledger_out": str(slot["ledger_out"]),
            "ledger_rows": hashes["rows"],
            "ledger_sha256": hashes["sha256"],
            "rc": promoted_rc, "ledger_src": str(ledger_src),
        })

    if not dry_run:
        for item in promoted:
            destination = Path(item["rc_out"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(item["rc"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger_out = Path(item["ledger_out"])
            ledger_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item["ledger_src"], ledger_out)
            if _sha256(ledger_out) != _sha256(Path(item["ledger_src"])):
                raise PromotionRefused(f"copy verification failed for {ledger_out}")

    return {
        "evidence_root": str(evidence_root),
        "generation": generation,
        "dry_run": dry_run,
        "promoted": [
            {k: v for k, v in item.items() if k not in ("rc", "ledger_src")}
            for item in promoted
        ],
        "source_tree_hash": provenance["source_tree_hash"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="promote a smoke attempt into the repo")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        outcome = promote(Path(args.evidence_root).expanduser().resolve(),
                          dry_run=args.dry_run)
    except PromotionRefused as exc:
        print(json.dumps({"promoted": False, "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(outcome, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
