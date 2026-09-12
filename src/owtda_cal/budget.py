"""Full-scale disk and time budget (task pack §8).

The re-audit (2026-09-13) rejected the previous estimate on one ground: it took
the smoke record's bytes and multiplied by a copy factor, never scaling to the
formal number of evaluations, and it left the whole lifecycle (feature ledgers,
indices, resource streams, recovery originals, merge stages, archives) out of the
account.

This module derives the budget from the frozen plan instead:

* 82,800 data units, 165,600 feature rows, 331,200 evaluation rows, each phase
  listed separately;
* an explicit statement of whether full feature matrices, summaries, PH diagrams
  and resampling statistics are stored -- and their bytes if they are;
* resource logs at 1 Hz, event/attempt records, indices, manifests, recovery
  originals and archives all counted;
* the staging/final/merge/recovery/archive coexistence peak and replica counts;
* a per-volume free-space check using integer cross-multiplication;
* a separate time projection (compute / serialize / merge / seal / recovery),
  with the formal measurement recorded as ``NOT_YET_OBSERVED`` -- which does not
  block the estimate, while a *missing* required component does.
"""

from __future__ import annotations

import hashlib
import json

from .canonical import canonical_json_bytes

#: Every one of these must be present in the schema/profile or the budget is
#: INCOMPLETE -- the list is the audit's list, not a convenience default.
REQUIRED_SCHEMA_KEYS = (
    "evaluation_row_bytes",
    "feature_row_bytes",
    "data_unit_bytes",
    "index_entry_bytes",
    "event_row_bytes",
    "resource_row_bytes",
    "manifest_bytes",
    "store_full_feature_matrices",
    "store_summaries",
    "store_ph_diagrams",
    "store_resampling_stats",
)

REQUIRED_PROFILE_KEYS = (
    "compute_seconds_per_evaluation",
    "serialize_seconds_per_evaluation",
    "merge_seconds_per_phase",
    "seal_seconds_per_phase",
    "recovery_seconds",
)

REQUIRED_STORAGE_KEYS = ("copies", "coexisting_stages")

ALLOWED_COUNT_SOURCES = ("frozen_plan",)


def derive_counts(scope_counts: dict | None = None) -> dict:
    """The frozen formal counts, phase by phase."""
    if scope_counts is None:
        from . import scope

        scope_counts = scope.scope_counts_summary()
    return {
        "source": "frozen_plan",
        "h0": {
            "logical_cells": scope_counts["h0_logical_cells"],
            "data_units": scope_counts["h0_data_units"],
            "feature_rows": scope_counts["h0_feature_rows"],
            "evaluation_rows": scope_counts["h0_evaluation_rows"],
        },
        "h1": {
            "logical_cells": scope_counts["h1_logical_cells"],
            "data_units": scope_counts["h1_data_units"],
            "feature_rows": scope_counts["h1_feature_rows"],
            "evaluation_rows": scope_counts["h1_evaluation_rows"],
        },
        "totals": {
            "data_units": scope_counts["h0_data_units"] + scope_counts["h1_data_units"],
            "feature_rows": (
                scope_counts["h0_feature_rows"] + scope_counts["h1_feature_rows"]
            ),
            "evaluation_rows": (
                scope_counts["h0_evaluation_rows"] + scope_counts["h1_evaluation_rows"]
            ),
        },
    }


def _bytes(count: int, per_row: int) -> int:
    return int(count) * int(per_row)


def build_budget(
    *,
    counts: dict,
    serialization_schema: dict,
    storage_policy: dict,
    profile: dict,
    volumes: list[dict] | None = None,
    disk_fraction: dict | None = None,
) -> dict:
    """Derive the full budget; ``APPROVED_ESTIMATE`` or ``INCOMPLETE``."""
    missing: list[str] = []
    if counts.get("source") not in ALLOWED_COUNT_SOURCES:
        missing.append(
            "counts must be derived from the frozen plan (derive_counts()); a "
            "smoke-record extrapolation is not a full-scale derivation"
        )
    for key in REQUIRED_SCHEMA_KEYS:
        if key not in serialization_schema:
            missing.append(f"serialization_schema.{key}")
    for key in REQUIRED_PROFILE_KEYS:
        if key not in profile:
            missing.append(f"profile.{key}")
    for key in REQUIRED_STORAGE_KEYS:
        if key not in storage_policy:
            missing.append(f"storage_policy.{key}")
    if missing:
        return {
            "status": "INCOMPLETE",
            "missing": missing,
            "counts": counts.get("totals"),
            "formal_measurement": "NOT_YET_OBSERVED",
        }

    schema = serialization_schema
    totals = counts["totals"]
    evaluations = totals["evaluation_rows"]
    features = totals["feature_rows"]
    data_units = totals["data_units"]
    phases = {
        name: {
            "data_units": counts[name]["data_units"],
            "feature_rows": counts[name]["feature_rows"],
            "evaluation_rows": counts[name]["evaluation_rows"],
        }
        for name in ("h0", "h1")
    }

    components: dict[str, int] = {
        "evaluation_ledger_bytes": _bytes(evaluations, schema["evaluation_row_bytes"]),
        "feature_ledger_bytes": _bytes(features, schema["feature_row_bytes"]),
        "data_unit_bytes": _bytes(data_units, schema["data_unit_bytes"]),
        "index_bytes": _bytes(
            evaluations + features + data_units, schema["index_entry_bytes"]
        ),
        "event_attempt_bytes": _bytes(evaluations, schema["event_row_bytes"]),
        "manifest_bytes": int(schema["manifest_bytes"]),
    }
    stored: dict[str, bool] = {
        "full_feature_matrices": bool(schema["store_full_feature_matrices"]),
        "summaries": bool(schema["store_summaries"]),
        "ph_diagrams": bool(schema["store_ph_diagrams"]),
        "resampling_stats": bool(schema["store_resampling_stats"]),
    }
    if stored["full_feature_matrices"]:
        components["feature_matrix_bytes"] = _bytes(
            features, schema.get("feature_matrix_bytes", 0)
        )
    if stored["summaries"]:
        components["summary_bytes"] = _bytes(
            counts["h0"]["logical_cells"] + counts["h1"]["logical_cells"],
            schema.get("summary_bytes", 0),
        )
    if stored["ph_diagrams"]:
        components["ph_diagram_bytes"] = _bytes(
            features, schema.get("ph_diagram_bytes", 0)
        )
    if stored["resampling_stats"]:
        components["resampling_stat_bytes"] = _bytes(
            evaluations, schema.get("resampling_stats_row_bytes", 0)
        )

    # Time first: the resource stream is logged once per second of wall time.
    seconds = (
        evaluations * float(profile["compute_seconds_per_evaluation"])
        + evaluations * float(profile["serialize_seconds_per_evaluation"])
        + 2 * float(profile["merge_seconds_per_phase"])
        + 2 * float(profile["seal_seconds_per_phase"])
        + float(profile["recovery_seconds"])
    )
    components["resource_log_bytes"] = int(seconds) * int(schema["resource_row_bytes"])

    content_total = sum(components.values())
    copies = storage_policy["copies"]
    stages = storage_policy["coexisting_stages"]
    stage_bytes = {
        stage: int(content_total * float(copies.get(stage, 1)))
        for stage in stages
    }
    peak = sum(stage_bytes.values())
    recovery_original = int(content_total * float(copies.get("recovery", 1)))
    archive = int(content_total * float(copies.get("archive", 1)))

    volume_reports: list[dict] = []
    fraction = disk_fraction or {"num": 4, "den": 5}
    for volume in volumes or []:
        free = volume.get("free_bytes")
        ok = (isinstance(free, int)
              and (peak + recovery_original + archive) * fraction["den"]
              <= fraction["num"] * free)
        volume_reports.append({**volume, "projected_bytes": peak + recovery_original
                               + archive, "within_limit": bool(ok)})

    def _ms(value: float) -> int:
        # canonical payloads forbid bare floats: milliseconds as integers
        return int(round(value * 1000))

    body = {
        "counts": {"totals": totals, "phases": phases},
        "stored_objects": stored,
        "components": components,
        "content_total_bytes": content_total,
        "stage_bytes": stage_bytes,
        "recovery_original_bytes": recovery_original,
        "archive_bytes": archive,
        "peak_bytes": peak + recovery_original + archive,
        "volumes": volume_reports,
        "time_milliseconds": {
            "total": _ms(seconds),
            "compute": _ms(evaluations * float(profile["compute_seconds_per_evaluation"])),
            "serialize": _ms(
                evaluations * float(profile["serialize_seconds_per_evaluation"])
            ),
            "merge": _ms(2 * float(profile["merge_seconds_per_phase"])),
            "seal": _ms(2 * float(profile["seal_seconds_per_phase"])),
            "recovery": _ms(float(profile["recovery_seconds"])),
        },
    }
    budget_hash = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    volumes_ok = all(v["within_limit"] for v in volume_reports) if volume_reports else True
    return {
        "schema_version": 1,
        "kind": "full_scale_budget",
        "status": "APPROVED_ESTIMATE" if volumes_ok else "INCOMPLETE",
        "missing": [] if volumes_ok else ["a volume does not have room for the peak"],
        "budget_hash": budget_hash,
        "disk_fraction": fraction,
        "formal_measurement": "NOT_YET_OBSERVED",
        "formal_measurement_note": (
            "the estimate does not require a completed formal run; the formal "
            "measurement is reported separately and never fabricated"
        ),
        **body,
    }


__all__ = [
    "ALLOWED_COUNT_SOURCES",
    "REQUIRED_PROFILE_KEYS",
    "REQUIRED_SCHEMA_KEYS",
    "REQUIRED_STORAGE_KEYS",
    "build_budget",
    "derive_counts",
]
