"""Build the B14 (2026-09-23) common-freeze objects (Plan §16.2).

Generates, in cycle-free order:

  1. ``SCOPE_SPEC_v1.json``      (scientific factors only, no derived IDs)
  2. ``PROTOCOL_CONTENT_v1.json`` (protocol identity + frozen document manifest)
  3. ``ESTIMAND_SPEC_REGISTRY_v1.json``
  4. ``ANALYSIS_SPEC_v1.0.json`` (binds the estimand registry hash + 7 plans)
  5. ``COMPUTE_SPEC_v1.json`` and ``COMPUTE_FREEZE.json`` (environment lock)
  6. ``freeze_id`` from the four spec hashes
  7. ``SCOPE_DESIGN_<phase>_<scope_design_hash>.csv``
  8. ``FREEZE_MANIFEST.json`` (records everything, feeds back into nothing)

Re-running is idempotent for every hashed object; only ``source_tree_hash``
tracks later source edits (which require re-binding before formal runs).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import chains, components, disposition, freeze, registry, scope

PROJECT_ID = "owtda-cal-r1"
PROTOCOL_ID = "OWTDA-CAL-R1-PROTOCOL-v1.0"
EVIDENCE_GENERATION_ID = "G01"
FREEZE_DATE = "2026-09-10"
FROZEN_DOCUMENTS = (
    "governance/PROJECT_CHARTER.md",
    "governance/PROTOCOL_v1.0.md",
    "governance/METHOD_SPEC_v1.0.md",
    "governance/SAP_v1.0.md",
    "governance/DATA_SPEC_v1.0.md",
    "governance/CLAIM_MATRIX_v1.0.csv",
    "governance/ATTACK_SUITE_v1.0.md",
    "OWTDA_CAL_R1_COMPLETE_PLAN_v1.0.md",
)
COMPONENT_GENERATIONS = {
    "data_generation_id": "D01",
    "feature_generation_id": {"bpi": "F01", "moments": "F01"},
    "method_generation_id": {"M0": "M01", "M1": "M01"},
}
SOURCE_TREE_PREFIXES = ("src/", "configs/", "audit/")
TASK_INDEX_GENERATION_ID = "T01"
SEED_ROOT_FAMILIES = (
    ("SMOKE_NULL", "smoke", scope.SMOKE_GENERATION_ID),
    ("SMOKE_ALT", "smoke", scope.SMOKE_GENERATION_ID),
    ("NULL", "null_data", "D01"),
    ("NULL", "null_M0", "M01"),
    ("NULL", "null_M1", "M01"),
    ("ALT", "h1_data", "D01"),
    ("ALT", "h1_M0", "M01"),
    ("ALT", "h1_M1", "M01"),
    ("REAL_TASK_BUILD", "real_task", "T01"),
    ("REAL_TASK_BUILD", "real_task_id_salt", "T01"),
    ("REAL_PREDICTION", "real_M0", "M01"),
    ("REAL_PREDICTION", "real_M1", "M01"),
    ("ANALYSIS", "analysis_bootstrap", "A01"),
)
ISOLATED_FAMILIES = frozenset({"real_task", "real_task_id_salt"})
SECRET_KEY_BY_FAMILY = {
    "real_task": "real_task_root_key",
    "real_task_id_salt": "real_task_id_salt",
}
GOV = REPO / "governance"
SECRETS_FILE = REPO / "secrets" / "REAL_TASK_SECRETS.local.json"
COMPONENT_GENERATION_BY_KIND = {"data": "D01", "feature": "F01", "method": "M01"}
REAL_RC_EVIDENCE = {
    "admitted_subjects": 8,
    "min_subjects_required": 8,
    "eligible_tasks": 23,
    "min_tasks_required": 24,
    "subjects_without_candidate": ["subject109"],
    "dataset_hash": "eb0e11f9c20a0498ffc5f69017b5fd7744f4d46232b8adf52f1b9352525fc33b",
    "task_builder_config_hash": "bbaaa38bcc421818d6d8a22c89f26078be8c72baabb81dd53fb55a0e75db7961",
}


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scope_spec() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "config_kind": "scope_spec",
        "phases": [scope.scope_spec_h0(), scope.scope_spec_h1()],
        "real": {
            "replicate_source": "TASK_INDEX_SEAL",
            "W": 100,
            "strides": [100, 50, 25],
            "features": list(scope.FEATURE_IDS),
            "methods": list(scope.METHOD_IDS),
            "required_relations": [
                "prediction_row_per_task_stride_feature_method",
                "evaluation_row_one_to_one_with_prediction",
                "truth_row_per_task",
            ],
            "n_task": "DERIVED_FROM_TASK_INDEX_SEAL",
        },
    }


def _protocol_content() -> dict[str, Any]:
    entries = freeze.file_manifest_entries(FROZEN_DOCUMENTS, root=REPO)
    return {
        "schema_version": 1,
        "config_kind": "protocol_content",
        "project_id": PROJECT_ID,
        "protocol_id": PROTOCOL_ID,
        "protocol_version": "1.0",
        "freeze_date": FREEZE_DATE,
        "phases": ["NULL", "ALT", "REAL"],
        "evidence_generation_id": EVIDENCE_GENERATION_ID,
        "statistics": {
            "B": 999,
            "p_value_rule": "(1+exceed)/(B+1)",
            "reject_rule": "p<=0.05",
            "alpha": "0.05",
            "resample_exceed_comparison": "float64_ge",
            "equivalence_band": ["0.035", "0.065"],
            "max_statistic_plateau_tolerance": "64*eps64*max(1,abs(Tmax))",
            "boundary_audit_tolerance": "128*eps64*max(1,abs(Tb),abs(Tobs))",
            "window_mean_variance_factor": "A_mean=q-(q*q-1)/(3M)",
        },
        "gates": ["G0", "G1", "G2", "G3", "G4", "G5", "G6"],
        "failure_routes": [
            "REAL_OMITTED_BY_DATA_GATE",
            "REAL_DEFERRED",
            "INVALIDATED",
            "VOID_EVALUATOR_DEFECT",
        ],
        "documents": entries,
    }


def _estimands() -> dict[str, dict[str, Any]]:
    primary = {"role": "PRIMARY", "aggregation": "equal_DGP_weight", "sidedness": "one_sided"}
    return {
        "CELL_REJECT_RATE": {
            "statistic": "pi_hat=K/2500",
            "role": "PRIMARY_DESCRIPTIVE",
            "ci": ["wilson_90", "wilson_95", "clopper_pearson_95"],
            "conditioning": "cell_feature_method",
        },
        "P1_D_OV_M0": {**primary, "statistic": "D_OV", "method": "M0", "rho": "0", "boundary": "0.10", "claim": "C2"},
        "P2_D_ST_M0": {**primary, "statistic": "D_ST", "method": "M0", "rho": "0", "boundary": "0.10", "claim": "C3"},
        "P3_D_CONS_M1": {**primary, "statistic": "D_CONS", "method": "M1", "rho": "0", "boundary": "0.01", "claim": "C5"},
        "D_OV_MOMENTS": {"role": "SECONDARY", "statistic": "D_OV", "method": "MOMENTS", "rho": "0", "aggregation": "equal_DGP_weight"},
        "D_ST_MOMENTS": {"role": "SECONDARY", "statistic": "D_ST", "method": "MOMENTS", "rho": "0", "aggregation": "equal_DGP_weight"},
        "D_CONS_MOMENTS": {"role": "SECONDARY", "statistic": "D_CONS", "method": "MOMENTS", "rho": "0", "aggregation": "equal_DGP_weight"},
        "PAIRED_M0_M1_DIFF": {"role": "SECONDARY", "statistic": "paired_difference", "scope": "cell_feature"},
        "I_RHO_M0": {"role": "DESCRIPTIVE_ONLY", "statistic": "D_0.8-D_0", "method": "M0", "causal_reading": "forbidden"},
        "A_TR_M0": {"role": "DESCRIPTIVE_ONLY", "statistic": "A_tr", "method": "M0", "formula": "Dhat_inv*numerator"},
        "A_TR_MOMENTS": {"role": "DESCRIPTIVE_ONLY", "statistic": "A_tr", "method": "MOMENTS", "formula": "Dhat_inv*numerator"},
        "H1_SIZE_STD_POWER": {"role": "DESCRIPTIVE_ONLY", "statistic": "size_standardized_power", "quantile_rule": "nearest_rank"},
        "REAL_MARGINAL_DECISION_RATE": {"role": "DESCRIPTIVE_ONLY", "statistic": "r", "stratum": "feature_method_stride", "n_subject_bootstrap": 2000},
        "REAL_JOINT_ENDPOINT": {"role": "DESCRIPTIVE_ONLY", "statistic": "J", "stratum": "feature_method_stride"},
        "REAL_POSITION_HIT": {"role": "DESCRIPTIVE_ONLY", "statistic": "L", "stratum": "feature_stride", "threshold_seconds": 2},
        "REAL_DISTANCE": {"role": "DESCRIPTIVE_ONLY", "statistic": "distance", "unit": "seconds", "threshold_seconds": 2},
    }


def _plans() -> dict[str, dict[str, Any]]:
    h0_cluster = {
        "resample_role": "H0_CLUSTER_STRATUM",
        "stratum_domain": "DGP_family",
        "cluster_ordering": "cluster_id_ascii",
        "replacement": True,
    }
    return {
        "P1_H0_PRIMARY_V1": {**h0_cluster, "target_estimand": "P1_D_OV_M0", "sample_size": 10000},
        "P2_H0_PRIMARY_V1": {**h0_cluster, "target_estimand": "P2_D_ST_M0", "sample_size": 10000},
        "P3_H0_PRIMARY_V1": {**h0_cluster, "target_estimand": "P3_D_CONS_M1", "sample_size": 10000},
        "H0_DIAGNOSTICS_ALL_V1": {**h0_cluster, "target_estimand": "CELL_REJECT_RATE", "sample_size": 2000},
        "H1_NULL_QUANTILE_ALL_V1": {**h0_cluster, "target_estimand": "H1_SIZE_STD_POWER", "sample_size": 2000},
        "H1_ALT_POWER_ALL_V1": {
            "resample_role": "H1_CLUSTER_STRATUM",
            "stratum_domain": "DGP_family",
            "cluster_ordering": "cluster_id_ascii",
            "replacement": True,
            "target_estimand": "H1_SIZE_STD_POWER",
            "sample_size": 2000,
        },
        "REAL_ALL_ENDPOINTS_V1": {
            "resample_role": "REAL_SUBJECT",
            "stratum_domain": "subject_admitted",
            "cluster_ordering": "subject_opaque_id_ascii",
            "replacement": True,
            "target_estimand": "REAL_MARGINAL_DECISION_RATE",
            "sample_size": 2000,
        },
    }


def _analysis_spec(estimand_registry_hash_value: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "config_kind": "analysis_spec",
        "analysis_spec_version": "1.0",
        "estimand_spec_registry_hash": estimand_registry_hash_value,
        "bootstrap_plans": freeze.bootstrap_plans(_plans()),
        "holm": {"family": ["P1_D_OV_M0", "P2_D_ST_M0", "P3_D_CONS_M1"], "method": "holm_step_down", "alpha": "0.05"},
        "quantile_rule": "nearest_rank",
        "ci": {
            "wilson_z_90": "1.6448536269514722",
            "wilson_z_95": "1.959963984540054",
            "continuity_correction": False,
            "clopper_pearson_role": "auxiliary_only",
        },
        "classification": {
            "band": ["0.035", "0.065"],
            "labels": [
                "POINTWISE_PRACTICALLY_CALIBRATED",
                "MATERIAL_CONSERVATISM",
                "MATERIAL_ANTI_CONSERVATISM",
                "BOUNDARY_OR_INDETERMINATE",
            ],
            "rule": "wilson90_subset_band_or_wilson95_bounds",
        },
        "claim_states": [
            "UNTESTED",
            "SUPPORTED",
            "NOT_SUPPORTED",
            "INCONCLUSIVE",
            "DESCRIPTIVE_ONLY",
            "INVALIDATED",
            "SUPERSEDED",
        ],
        "no_extension_after_inconclusive": True,
    }


def _confirmed_w_star() -> tuple[int, str]:
    """``w*`` from the preregistered confirmation verdict (audit P0-3).

    ``COMPUTE_SPEC.w_star`` must come from the protocol's verdict rather than a
    hand-typed number: ``OWTDA_WSTAR_RC`` points at
    ``worker_confirmation_RC.json``.  Without it the previous frozen value is
    kept and that is recorded explicitly.
    """
    import os

    rc = os.environ.get("OWTDA_WSTAR_RC")
    if rc and Path(rc).exists():
        data = json.loads(Path(rc).read_text(encoding="utf-8"))
        if data.get("frozen_w_star_confirmed"):
            return int(data["frozen_w_star"]), f"{rc}:CONFIRMED"
        selected = data.get("selected_workers") or []
        if selected:
            return int(selected[0]), f"{rc}:AMENDED_FROM_MEASUREMENT"
    return 8, "PREVIOUS_FROZEN_VALUE (no confirmation RC supplied)"


def _compute_spec() -> dict[str, Any]:
    w_star, w_star_source = _confirmed_w_star()
    return {
        "schema_version": 1,
        "config_kind": "compute_spec",
        "w_star": w_star,
        "w_star_source": w_star_source,
        "w_star_confirmation_protocol": "configs/wstar/WSTAR_CONFIRMATION_PROTOCOL.json",
        "worker_consistency": "bitwise_identical_payload",
        "thread_env": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
        "budget_limits": {
            "h0_wall_hours": "192",
            "h1_wall_hours": "76.8",
            "core_wall_hours": "268.8",
            "peak_rss_gib": "24",
            "disk_rule": "estimated_peak_disk<=0.8*F_free",
        },
        "ph_windows": {"h0": 5750000, "h1": 2457600, "total": 8207600},
        "ripser": {"maxdim": 1, "thresh": "inf", "coeff": 2, "engine": "cpu"},
        "cache_key_fields": ["data_unit_id", "window_start", "W", "feature_config_hash"],
        "no_cross_cell_cache_reuse": True,
        "reference_environment": "registered_windows11_host_float64_frozen_lock_w_star",
    }


def _blas_vendor() -> str:
    try:
        cfg = np.show_config(mode="dicts")
        blas = cfg.get("Build Dependencies", {}).get("blas", {})
        return str(blas.get("name") or blas.get("version") or "unknown")
    except Exception:  # noqa: BLE001  # pragma: no cover - numpy build dependent
        return "unknown"


def _compute_freeze(w_star: int) -> dict[str, Any]:
    thread_vars = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    return {
        "schema_version": 1,
        "kind": "compute_freeze",
        "freeze_date": FREEZE_DATE,
        "w_star": w_star,
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": _scipy_version(),
        "ripser": _ripser_version(),
        "blas_vendor": _blas_vendor(),
        "cpu_count": os.cpu_count(),
        "thread_env_observed": {v: os.environ.get(v, "unset") for v in thread_vars},
        "gpu_used": False,
        # P0-2: the 8-replicate / pre-amendment budget probes are historical
        # diagnostics; the authoritative budget basis is the preregistered w*
        # confirmation on the full 32-replicate worklist (audit supplement R1).
        "budget_evidence": (
            "OWTDA-CAL-R1-AUDIT-SUPPLEMENT-R1-20260910.zip:/wstar/worker_confirmation_RC.json"
        ),
        "budget_evidence_superseded": ["artifacts/audit/compute_budget_RC.json", "artifacts/audit/worker_sweep_RC.json"],
        "superseded_evidence_status": "HISTORICAL_DIAGNOSTIC_ONLY",
    }


def _scipy_version() -> str:
    try:
        import scipy

        return scipy.__version__
    except ImportError:  # pragma: no cover
        return "absent"


def _ripser_version() -> str:
    try:
        import ripser

        return str(getattr(ripser, "__version__", "unknown"))
    except ImportError:  # pragma: no cover
        return "absent"


def _git_tracked(prefixes: tuple[str, ...]) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", *prefixes],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _load_local_secrets() -> dict[str, str]:
    """Load-or-create the isolated REAL secrets (git-ignored, never committed)."""
    data: dict[str, str] = {}
    if SECRETS_FILE.exists():
        data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    changed = False
    for name in ("real_task_root_key", "real_task_id_salt"):
        if name not in data:
            data[name] = secrets.token_bytes(32).hex()
            changed = True
    if changed:
        SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRETS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return data


def _seed_entries(fid: str) -> list[dict[str, Any]]:
    path = GOV / "SEED_REGISTRY_v1.0.json"
    prior: dict[tuple[str, str, str], dict[str, Any]] = {}
    prior_by_phase_family: dict[tuple[str, str], dict[str, Any]] = {}
    if path.exists():
        for entry in json.loads(path.read_text(encoding="utf-8"))["entries"]:
            prior[
                (entry["phase"], entry["stream_family"], entry["component_generation_id"])
            ] = entry
            prior_by_phase_family[(entry["phase"], entry["stream_family"])] = entry
    local = _load_local_secrets()
    entries = []
    for phase, family, generation in SEED_ROOT_FAMILIES:
        registry.assert_family_phase_allowed(family, phase)
        registry.assert_smoke_formal_separation(phase, family)
        common = {
            "project_id": PROJECT_ID,
            "protocol_id": PROTOCOL_ID,
            "freeze_id": fid,
            "evidence_generation_id": EVIDENCE_GENERATION_ID,
            "phase": phase,
            "stream_family": family,
            "component_generation_id": generation,
        }
        if family in ISOLATED_FAMILIES:
            secret_name = SECRET_KEY_BY_FAMILY[family]
            entries.append(
                registry.seed_entry(
                    **common,
                    secret_ref=f"local_secret_store://REAL_TASK_SECRETS/{secret_name}",
                    root_key_commitment_hex=hashlib.sha256(
                        bytes.fromhex(local[secret_name])
                    ).hexdigest(),
                )
            )
            continue
        # A smoke-generation bump (Plan §9.3) must re-key every *derived* seed
        # through the stream payload, not by silently minting a new phase root
        # key: keep the family's existing key so the generation id is the only
        # thing that changes.
        old = prior.get((phase, family, generation)) or prior_by_phase_family.get(
            (phase, family)
        )
        key_hex = (
            old["root_key_hex"]
            if old and old.get("root_key_hex")
            else secrets.token_bytes(32).hex()
        )
        entries.append(registry.seed_entry(**common, root_key_hex=key_hex))
    return sorted(
        entries,
        key=lambda e: (
            e["project_id"],
            e["protocol_id"],
            e["freeze_id"],
            e["evidence_generation_id"],
            e["phase"],
            e["stream_family"],
            e["component_generation_id"],
        ),
    )


def _component_entries(fid: str) -> list[dict[str, Any]]:
    entries = []
    for definition in components.component_definitions():
        manifests = freeze.file_manifest_entries(
            [REPO / f for f in definition["code_files"]], root=REPO
        )
        entries.append(
            registry.component_entry(
                project_id=PROJECT_ID,
                protocol_id=PROTOCOL_ID,
                freeze_id=fid,
                evidence_generation_id=EVIDENCE_GENERATION_ID,
                component_kind=definition["component_kind"],
                stable_id=definition["stable_id"],
                component_generation_id=COMPONENT_GENERATION_BY_KIND[
                    definition["component_kind"]
                ],
                config_hash=definition["config_hash"],
                code_file_manifest_hash=freeze.source_tree_hash(manifests),
            )
        )
    return sorted(
        entries,
        key=lambda e: (
            e["project_id"],
            e["protocol_id"],
            e["freeze_id"],
            e["evidence_generation_id"],
            e["component_kind"],
            e["stable_id"],
            e["component_generation_id"],
        ),
    )


def _write_real_disposition(fid: str) -> dict[str, Any]:
    path = GOV / "REAL_DISPOSITION.jsonl"
    if not path.exists():
        reason = disposition.reason_object(
            reason_code="TASK_GATE_MIN_TASKS_NOT_MET", **REAL_RC_EVIDENCE
        )
        r_hash = disposition.reason_object_hash(reason)
        _write_json(GOV / f"REAL_DISPOSITION_REASON_{r_hash}.json", reason)
        genesis = disposition.genesis_hash(
            project_id=PROJECT_ID,
            protocol_id=PROTOCOL_ID,
            freeze_id=fid,
            evidence_generation_id=EVIDENCE_GENERATION_ID,
        )
        event = disposition.event(
            project_id=PROJECT_ID,
            protocol_id=PROTOCOL_ID,
            freeze_id=fid,
            evidence_generation_id=EVIDENCE_GENERATION_ID,
            disposition_status="REAL_OMITTED_BY_DATA_GATE",
            disposition_stage="REAL_DATA_FROZEN",
            reason_code="TASK_GATE_MIN_TASKS_NOT_MET",
            reason_object_hash_value=r_hash,
            task_index_seal_hash=None,
            truth_unsealed=False,
            prev_real_disposition_event_hash=genesis,
        )
        chains.append_cas(str(path), event, expected_tip=None, hash_field="disposition_hash")
    info = disposition.validate_chain(path)
    if info["latest_status"] != "REAL_OMITTED_BY_DATA_GATE":
        raise ValueError("existing REAL_DISPOSITION chain has unexpected status")
    info["reason_object_hash"] = disposition.read_events(path)[-1]["reason_object_hash"]
    return info


def main() -> int:
    gov = REPO / "governance"

    scope_spec = _scope_spec()
    _write_json(gov / "SCOPE_SPEC_v1.json", scope_spec)
    s_hash = freeze.scope_spec_hash(scope_spec)

    protocol = _protocol_content()
    _write_json(gov / "PROTOCOL_CONTENT_v1.json", protocol)
    p_hash = freeze.protocol_content_hash(protocol)

    estimand_registry = freeze.estimand_registry(_estimands())
    _write_json(gov / "ESTIMAND_SPEC_REGISTRY_v1.json", estimand_registry)
    e_hash = freeze.estimand_registry_hash(estimand_registry)

    analysis = _analysis_spec(e_hash)
    _write_json(gov / "ANALYSIS_SPEC_v1.0.json", analysis)
    a_hash = freeze.analysis_spec_hash(analysis)

    compute = _compute_spec()
    _write_json(gov / "COMPUTE_SPEC_v1.json", compute)
    c_hash = freeze.compute_spec_hash(compute)

    fid = scope.freeze_id(
        project_id=PROJECT_ID,
        protocol_id=PROTOCOL_ID,
        protocol_content_hash=p_hash,
        scope_spec_hash=s_hash,
        analysis_spec_hash=a_hash,
        compute_spec_hash=c_hash,
    )

    scope_design: dict[str, dict[str, Any]] = {}
    for phase, tag in ((scope.PHASE_NULL, "NULL"), (scope.PHASE_ALT, "ALT")):
        rows = scope.scope_design_rows(
            project_id=PROJECT_ID,
            protocol_id=PROTOCOL_ID,
            freeze_id=fid,
            evidence_generation_id=EVIDENCE_GENERATION_ID,
            phase=phase,
        )
        d_hash = freeze.scope_design_hash(phase, rows)
        text = freeze.scope_design_csv_text(rows)
        name = f"SCOPE_DESIGN_{tag}_{d_hash}.csv"
        (gov / name).write_text(text, encoding="utf-8")
        scope_design[phase] = {
            "file": name,
            "scope_design_hash": d_hash,
            "rows": len(rows),
            "csv_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    _write_json(gov / "COMPUTE_FREEZE.json", _compute_freeze(compute["w_star"]))

    seed_entries = _seed_entries(fid)
    registry.validate_seed_registry(seed_entries)
    _write_json(gov / "SEED_REGISTRY_v1.0.json", {"schema_version": 1, "entries": seed_entries})

    component_entries = _component_entries(fid)
    registry.validate_component_registry(component_entries)
    _write_json(
        gov / "COMPONENT_REGISTRY_v1.json",
        {"schema_version": 1, "entries": component_entries},
    )

    # REAL is omitted before any formal task index exists, so no candidate /
    # ground-truth salt entries may be minted for a task-index generation.
    _write_json(
        gov / "SECRET_COMMITMENT_REGISTRY_v1.0.json",
        {"schema_version": 1, "entries": [], "reveal_events": []},
    )

    disposition_info = _write_real_disposition(fid)

    # P0-2: the environment lock must cover the real environment, not only
    # pyproject/COMPUTE_FREEZE: the lock file, the tool/version map, the observed
    # thread variables and the fresh-venv rebuild test all enter the hash.
    env_files = [REPO / "pyproject.toml", gov / "COMPUTE_FREEZE.json"]
    uv_lock = REPO / "uv.lock"
    if uv_lock.exists():
        env_files.append(uv_lock)
    env_evidence = sorted((REPO / "environment").glob("*")) if (REPO / "environment").is_dir() else []
    env_files.extend(p for p in env_evidence if p.is_file())
    env_entries = freeze.file_manifest_entries(env_files, root=REPO)
    env_hash = freeze.environment_lock_hash(env_entries)

    src_files = _git_tracked(SOURCE_TREE_PREFIXES)
    src_entries = freeze.file_manifest_entries([REPO / f for f in src_files], root=REPO)
    src_hash = freeze.source_tree_hash(src_entries)

    manifest = freeze.build_freeze_manifest(
        project_id=PROJECT_ID,
        protocol_id=PROTOCOL_ID,
        freeze_id=fid,
        evidence_generation_id=EVIDENCE_GENERATION_ID,
        protocol_content_hash_value=p_hash,
        scope_spec_hash_value=s_hash,
        analysis_spec_hash_value=a_hash,
        compute_spec_hash_value=c_hash,
        scope_design=scope_design,
        source_tree_hash_value=src_hash,
        environment_lock_hash_value=env_hash,
        component_generations=COMPONENT_GENERATIONS,
    )
    manifest["estimand_spec_registry_hash"] = e_hash
    manifest["source_tree_manifest"] = src_entries
    manifest["environment_lock_manifest"] = env_entries
    manifest["seed_registry_snapshot_hash"] = registry.registry_snapshot_hash(
        [e["root_entry_hash"] for e in seed_entries]
    )
    manifest["component_registry_snapshot_hash"] = registry.registry_snapshot_hash(
        [e["component_registry_entry_hash"] for e in component_entries]
    )
    manifest["secret_registry_snapshot_hash"] = registry.registry_snapshot_hash([])
    manifest["real_disposition"] = {
        "chain_file": "governance/REAL_DISPOSITION.jsonl",
        "tip_hash": disposition_info["tip_hash"],
        "event_count": disposition_info["event_count"],
        "latest_status": disposition_info["latest_status"],
        "latest_stage": disposition_info["latest_stage"],
        "truth_unsealed": disposition_info["truth_unsealed"],
        "reason_object_hash": disposition_info["reason_object_hash"],
    }
    _write_json(gov / "FREEZE_MANIFEST.json", manifest)

    print(f"protocol_content_hash = {p_hash}")
    print(f"scope_spec_hash       = {s_hash}")
    print(f"estimand_registry_hash= {e_hash}")
    print(f"analysis_spec_hash    = {a_hash}")
    print(f"compute_spec_hash     = {c_hash}")
    print(f"freeze_id             = {fid}")
    for phase, info in scope_design.items():
        print(f"SCOPE_DESIGN[{phase}] = {info['file']} rows={info['rows']}")
    print(f"source_tree_hash      = {src_hash} ({len(src_entries)} files)")
    print(f"environment_lock_hash = {env_hash} ({len(env_entries)} files)")
    print(f"manifest              = {gov / 'FREEZE_MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
