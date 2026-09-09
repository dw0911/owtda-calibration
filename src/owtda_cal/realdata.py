"""PAMAP2 scientific data identity (Plan §13.2).

``dataset_hash = H("pamap2_protocol_dataset", manifest_entries=<sorted list of
{path, size, file_sha256}>)`` over the nine ``Protocol/subject10X.dat`` files
only.  The outer/inner ZIPs and ``readme.pdf`` are provenance-only and never
enter ``dataset_hash``.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from .hashing import file_sha256
from .identity import H, is_sha256_hex

SUBJECTS = (f"subject10{i}.dat" for i in range(1, 10))
SUBJECT_NAMES = [f"subject10{i}.dat" for i in range(1, 10)]
PROTOCOL_REL_DIR = "Protocol"
DATASET_HASH_ID = "pamap2_protocol_dataset"


def protocol_entries(base_dir: str) -> list[dict]:
    """Compute the nine Protocol manifest entries from a local base directory.

    ``base_dir`` must contain a ``Protocol/`` directory with the nine files.
    """
    out = []
    for name in SUBJECT_NAMES:
        path = f"{PROTOCOL_REL_DIR}/{name}"
        fp = os.path.join(base_dir, PROTOCOL_REL_DIR, name)
        if not os.path.exists(fp):
            raise FileNotFoundError(fp)
        out.append({"path": path, "size": os.path.getsize(fp), "file_sha256": file_sha256(fp)})
    return out


def dataset_hash(entries: Iterable[dict]) -> str:
    """PAMAP2 scientific dataset hash over the nine Protocol entries."""
    normalized = validate_entries(entries)
    return H(DATASET_HASH_ID, manifest_entries=normalized)


def validate_entries(entries: Iterable[dict]) -> list[dict]:
    """Validate/normalise nine {path,size,file_sha256} entries (sorted)."""
    items = list(entries)
    if len(items) != len(SUBJECT_NAMES):
        raise ValueError(f"PAMAP2 dataset_hash needs exactly {len(SUBJECT_NAMES)} entries")
    out = []
    for entry in items:
        if set(entry) != {"path", "size", "file_sha256"}:
            raise ValueError(f"entry keys must be path/size/file_sha256: {entry}")
        path = entry["path"]
        if not (isinstance(path, str) and path.startswith(f"{PROTOCOL_REL_DIR}/")
                and path.count("/") == 1):
            raise ValueError(f"invalid Protocol relative path: {path!r}")
        size = entry["size"]
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"size must be positive int: {entry}")
        if not is_sha256_hex(entry["file_sha256"]):
            raise ValueError(f"invalid file_sha256: {entry}")
        out.append(
            {"path": path, "size": size, "file_sha256": entry["file_sha256"]}
        )
    out.sort(key=lambda e: e["path"])
    expected_paths = [f"{PROTOCOL_REL_DIR}/{n}" for n in SUBJECT_NAMES]
    if [e["path"] for e in out] != expected_paths:
        raise ValueError("entries must be exactly Protocol/subject101..109.dat")
    return out


__all__ = [
    "SUBJECT_NAMES",
    "PROTOCOL_REL_DIR",
    "DATASET_HASH_ID",
    "protocol_entries",
    "dataset_hash",
    "validate_entries",
]
