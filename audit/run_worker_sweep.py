"""``w*`` confirmation sweep (Plan §9.4).

Plan §9.4: choose the unique worker count with the highest throughput that also
satisfies (a) *all* scientific payloads bitwise identical across worker counts,
(b) total peak RSS <= 24 GiB, (c) no swap growth, (d) no unexplained error; if
two candidates are within 2% throughput, take the smaller one.

``COMPUTE_SPEC_v1.json`` freezes ``w_star = 8``; changing it would require a
freeze amendment, so this script's job is to *confirm or falsify* that value.

The sweep runs both smoke phases at a reduced replicate count (the reference
``t_0,32``/``t_1,32`` come from the full ``audit/run_smoke.py`` run) and compares
the ordered evaluation-row payloads across worker counts.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import scope, smoke
from owtda_cal.identity import H

GOV = REPO / "governance"
DEFAULT_WORKERS = (1, 4, 8, 10, 12)
DEFAULT_REPLICATES = 8
RSS_LIMIT_BYTES = 24 * 1024**3
TIE_MARGIN = 0.02


def _load(name: str) -> dict[str, Any]:
    return json.loads((GOV / name).read_text(encoding="utf-8"))


def _payload_hash(rows: list[dict[str, Any]]) -> str:
    return H(
        "smoke_payload",
        rows=[json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows],
    )


def _measure(*, phase: str, workers: int, replicates: int,
             manifest: dict[str, Any], seed_registry: dict[str, Any]) -> dict[str, Any]:
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
        replicate_limit=replicates,
    )
    stop.set()
    thread.join(timeout=2.0)

    return {
        "phase": phase,
        "workers": workers,
        "replicates": replicates,
        "wall_seconds": result.wall_seconds,
        "data_units": result.data_units,
        "evaluation_rows": result.evaluation_rows,
        "ph_windows_unique": result.ph_windows,
        # A10: PH throughput counts only the windows that entered the PH engine.
        "ph_windows_computed": result.ph_windows,
        "ph_windows_per_second": result.ph_windows / result.wall_seconds,
        "feature_windows_processed": result.feature_windows,
        "feature_windows_per_second": result.feature_windows / result.wall_seconds,
        "errors": result.errors,
        "missing_fields": smoke.assert_row_fields(result.rows),
        "payload_hash": _payload_hash(result.rows),
        "peak_total_rss_bytes": max(samples) if samples else None,
        "swap_growth_bytes": swap_peak - swap_before,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="w* confirmation sweep")
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    parser.add_argument("--workers", type=int, nargs="+", default=list(DEFAULT_WORKERS))
    args = parser.parse_args()

    manifest = _load("FREEZE_MANIFEST.json")
    seed_registry = _load("SEED_REGISTRY_v1.0.json")
    # AM_PARALLELISM_DECOUPLING: there is no frozen worker count any more.  The
    # reference for throughput comparison is the run-level declaration in
    # SMOKE_CONFIG; the frozen object only carries the contract it must satisfy.
    smoke_config = _load("SMOKE_CONFIG_v1.json")
    frozen_w_star = int(smoke_config["default_workers"])

    results: list[dict[str, Any]] = []
    for phase in scope.SMOKE_PHASES:
        for workers in args.workers:
            row = _measure(
                phase=phase, workers=workers, replicates=args.replicates,
                manifest=manifest, seed_registry=seed_registry,
            )
            results.append(row)
            print(
                f"{phase} w={workers:<3} wall={row['wall_seconds']:.2f}s "
                f"throughput={row['ph_windows_per_second']:.1f} PH win/s "
                f"rows={row['evaluation_rows']} errors={row['errors']} "
                f"rss={row['peak_total_rss_bytes']}"
            )

    verdicts: dict[str, Any] = {}
    for phase in scope.SMOKE_PHASES:
        rows = [r for r in results if r["phase"] == phase]
        reference = next(r for r in rows if r["workers"] == 8)
        for r in rows:
            r["payload_identical_to_w8"] = r["payload_hash"] == reference["payload_hash"]
            r["eligible"] = (
                r["payload_identical_to_w8"]
                and r["errors"] == 0
                and r["missing_fields"] == 0
                and r["peak_total_rss_bytes"] is not None
                and r["peak_total_rss_bytes"] <= RSS_LIMIT_BYTES
                and r["swap_growth_bytes"] <= 0
            )
        eligible = [r for r in rows if r["eligible"]]
        if not eligible:
            verdicts[phase] = {"eligible": [], "selected_workers": None}
            continue
        best = max(r["windows_per_second"] for r in eligible)
        tied = sorted(
            r["workers"]
            for r in eligible
            if r["windows_per_second"] >= best * (1.0 - TIE_MARGIN)
        )
        verdicts[phase] = {
            "eligible": sorted(r["workers"] for r in eligible),
            "best_throughput_windows_per_second": best,
            "tied_within_2pct": tied,
            "selected_workers": tied[0],
        }

    selected = sorted({
        v["selected_workers"] for v in verdicts.values() if v["selected_workers"]
    })
    confirmed = selected == [frozen_w_star]
    out = {
        "schema_version": 1,
        "kind": "worker_sweep_rc_v1",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "smoke_generation_id": scope.SMOKE_GENERATION_ID,
        "replicates_per_cell": args.replicates,
        "reference_workers": 8,
        "frozen_w_star": frozen_w_star,
        "frozen_w_star_confirmed": confirmed,
        "selected_workers_per_phase": verdicts,
        "selected_workers_intersection": selected,
        "amendment_required": not confirmed,
        "results": results,
    }
    out_path = REPO / "artifacts/audit/worker_sweep_RC.json"
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"frozen_w_star={frozen_w_star} confirmed={confirmed} selected={selected}")
    print(f"EVIDENCE={out_path.name}")
    return 0 if confirmed else 1


if __name__ == "__main__":
    raise SystemExit(main())
