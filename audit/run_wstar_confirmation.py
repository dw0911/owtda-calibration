"""Preregistered ``w*`` confirmation (audit P0-3).

Reads the preregistered protocol from ``configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json``
(which lives inside the frozen source scope, so the registration itself is part of
the frozen identity) and executes it verbatim:

* both phases on the **full 32-replicate** smoke worklist,
* three paired runs per phase in the fixed order ``8->12, 12->8, 8->12``,
* median-of-three throughput, 2 % tie margin resolved toward the smaller count,
* payload identity / zero errors / zero swap growth / RSS <= 24 GiB per run,
* G3 counts must equal the frozen per-phase counts.

The protocol hash is recorded before the first run; any acceptance failure voids
the confirmation instead of being repaired by re-running.

Usage (always through the frozen-env launcher)::

    python scripts/frozen_env.py --out-dir <evidence> --label wstar --capture \
        --cmd .venv/Scripts/python.exe -- audit/run_wstar_confirmation.py --out-dir <evidence>/wstar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import scope, smoke

PROTOCOL_PATH = REPO / "configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json"
GOV = REPO / "governance"
RSS_LIMIT_BYTES = 24 * 1024**3
TERMINAL_FAIL = "VOIDED_ACCEPTANCE_CONDITION_FAILED"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_hash(rows: list[dict[str, Any]]) -> str:
    from owtda_cal.identity import H

    return H(
        "smoke_payload",
        rows=[json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows],
    )


def _measure(
    *, phase: str, workers: int, manifest: dict[str, Any],
    seed_registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    import psutil

    runner = (
        smoke.run_smoke_null
        if phase == scope.PHASE_SMOKE_NULL
        else smoke.run_smoke_alt
    )
    proc = psutil.Process()
    samples: list[int] = []
    swap_before = psutil.swap_memory().used
    swap_peak = swap_before
    stop = threading.Event()

    def sampler() -> None:
        nonlocal swap_peak
        while not stop.is_set():
            total = proc.memory_info().rss
            for child in proc.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except psutil.Error:
                    pass
            samples.append(total)
            swap_peak = max(swap_peak, psutil.swap_memory().used)
            stop.wait(0.25)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    result = runner(
        manifest=manifest, seed_registry=seed_registry, workers=workers,
        replicate_limit=None,
    )
    stop.set()
    thread.join(timeout=2.0)

    expected = smoke.expected_smoke_counts(phase)
    run = {
        "phase": phase,
        "workers": workers,
        "replicates_per_cell": scope.R0_SMOKE,
        "wall_seconds": result.wall_seconds,
        "ph_windows_unique": result.ph_windows,
        # A10: PH throughput counts only the windows that really entered the PH
        # engine (BPI); MOMENTS windows are reported separately and never mixed in.
        "ph_windows_computed": result.ph_windows,
        "ph_windows_per_second": result.ph_windows / result.wall_seconds,
        "feature_windows_processed": result.feature_windows,
        "feature_windows_per_second": result.feature_windows / result.wall_seconds,
        "data_units": result.data_units,
        "evaluation_rows": result.evaluation_rows,
        "errors": result.errors,
        "missing_fields": smoke.assert_row_fields(result.rows),
        "counts_match_g3": (
            result.data_units == expected["data_units"]
            and result.evaluation_rows == expected["evaluation_rows"]
            and result.ph_windows == expected["ph_windows"]
        ),
        "payload_hash": _payload_hash(result.rows),
    }
    resources = {
        "phase": phase,
        "workers": workers,
        "peak_total_rss_bytes": max(samples) if samples else None,
        "swap_before_bytes": swap_before,
        "swap_peak_bytes": swap_peak,
        "swap_growth_bytes": swap_peak - swap_before,
        "samples": len(samples),
    }
    return run, resources


def main() -> int:
    parser = argparse.ArgumentParser(description="w* confirmation per preregistered protocol")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    protocol = _load(PROTOCOL_PATH)
    protocol_sha = _sha256(PROTOCOL_PATH)
    if protocol.get("status") != "PREREGISTERED_BEFORE_MEASUREMENT":
        raise SystemExit("protocol is not in the preregistered state")

    manifest = _load(GOV / "FREEZE_MANIFEST.json")
    seed_registry = _load(GOV / "SEED_REGISTRY_v1.0.json")
    raw_path = out_dir / "worker_confirmation_raw.jsonl"
    res_path = out_dir / "resource_samples.jsonl"
    raw_path.write_text("", encoding="utf-8")
    res_path.write_text("", encoding="utf-8")
    header = {
        "record_type": "protocol_preregistration",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "preregistered_at_utc": protocol["preregistered_at_utc"],
        "opened_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": __import__("subprocess").run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        ).stdout.strip(),
        "source_tree_hash": manifest["source_tree_hash"],
        "environment_lock_hash": manifest["environment_lock_hash"],
    }
    with raw_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(header, ensure_ascii=False, sort_keys=True) + "\n")

    runs: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    index = 0
    for phase in protocol["phases"]:
        for pair, (first, second) in enumerate(protocol["sequence"], start=1):
            for workers in (first, second):
                index += 1
                print(
                    f"[wstar] run {index} phase={phase} pair={pair} workers={workers}",
                    flush=True,
                )
                run, resource = _measure(
                    phase=phase, workers=workers, manifest=manifest,
                    seed_registry=seed_registry,
                )
                run.update(run_index=index, pair=pair, protocol_sha256=protocol_sha)
                resource.update(run_index=index, pair=pair)
                runs.append(run)
                resources.append(resource)
                with raw_path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(run, ensure_ascii=False, sort_keys=True) + "\n")
                with res_path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(
                        json.dumps(resource, ensure_ascii=False, sort_keys=True) + "\n"
                    )
                print(
                    f"[wstar]   wall={run['wall_seconds']:.2f}s "
                    f"throughput={run['ph_windows_per_second']:.1f} PH win/s "
                    f"errors={run['errors']} rss={resource['peak_total_rss_bytes']} "
                    f"swap_delta={resource['swap_growth_bytes']}",
                    flush=True,
                )

    comparison: dict[str, Any] = {"schema_version": 1, "kind": "wstar_payload_comparison"}
    decisions: dict[str, Any] = {}
    margin = protocol["decision_rule"]["tie_margin"]
    for phase in protocol["phases"]:
        phase_runs = [r for r in runs if r["phase"] == phase]
        phase_res = [r for r in resources if r["phase"] == phase]
        hashes = {r["payload_hash"] for r in phase_runs}
        comparison[phase] = {
            "payload_hashes": sorted(hashes),
            "identical": len(hashes) == 1,
            "run_count": len(phase_runs),
        }
        by_workers: dict[int, list[dict[str, Any]]] = {}
        for run in phase_runs:
            by_workers.setdefault(run["workers"], []).append(run)
        medians = {
            w: statistics.median(r["ph_windows_per_second"] for r in rs)
            for w, rs in sorted(by_workers.items())
        }
        acceptance = {
            "payload_identical": len(hashes) == 1,
            "zero_errors": all(r["errors"] == 0 for r in phase_runs),
            "zero_missing_fields": all(r["missing_fields"] == 0 for r in phase_runs),
            "counts_match_g3": all(r["counts_match_g3"] for r in phase_runs),
            "no_swap_growth": all(r["swap_growth_bytes"] <= 0 for r in phase_res),
            "rss_within_limit": all(
                r["peak_total_rss_bytes"] is not None
                and r["peak_total_rss_bytes"] <= RSS_LIMIT_BYTES
                for r in phase_res
            ),
            "three_paired_runs": all(
                len(rs) == protocol["paired_runs_per_phase"]
                for rs in by_workers.values()
            )
            and len(by_workers) == len(protocol["candidates"]),
        }
        ok = all(acceptance.values())
        if not ok:
            decisions[phase] = {
                "status": TERMINAL_FAIL,
                "acceptance": acceptance,
                "medians": medians,
                "selected_workers": None,
            }
            continue
        best = max(medians, key=lambda w: medians[w])
        worst = min(medians.values())
        close = (medians[best] - min(medians.values())) / min(medians.values()) <= margin
        selected = min(protocol["candidates"]) if close else best
        decisions[phase] = {
            "status": "CONFIRMED",
            "acceptance": acceptance,
            "medians": medians,
            "relative_gain_of_best": medians[best] / worst - 1.0,
            "within_tie_margin": close,
            "selected_workers": selected,
        }

    selected = sorted(
        {d["selected_workers"] for d in decisions.values() if d.get("selected_workers")}
    )
    frozen = protocol["frozen_w_star"]
    confirmed = (
        all(d["status"] == "CONFIRMED" for d in decisions.values())
        and selected == [frozen]
    )
    rc = {
        "schema_version": 1,
        "kind": "wstar_confirmation_rc",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frozen_w_star": frozen,
        "candidates": protocol["candidates"],
        "worklist_replicates": scope.R0_SMOKE,
        "paired_runs_per_phase": protocol["paired_runs_per_phase"],
        "sequence": protocol["sequence"],
        "decisions_per_phase": decisions,
        "selected_workers": selected,
        "frozen_w_star_confirmed": confirmed,
        "amendment_required": not confirmed,
        "runs": runs,
    }
    (out_dir / "worker_payload_comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "worker_confirmation_RC.json").write_text(
        json.dumps(rc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[wstar] selected={selected} confirmed={confirmed}", flush=True)
    return 0 if confirmed else 1


if __name__ == "__main__":
    raise SystemExit(main())
