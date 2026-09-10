"""PAMAP2 transition-task construction (Plan §13.3).

Within one grid-contiguous analysis segment:
  * a ``bout`` is a maximal run of equal non-zero activity;
  * a candidate is ``A bout -> optional zero run -> B bout`` with
    ``activity_A != activity_B``, ``n_A, n_B >= 3000`` and ``0 <= n_0 <= 500``
    (zero run required to be a single maximal label-0 run when non-adjacent);
  * context lengths ``L_A, L_B in {20..30}`` come from HMAC rejection mapping
    on ``real_context_left/right`` streams (no modulo bias); equal values bump
    ``L_B`` cyclically by one;
  * the task array is A's last ``100*L_A`` rows + the zero run + B's first
    ``100*L_B`` rows; coordinates are ``sample_index=i+1`` and
    ``relative_s=i/100``; truth indices are ``a=100*L_A`` and
    ``b=100*L_A+n_0+1`` with interval ``[a+0.5, b-0.5]``.

Opaque ``task_id`` is HMAC-SHA256 over a canonical payload keyed by the
isolated ``real_task_id_salt``.  Sanitized task directories contain only the
opaque ID, the float64 signal, sample indices and relative seconds.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from .canonical import canonical_json_bytes
from .hashing import array_hash
from .identity import H

MIN_BOUT_ROWS = 3000
MAX_ZERO_RUN = 500
CONTEXT_MIN = 20
CONTEXT_SPAN = 11  # 20..30 inclusive
TASK_SIGNAL_OBJECT_KIND = "pamap2_chest_accel_task_v1"
TASK_ID_DOMAIN = "owtda-real-task-id-v1"
SEED_DOMAIN = "owtda-seed-v1"


class TaskBuildError(ValueError):
    """Task construction contract violation."""


@dataclass(frozen=True)
class Bout:
    activity: int
    start: int  # inclusive position inside the segment arrays
    end: int  # exclusive
    @property
    def n(self) -> int:
        return self.end - self.start


def bouts(activity: np.ndarray) -> list[Bout]:
    """Maximal runs of equal non-zero activity (input = one grid segment)."""
    out: list[Bout] = []
    i = 0
    n = activity.shape[0]
    while i < n:
        a = int(activity[i])
        j = i
        while j < n and int(activity[j]) == a:
            j += 1
        if a != 0:
            out.append(Bout(activity=a, start=i, end=j))
        i = j
    return out


def transition_candidates(
    activity: np.ndarray, *, min_rows: int = MIN_BOUT_ROWS, max_zero: int = MAX_ZERO_RUN
) -> list[dict]:
    """Candidate A->(zero)->B transitions inside one grid segment."""
    bs = bouts(activity)
    out = []
    for a, b in pairwise(bs):
        if a.activity == b.activity:
            continue
        if a.n < min_rows or b.n < min_rows:
            continue
        zero_rows = b.start - a.end
        if zero_rows > max_zero:
            continue
        if zero_rows > 0:
            gap = activity[a.end : b.start]
            if not np.all(gap == 0):
                continue
        out.append({"A": a, "B": b, "zero_rows": int(zero_rows)})
    return out


def candidate_identity(
    *,
    dataset_hash: str,
    relative_file_path: str,
    subject_internal_id: str,
    analysis_segment_id: int,
    activity_A: int,
    A_grid_start: int,
    A_grid_end: int,
    activity_B: int,
    B_grid_start: int,
    B_grid_end: int,
    zero_grid_start: int | None,
    zero_grid_end: int | None,
) -> dict:
    return {
        "dataset_hash": dataset_hash,
        "relative_file_path": relative_file_path,
        "subject_internal_id": subject_internal_id,
        "analysis_segment_id": analysis_segment_id,
        "activity_A": int(activity_A),
        "A_grid_start": int(A_grid_start),
        "A_grid_end": int(A_grid_end),
        "activity_B": int(activity_B),
        "B_grid_start": int(B_grid_start),
        "B_grid_end": int(B_grid_end),
        "zero_grid_start": None if zero_grid_start is None else int(zero_grid_start),
        "zero_grid_end": None if zero_grid_end is None else int(zero_grid_end),
    }


def task_candidate_id(identity: dict) -> str:
    return H("real_task_candidate", candidate_identity=identity)


def _hmac_first8(root_key_hex: str, stream_kind: str, payload_fields: dict) -> int:
    payload = canonical_json_bytes(
        {"domain": SEED_DOMAIN, "stream_kind": stream_kind, **payload_fields}
    )
    digest = hmac.new(bytes.fromhex(root_key_hex), payload, hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big")


def draw_context_length(
    *,
    root_key_hex: str,
    stream_kind: str,
    dataset_hash: str,
    task_candidate_id: str,
    task_index_generation_id: str,
    task_builder_config_hash: str,
) -> int:
    """Unbiased L in {20..30} via rejection mapping (Plan §15.2)."""
    if stream_kind not in ("real_context_left", "real_context_right"):
        raise TaskBuildError(f"bad context stream_kind {stream_kind!r}")
    limit = 2**64 - (2**64 % CONTEXT_SPAN)
    counter = 0
    while True:
        x = _hmac_first8(
            root_key_hex,
            stream_kind,
            {
                "dataset_hash": dataset_hash,
                "task_candidate_id": task_candidate_id,
                "task_index_generation_id": task_index_generation_id,
                "task_builder_config_hash": task_builder_config_hash,
                "counter": counter,
            },
        )
        if x < limit:
            return CONTEXT_MIN + (x % CONTEXT_SPAN)
        counter += 1


def draw_context_lengths(
    *,
    root_key_hex: str,
    dataset_hash: str,
    task_candidate_id: str,
    task_index_generation_id: str,
    task_builder_config_hash: str,
) -> tuple[int, int]:
    la = draw_context_length(
        root_key_hex=root_key_hex, stream_kind="real_context_left",
        dataset_hash=dataset_hash, task_candidate_id=task_candidate_id,
        task_index_generation_id=task_index_generation_id,
        task_builder_config_hash=task_builder_config_hash,
    )
    lb = draw_context_length(
        root_key_hex=root_key_hex, stream_kind="real_context_right",
        dataset_hash=dataset_hash, task_candidate_id=task_candidate_id,
        task_index_generation_id=task_index_generation_id,
        task_builder_config_hash=task_builder_config_hash,
    )
    if lb == la:
        lb = CONTEXT_MIN + ((lb - CONTEXT_MIN + 1) % CONTEXT_SPAN)
    return la, lb


def build_task(
    *,
    segment_chest_g: np.ndarray,
    segment_grid: np.ndarray,
    candidate: dict,
    L_A: int,
    L_B: int,
) -> dict:
    """Extract one task; returns arrays, truth and hashes."""
    a_bout: Bout = candidate["A"]
    b_bout: Bout = candidate["B"]
    n0 = candidate["zero_rows"]
    if not (CONTEXT_MIN <= L_A <= CONTEXT_MIN + CONTEXT_SPAN - 1):
        raise TaskBuildError(f"L_A out of range: {L_A}")
    if not (CONTEXT_MIN <= L_B <= CONTEXT_MIN + CONTEXT_SPAN - 1):
        raise TaskBuildError(f"L_B out of range: {L_B}")
    left = segment_chest_g[a_bout.end - 100 * L_A : a_bout.end]
    zero = segment_chest_g[a_bout.end : b_bout.start]
    right = segment_chest_g[b_bout.start : b_bout.start + 100 * L_B]
    if left.shape[0] != 100 * L_A or right.shape[0] != 100 * L_B or zero.shape[0] != n0:
        raise TaskBuildError("insufficient rows for requested context lengths")
    signal = np.ascontiguousarray(np.vstack([left, zero, right]), dtype=np.float64)
    T = signal.shape[0]
    sample_index = np.arange(1, T + 1, dtype=np.int64)
    relative_s = np.arange(T, dtype=np.float64) / 100.0
    a = 100 * L_A
    b = 100 * L_A + n0 + 1
    truth = {
        "truth_sample_left": a,
        "truth_sample_right": b,
        "truth_relative_s_left": (a - 0.5) / 100.0,
        "truth_relative_s_right": (b - 1.5) / 100.0,
        "T": T,
    }
    signal_hash = array_hash(TASK_SIGNAL_OBJECT_KIND, signal, dtype_code=">f8")
    return {
        "signal": signal,
        "sample_index": sample_index,
        "relative_s": relative_s,
        "truth": truth,
        "task_signal_hash": signal_hash,
        "L_A": L_A,
        "L_B": L_B,
    }


def task_id(
    *,
    real_task_id_salt_hex: str,
    task_candidate_id: str,
    task_index_generation_id: str,
    task_builder_config_hash: str,
    L_A: int,
    L_B: int,
    task_root_entry_hash: str,
    task_signal_hash: str,
) -> str:
    msg = canonical_json_bytes(
        {
            "domain": TASK_ID_DOMAIN,
            "task_candidate_id": task_candidate_id,
            "task_index_generation_id": task_index_generation_id,
            "task_builder_config_hash": task_builder_config_hash,
            "L_A": L_A,
            "L_B": L_B,
            "task_root_entry_hash": task_root_entry_hash,
            "task_signal_hash": task_signal_hash,
        }
    )
    return hmac.new(bytes.fromhex(real_task_id_salt_hex), msg, hashlib.sha256).hexdigest()


def write_sanitized_task(
    directory: str,
    *,
    task: dict,
    task_id_value: str,
) -> dict:
    """Write opaque task dir: signal (f8), sample index, relative seconds."""
    os.makedirs(directory, exist_ok=True)
    sig_path = os.path.join(directory, "signal.f64le")
    idx_path = os.path.join(directory, "sample_index.i64le")
    rel_path = os.path.join(directory, "relative_s.f64le")
    np.asarray(task["signal"], dtype="<f8").tofile(sig_path)
    np.asarray(task["sample_index"], dtype="<i8").tofile(idx_path)
    np.asarray(task["relative_s"], dtype="<f8").tofile(rel_path)
    manifest = {
        "schema_version": 1,
        "task_id": task_id_value,
        "T": int(task["signal"].shape[0]),
        "columns": ["x", "y", "z"],
        "files": ["signal.f64le", "sample_index.i64le", "relative_s.f64le"],
        "task_signal_hash": task["task_signal_hash"],
    }
    with open(os.path.join(directory, "task_manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n")
    return manifest


def eligibility_rows(per_subject_task_counts: dict[str, int]) -> list[dict]:
    """Nine-row eligibility table (Plan §13.3 step 13)."""
    rows = []
    for subject in sorted(per_subject_task_counts):
        count = int(per_subject_task_counts[subject])
        admitted = count >= 1
        rows.append(
            {
                "subject_internal_id": subject,
                "identity_gate_status": "PASS",
                "task_count": count,
                "subject_admitted": admitted,
                "nonadmission_reason": None if admitted else "NO_ELIGIBLE_TASK",
            }
        )
    return rows


def real_data_task_gate(eligibility: Iterable[dict], *, min_subjects: int = 8,
                        min_tasks: int = 24) -> dict:
    rows = list(eligibility)
    admitted = [r for r in rows if r["subject_admitted"]]
    tasks = sum(r["task_count"] for r in admitted)
    every_admitted_has_task = all(r["task_count"] >= 1 for r in admitted)
    ok = (
        len(admitted) >= min_subjects
        and tasks >= min_tasks
        and every_admitted_has_task
    )
    return {
        "admitted_subjects": len(admitted),
        "total_tasks": tasks,
        "every_admitted_subject_has_task": every_admitted_has_task,
        "pass": bool(ok),
        "requirements": {"min_subjects": min_subjects, "min_tasks": min_tasks},
    }


__all__ = [
    "MIN_BOUT_ROWS",
    "MAX_ZERO_RUN",
    "CONTEXT_MIN",
    "CONTEXT_SPAN",
    "TASK_SIGNAL_OBJECT_KIND",
    "TASK_ID_DOMAIN",
    "TaskBuildError",
    "Bout",
    "bouts",
    "transition_candidates",
    "candidate_identity",
    "task_candidate_id",
    "draw_context_length",
    "draw_context_lengths",
    "build_task",
    "task_id",
    "write_sanitized_task",
    "eligibility_rows",
    "real_data_task_gate",
]
