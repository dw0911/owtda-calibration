"""Deterministic ordered parallelism (Plan §9.3-§9.4, attack #8/#9/#12).

Workers are used only for embarrassingly parallel, pure per-item computation.
Results are always reassembled in input order, so ``workers=1`` and any
``workers=w`` produce bit-identical scientific payloads; task submission order
cannot change the output.

Global NumPy RNG entry points (the ``np.random`` module-level functions such as
seed/rand/permutation/normal) are forbidden in scientific code: every stream
must come from ``seeding.make_rng``.  ``scan_for_global_numpy_random`` is the
static attack that enforces this; note that source text must not spell out the
forbidden pattern (not even in docstrings), so this module phrases it
descriptively.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

from . import features

T = TypeVar("T")
R = TypeVar("R")

# ``Generator``/``PCG64DXSM``/``SeedSequence``/``default_rng`` create *local*
# generators and never touch global state, so they are allowed.
_ALLOWED_NUMPY_RANDOM = frozenset({"Generator", "PCG64DXSM", "SeedSequence", "default_rng"})
_NUMPY_RANDOM_RE = re.compile(r"\bnp\.random\.([A-Za-z_][A-Za-z0-9_]*)")


def _apply_chunk(args: tuple[Callable[[T], R], Sequence[T]]) -> list[R]:
    func, chunk = args
    return [func(item) for item in chunk]


def ordered_map(
    func: Callable[[T], R],
    items: Iterable[T],
    *,
    workers: int = 1,
    chunk_size: int | None = None,
) -> list[R]:
    """Map ``func`` over ``items`` with ordered reassembly (bit-stable)."""
    seq = list(items)
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    if workers == 1 or len(seq) <= 1:
        return [func(item) for item in seq]
    size = chunk_size or max(1, math.ceil(len(seq) / (workers * 2)))
    chunks = [seq[i : i + size] for i in range(0, len(seq), size)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        chunk_results = list(pool.map(_apply_chunk, [(func, c) for c in chunks]))
    out: list[R] = []
    for part in chunk_results:
        out.extend(part)
    return out


def feature_chunk(payload: tuple[list[np.ndarray], str, str]) -> np.ndarray:
    """Worker entry point (module level so it stays picklable)."""
    windows, feature_kind, scenario = payload
    return features.feature_matrix_for_windows(
        windows, feature_kind=feature_kind, scenario=scenario
    )


def feature_matrix_parallel(
    windows_raw: Iterable[np.ndarray],
    *,
    feature_kind: str,
    scenario: str,
    workers: int = 1,
    chunk_size: int | None = None,
) -> np.ndarray:
    """Window feature matrix, computed in ordered chunks.

    Identical to ``features.feature_matrix_for_windows`` for every worker
    count; the serial path is used directly so ``workers=1`` is the reference.
    """
    windows = list(windows_raw)
    if workers == 1 or len(windows) <= 1:
        return features.feature_matrix_for_windows(
            windows, feature_kind=feature_kind, scenario=scenario
        )
    size = chunk_size or max(1, math.ceil(len(windows) / (workers * 2)))
    chunks = [windows[i : i + size] for i in range(0, len(windows), size)]
    payloads = [(c, feature_kind, scenario) for c in chunks]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        mats = list(pool.map(feature_chunk, payloads))
    return np.ascontiguousarray(np.vstack(mats))


def scan_for_global_numpy_random(*roots: str | Path) -> list[dict[str, Any]]:
    """Static attack: report forbidden global ``np.random.*`` call sites."""
    violations: list[dict[str, Any]] = []
    for root in roots:
        for path in sorted(Path(root).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in _NUMPY_RANDOM_RE.finditer(line):
                    if match.group(1) not in _ALLOWED_NUMPY_RANDOM:
                        violations.append(
                            {
                                "file": str(path),
                                "line": lineno,
                                "call": match.group(0),
                                "text": line.strip(),
                            }
                        )
    return violations


__all__ = [
    "ordered_map",
    "feature_chunk",
    "feature_matrix_parallel",
    "scan_for_global_numpy_random",
]
