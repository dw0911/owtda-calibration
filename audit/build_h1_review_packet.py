"""Build the H1 construct-review packet (audit item: PENDING_CODE_REVIEW).

The material-admission verdict left exactly one audit item that needs no new
computation: ``H1-ALTERNATIVE-CONSTRUCT-CONTRACTS = PENDING_CODE_REVIEW``.  This
tool answers it with a *recomputable* packet rather than prose:

  * every reviewed function is pinned by the SHA-256 of its exact source text, so
    a reviewer can diff the reviewed code against the delivered revision;
  * every construct claim carries a live, recomputed value and a tolerance, plus
    the name of the test that locks it (a cited test that does not exist is
    reported as ``MISSING_TEST`` — the packet fails closed on its own evidence);
  * claims that are deliberately **not** made are listed explicitly (no
    second-order process matching; independent streams, not shared draws).

Outputs ``governance/H1_CONSTRUCT_REVIEW_PACKET.json`` and ``.md``.

Usage::

    python audit/build_h1_review_packet.py
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import cells, dgp, scan, scope

GOV = REPO / "governance"
TESTS = REPO / "tests/test_h1_dgp.py"
REVIEWED = (
    "h1_data_model_spec",
    "h1_change_point",
    "generate_h1_master",
    "build_null_signature",
    "H1Master.raw_prefix",
)
#: Uniform grid for the map moments; the trapezoid rule is exact for the integer
#: harmonics of both maps, so the reported values are machine-precision, not MC.
GRID = 4096
#: float64 rounding budget for quantities that are algebraic identities.
FP_TOL = 1e-15


def _source_digest(func: Any) -> dict[str, Any]:
    lines, start = inspect.getsourcelines(func)
    text = "".join(lines)
    return {
        "qualname": func.__qualname__,
        "file": str(Path(inspect.getsourcefile(func)).relative_to(REPO)).replace("\\", "/"),
        "first_line": start,
        "line_count": len(lines),
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _cited_tests() -> set[str]:
    """Every test name in the suite: a cited test that does not exist fails the packet."""
    names: set[str] = set()
    for path in sorted((REPO / "tests").glob("test_*.py")):
        names.update(
            re.findall(r"^    def (test_\w+)", path.read_text(encoding="utf-8"),
                       flags=re.MULTILINE)
        )
    return names


def _map_moments(u: np.ndarray) -> dict[str, Any]:
    """Exact (trapezoid) mean/covariance of the two unit-circle-family maps."""
    circle = np.column_stack([np.cos(2 * np.pi * u), np.sin(2 * np.pi * u)])
    figure = np.column_stack([np.sin(2 * np.pi * u), np.sin(4 * np.pi * u)])

    def stats(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return a.mean(axis=0), np.cov(a, rowvar=False, bias=True)

    c_mean, c_cov = stats(circle)
    f_mean, f_cov = stats(figure)
    half_i = 0.5 * np.eye(2)
    return {
        "grid_points": int(u.size),
        "circle_mean": [float(v) for v in c_mean],
        "figure_eight_mean": [float(v) for v in f_mean],
        "circle_covariance": c_cov.tolist(),
        "figure_eight_covariance": f_cov.tolist(),
        "max_abs_mean_difference": float(np.abs(c_mean - f_mean).max()),
        "max_abs_covariance_difference": float(np.abs(c_cov - f_cov).max()),
        "max_abs_covariance_to_half_identity": float(np.abs(c_cov - half_i).max()),
    }


def _cell_evidence() -> dict[str, Any]:
    fields = {
        "data_generation_id": "G01",
        "master_replicate_id": "review-packet",
    }
    root = "5a" * 32
    per_cell: list[dict[str, Any]] = []
    for cell in scope.h1_alt_cells():
        signature = dgp.build_null_signature(
            rho=cell.rho, W=cell.W, stride=cell.stride, T=cell.T, M=cell.M
        )
        per_cell.append(
            {
                "scenario": cell.scenario,
                "rho": cell.rho,
                "W": cell.W,
                "stride": cell.stride,
                "T": cell.T,
                "M": cell.M,
                "change_point_tau": dgp.h1_change_point(cell.T),
                "null_model_config_hash": signature,
                "source_null_logical_cell_id": scope.logical_cell_id(
                    project_id="owtda-cal-r1",
                    protocol_id="OWTDA-CAL-R1-PROTOCOL-v1.0",
                    freeze_id="0" * 64,
                    evidence_generation_id="G01",
                    phase=scope.PHASE_ALT,
                    DGP_family=dgp.DGP_FAMILY_H1,
                    scenario_id=cell.scenario,
                    rho=cell.rho,
                    W=cell.W,
                    stride=cell.stride,
                    T=cell.T,
                    M=cell.M,
                ),
            }
        )

    shape = dgp.generate_h1_master(
        scenario=dgp.H1_SCENARIO_SHAPE, rho="0.8", root_key_hex=root,
        data_generation_id="G01", master_replicate_id="review-packet",
        stream_prefix="review_", stream_fields=fields,
    )
    mean = dgp.generate_h1_master(
        scenario=dgp.H1_SCENARIO_MEAN, rho="0.8", root_key_hex=root,
        data_generation_id="G01", master_replicate_id="review-packet",
        stream_prefix="review_", stream_fields=fields,
    )
    t_long, t_short = cells.L_MASTER, cells.T_FIXED_T
    tau_long = dgp.h1_change_point(t_long)
    tau_short = dgp.h1_change_point(t_short)

    u = shape.latent_u
    circle = np.column_stack([np.cos(2 * np.pi * u), np.sin(2 * np.pi * u)])
    figure = np.column_stack([np.sin(2 * np.pi * u), np.sin(4 * np.pi * u)])
    scale = dgp.NOISE_SCALE_FLOAT
    shape_skeleton = shape.raw_prefix(t_long) - scale * shape.noise
    shift_v = np.asarray(mean.shift_direction_v, dtype=np.float64)
    mean_skeleton = mean.raw_prefix(t_long) - scale * mean.noise
    post_offset = mean_skeleton[tau_long:] - circle[tau_long:]

    # Independent re-composition of the documented generator expression, in the
    # same operand order, so the raw series can be checked *bitwise* (the stronger
    # claim) while skeleton recovery is only checkable to float64 rounding.
    post_mask = (np.arange(1, t_long + 1) > tau_long).reshape(-1, 1)
    expected_shape = np.ascontiguousarray(
        np.where(post_mask, figure, circle)[:t_long] + scale * shape.noise[:t_long]
    )
    expected_mean = np.ascontiguousarray(
        circle[:t_long]
        + (dgp.H1_MEAN_SHIFT_DELTA_FLOAT * post_mask * shift_v)
        + scale * mean.noise[:t_long]
    )

    def alignment(t: int, stride: int) -> dict[str, Any]:
        """Plan §12.4 blocking gate: the k=96 candidate centre *is* tau_true."""
        tau = dgp.h1_change_point(t)
        tau_true = tau + 0.5
        centre_96 = scan.estimated_change_raw_time(96, stride=stride, W=cells.W_FIXED)
        centre_97 = scan.estimated_change_raw_time(97, stride=stride, W=cells.W_FIXED)
        # sample-centre convention: (k-1)s + W/2 (differs from the scan convention
        # by the half-sample offset that defines tau_true)
        sample_96 = (96 - 1) * stride + cells.W_FIXED / 2
        sample_97 = (97 - 1) * stride + cells.W_FIXED / 2
        return {
            "T": t,
            "stride": stride,
            "W": cells.W_FIXED,
            "tau": tau,
            "tau_true": tau_true,
            "k96_centre": centre_96,
            "k97_centre": centre_97,
            "sample_centre_step": centre_97 - centre_96,
            "tau_equals_midpoint_of_k96_k97": (sample_96 + sample_97) / 2.0 == tau,
            "tau_true_equals_k96_centre": centre_96 == tau_true,
            "max_abs_error": max(abs(centre_96 - tau_true), abs((sample_96 + sample_97) / 2.0 - tau)),
        }

    return {
        "cells": per_cell,
        "distinct_null_signatures": sorted({c["null_model_config_hash"] for c in per_cell}),
        # The k=96 gate is stated per H1 geometry (s=64 <-> T=12288,
        # s=16 <-> T=3120), not for the cross product.
        "change_point_alignment": [
            alignment(cell.T, cell.stride) for cell in scope.h1_alt_cells()
        ],
        "shape_map_identity": {
            "raw_series_bitwise_equal_to_documented_composition": bool(
                np.array_equal(shape.raw_prefix(t_long), expected_shape)
            ),
            "pre_skeleton_equal_within_fp_rounding": bool(
                np.allclose(shape_skeleton[:tau_long], circle[:tau_long], rtol=0, atol=FP_TOL)
            ),
            "post_skeleton_equal_within_fp_rounding": bool(
                np.allclose(shape_skeleton[tau_long:], figure[tau_long:], rtol=0, atol=FP_TOL)
            ),
            "max_abs_skeleton_residual": float(
                max(
                    np.abs(shape_skeleton[:tau_long] - circle[:tau_long]).max(),
                    np.abs(shape_skeleton[tau_long:] - figure[tau_long:]).max(),
                )
            ),
            "max_abs_figure_eight_identity_residual": float(
                np.abs(
                    figure[tau_long:, 1] ** 2
                    - 4 * figure[tau_long:, 0] ** 2 * (1 - figure[tau_long:, 0] ** 2)
                ).max()
            ),
        },
        "mean_shift_identity": {
            "raw_series_bitwise_equal_to_documented_composition": bool(
                np.array_equal(mean.raw_prefix(t_long), expected_mean)
            ),
            "pre_skeleton_equal_within_fp_rounding": bool(
                np.allclose(mean_skeleton[:tau_long], circle[:tau_long], rtol=0, atol=FP_TOL)
            ),
            "post_offset_equals_delta_v_within_fp_rounding": bool(
                np.allclose(
                    post_offset,
                    np.broadcast_to(
                        dgp.H1_MEAN_SHIFT_DELTA_FLOAT * shift_v,
                        post_offset.shape,
                    ),
                    rtol=0, atol=FP_TOL,
                )
            ),
            "max_abs_offset_residual": float(
                np.abs(
                    post_offset
                    - np.broadcast_to(
                        dgp.H1_MEAN_SHIFT_DELTA_FLOAT * shift_v, post_offset.shape
                    )
                ).max()
            ),
            "delta": dgp.H1_MEAN_SHIFT_DELTA,
            "max_abs_unit_norm_error": float(abs(np.linalg.norm(shift_v) - 1.0)),
            "shift_value": mean.shift_direction_value,
            "shift_direction_seed_len": len(mean.shift_direction_seed or ""),
            "shape_alternative_reports_null_shift": shape.shift_direction_value is None
            and shape.shift_direction_seed is None,
        },
        "shared_draws_across_alternatives": {
            "innovation_hash_equal": shape.innovation_hash == mean.innovation_hash,
            "noise_hash_equal": shape.noise_hash == mean.noise_hash,
            "latent_path_equal": bool(np.array_equal(shape.latent_u, mean.latent_u)),
        },
        "rng_consumption": {
            "latent_innovation_shape": list(shape.innovations.shape),
            "latent_innovation_dtype": str(shape.innovations.dtype),
            "observation_noise_shape": list(shape.noise.shape),
            "observation_noise_c_order": bool(shape.noise.flags["C_CONTIGUOUS"]),
            "burn_in_discarded_index": dgp.INITIAL_INDEX,
            "formal_length": cells.L_MASTER,
        },
        "cross_length_prefix_consistency": {
            "draws_are_shared_prefixes": bool(
                np.array_equal(shape.noise[:t_short], shape.noise[:t_long][:t_short])
            ),
            "pre_effect_segments_agree_bitwise": bool(
                np.array_equal(
                    shape.raw_prefix(t_short)[:tau_short],
                    shape.raw_prefix(t_long)[:tau_short],
                )
            ),
            "post_effect_segments_differ_by_design": bool(
                not np.array_equal(shape.raw_prefix(t_short), shape.raw_prefix(t_long)[:t_short])
            ),
            "short_tau": tau_short,
            "long_tau": tau_long,
        },
    }


def _contracts(evidence: dict[str, Any], tests: set[str]) -> list[dict[str, Any]]:
    def ok(claim: str, kind: str, anchor: str, cited: list[str], observed: Any,
           tolerance: str, passed: bool) -> dict[str, Any]:
        missing = [name for name in cited if name not in tests]
        return {
            "claim": claim,
            "kind": kind,
            "anchor": anchor,
            "verified_by_tests": cited,
            "cited_tests_present": not missing,
            "missing_tests": missing,
            "observed": observed,
            "tolerance": tolerance,
            "status": "PASS" if passed and not missing else "FAIL",
        }

    s = evidence["shape_map_identity"]
    m = evidence["mean_shift_identity"]
    d = evidence["shared_draws_across_alternatives"]
    x = evidence["cross_length_prefix_consistency"]
    moments = evidence["map_moments"]
    return [
        ok(
            "tau = floor(T/2), the true continuous boundary is tau_true = tau + 1/2, "
            "and tau_true coincides exactly with the k=96 candidate window centre "
            "under the scan convention (Plan §12.4 blocking gate) for every H1 "
            "geometry; equivalently tau is the midpoint of the k=96/k=97 sample "
            "centres",
            "STRUCTURAL",
            "dgp.h1_change_point + scan.estimated_change_raw_time",
            ["test_floor_half_of_T", "test_boundary_sits_between_k96_and_k97_centres",
             "test_19_window_index_to_raw_time_hand_reversal", "test_hand_mapping"],
            evidence["change_point_alignment"], "exact float equality (error 0.0)",
            all(
                a["tau_true_equals_k96_centre"]
                and a["tau_equals_midpoint_of_k96_k97"]
                and a["max_abs_error"] == 0.0
                for a in evidence["change_point_alignment"]
            ),
        ),
        ok(
            "shape alternative: the raw series is bitwise the documented composition "
            "(skeleton + 0.08 eta, skeleton = C(u) before tau and "
            "F(u) = (sin 2pi u, sin 4pi u) after it); recovering the skeleton back "
            "out of the raw series is only exact to float64 rounding",
            "NUMERICAL",
            "dgp.generate_h1_master / H1Master.raw_prefix",
            ["test_shape_change_switches_circle_to_figure_eight",
             "test_figure_eight_identity_on_the_post_effect_half",
             "test_pre_effect_half_is_the_unit_circle"],
            s, "raw series bitwise; skeleton recovery and implicit identity <= 1e-15",
            s["raw_series_bitwise_equal_to_documented_composition"]
            and s["pre_skeleton_equal_within_fp_rounding"]
            and s["post_skeleton_equal_within_fp_rounding"]
            and s["max_abs_figure_eight_identity_residual"] <= FP_TOL,
        ),
        ok(
            "mean shift: the raw series is bitwise the documented composition "
            "(C(u) + 0.5 v 1(t>tau) + 0.08 eta) with |v| = 1",
            "NUMERICAL",
            "dgp.generate_h1_master / H1Master.raw_prefix",
            ["test_mean_shift_is_a_constant_unit_circle_offset",
             "test_shift_direction_is_a_single_random_draw"],
            m, "raw series bitwise; recovered offset <= 1e-15; |v|-1 <= 1e-15",
            m["raw_series_bitwise_equal_to_documented_composition"]
            and m["pre_skeleton_equal_within_fp_rounding"]
            and m["post_offset_equals_delta_v_within_fp_rounding"]
            and m["max_abs_unit_norm_error"] <= 1e-15,
        ),
        ok(
            "both maps have identical mean (0) and covariance (1/2 I_2) under "
            "U ~ Uniform(0,1); no claim of second-order process equality is made",
            "NUMERICAL",
            "audit/build_h1_review_packet.py::_map_moments",
            ["test_the_two_maps_share_mean_and_covariance",
             "test_marginal_moments_are_close_on_both_sides"],
            moments, "trapezoid grid exact for these harmonics; <= 1e-12",
            moments["max_abs_mean_difference"] <= 1e-12
            and moments["max_abs_covariance_difference"] <= 1e-12
            and moments["max_abs_covariance_to_half_identity"] <= 1e-12,
        ),
        ok(
            "both alternatives consume one shared latent path and one shared noise "
            "master (independent of rho, scenario, s, T, M)",
            "IDENTITY",
            "dgp.generate_h1_master",
            ["test_rho_free_and_scenario_free_base_draws",
             "test_alternatives_differ_only_in_scenario"],
            d, "hash equality + array equality",
            d["innovation_hash_equal"] and d["noise_hash_equal"]
            and d["latent_path_equal"],
        ),
        ok(
            "RNG consumption shapes are exactly (), [13288], [12288,2] in float64 "
            "C order with a 1000-step burn-in",
            "CONTRACT",
            "dgp.generate_h1_master",
            ["test_draw_shapes_and_dtypes", "test_raw_prefix_is_float64_c_order"],
            evidence["rng_consumption"], "exact shapes/dtypes",
            evidence["rng_consumption"]["latent_innovation_shape"] == [13288]
            and evidence["rng_consumption"]["observation_noise_shape"] == [12288, 2]
            and evidence["rng_consumption"]["observation_noise_c_order"],
        ),
        ok(
            "one master serves every T: the draws are shared prefixes and the "
            "pre-effect segment agrees bitwise up to the shorter tau; beyond it the "
            "series intentionally differ because tau = floor(T/2) is a cell property",
            "STRUCTURAL",
            "H1Master.raw_prefix",
            ["test_short_length_is_a_bitwise_prefix_of_the_long_length",
             "test_shared_draws_agree_between_strides"],
            x, "bitwise equality on the pre-effect segment; deliberate divergence after",
            x["draws_are_shared_prefixes"]
            and x["pre_effect_segments_agree_bitwise"]
            and x["post_effect_segments_differ_by_design"],
        ),
        ok(
            "every H1 cell rejoins the N-CIRCLE H0 model identity: eight distinct "
            "cells collapse to four null signatures, one per (rho, s)",
            "IDENTITY",
            "dgp.build_null_signature",
            ["test_signature_is_scenario_and_phase_independent",
             "test_signature_separates_geometries",
             "test_geometry_matches_the_n_circle_h0_cells"],
            {
                "cells": len(evidence["cells"]),
                "distinct_signatures": len(evidence["distinct_null_signatures"]),
            }, "8 cells -> 4 signatures",
            len(evidence["cells"]) == 8
            and len(evidence["distinct_null_signatures"]) == 4,
        ),
    ]


def main() -> int:
    u = (np.arange(GRID) + 0.5) / GRID
    evidence = _cell_evidence()
    evidence["map_moments"] = _map_moments(u)
    tests = _cited_tests()
    contracts = _contracts(evidence, tests)

    reviewed = []
    for name in REVIEWED:
        target: Any = dgp
        for part in name.split("."):
            target = getattr(target, part)
        reviewed.append(_source_digest(target))

    packet = {
        "schema_version": 1,
        "kind": "h1_construct_review_packet",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "answers_audit_item": "H1-ALTERNATIVE-CONSTRUCT-CONTRACTS = PENDING_CODE_REVIEW",
        "reviewed_functions": reviewed,
        "reviewed_function_source_sha256": {
            r["qualname"]: r["source_sha256"] for r in reviewed
        },
        "contracts": contracts,
        "all_contracts_pass": all(c["status"] == "PASS" for c in contracts),
        "evidence": evidence,
        "claims_not_made": [
            "no second-order process matching between the two segments: only "
            "pointwise mean and covariance of the maps coincide",
            "H1 cells do NOT reuse the N-CIRCLE H0 draws (streams differ); they "
            "rejoin the H0 *model identity*, which is what size/power comparison "
            "requires",
            "no size, power or rejection-rate value is claimed here; those are L2 "
            "and remain unstarted",
            "the finite-sample empirical moments of one realised path are not "
            "claimed to be exactly equal; equality holds for the maps' laws",
        ],
    }
    (GOV / "H1_CONSTRUCT_REVIEW_PACKET.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (GOV / "H1_CONSTRUCT_REVIEW_PACKET.md").write_text(_markdown(packet), encoding="utf-8")
    print(json.dumps(
        {
            "contracts": len(contracts),
            "all_pass": packet["all_contracts_pass"],
            "packet": "governance/H1_CONSTRUCT_REVIEW_PACKET.{json,md}",
        },
        ensure_ascii=False,
    ))
    return 0 if packet["all_contracts_pass"] else 1


def _markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# H1 alternative 构造效度复审包",
        "",
        f"生成时间（UTC）：{packet['generated_at_utc']}；回答审计项："
        f"`{packet['answers_audit_item']}`。",
        "",
        "> 本包所有取值均可在交付 revision 上重算："
        "`python audit/build_h1_review_packet.py`。引用不存在的测试会判 "
        "`MISSING_TEST`（自校验，失败即 FAIL）。",
        "",
        "## 1. 受审函数（按源码哈希固定）",
        "",
        "| 函数 | 文件 | 起止行 | 源码 SHA256 |",
        "|---|---|---|---|",
    ]
    for r in packet["reviewed_functions"]:
        lines.append(
            f"| `{r['qualname']}` | `{r['file']}` | {r['first_line']}–"
            f"{r['first_line'] + r['line_count'] - 1} | `{r['source_sha256'][:16]}…` |"
        )
    lines += ["", "## 2. 构造合同", "", "| # | 合同 | 类型 | 观测 | 判定 |", "|---|---|---|---|---|"]
    for i, c in enumerate(packet["contracts"], 1):
        observed = json.dumps(c["observed"], ensure_ascii=False)
        if len(observed) > 160:
            observed = observed[:157] + "…"
        lines.append(f"| {i} | {c['claim']} | {c['kind']} | `{observed}` | {c['status']} |")
    lines += ["", "### 各合同锁定的测试", ""]
    for i, c in enumerate(packet["contracts"], 1):
        cited = "、".join(f"`{t}`" for t in c["verified_by_tests"])
        lines.append(f"- **{i}** 锚点 `{c['anchor']}`（容差：{c['tolerance']}）→ {cited}")
    lines += ["", "## 3. 刻意不作的声明", ""]
    lines += [f"- {item}" for item in packet["claims_not_made"]]
    lines += [
        "",
        "## 4. 结论",
        "",
        f"- 合同数 {len(packet['contracts'])}，全部 PASS：**{packet['all_contracts_pass']}**；",
        f"- H1 cell 8 个 → null signature {len(packet['evidence']['distinct_null_signatures'])} 个"
        "（每 (rho, s) 一个），与对应 N-CIRCLE H0 单元一致。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
