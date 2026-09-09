"""ID hashes and registry hashes (Plan §15.1, §15.3, §15.4).

``H(id_kind, **named_fields)`` hashes
``canonical_json({"domain": "owtda-id-v1", "id_kind": id_kind, **named_fields})``;
the keys ``domain`` and ``id_kind`` are reserved in ``named_fields``.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from .canonical import CanonicalizationError, canonical_json_bytes

_ID_DOMAIN = "owtda-id-v1"
_RESERVED_ID_FIELDS = frozenset({"domain", "id_kind"})
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_KIND_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_HEX_RE.fullmatch(value))


def ensure_sha256_hex(value: Any, *, what: str = "value") -> None:
    if not is_sha256_hex(value):
        raise ValueError(f"{what} must be 64 lowercase hex, got {value!r}")


def H(id_kind: str, **named_fields: Any) -> str:
    if not isinstance(id_kind, str) or not _ID_KIND_RE.fullmatch(id_kind):
        raise ValueError(f"id_kind must match ^[a-z][a-z0-9_]*$, got {id_kind!r}")
    bad = _RESERVED_ID_FIELDS & named_fields.keys()
    if bad:
        raise ValueError(f"reserved ID payload key(s): {sorted(bad)}")
    payload = canonical_json_bytes(
        {"domain": _ID_DOMAIN, "id_kind": id_kind, **named_fields}
    )
    return hashlib.sha256(payload).hexdigest()


def config_hash(config_kind: str, schema_version: Any, config: Any) -> str:
    """config_hash = H("config", config_kind=..., schema_version=..., config=...)."""
    return H(
        "config",
        config_kind=config_kind,
        schema_version=schema_version,
        config=config,
    )


def _validate_relpath(path: Any) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("manifest path must be a non-empty string")
    if not path.isascii():
        # POSIX-portable paths are kept ASCII-safe for byte-identical replay.
        raise ValueError(f"manifest path must be ASCII: {path!r}")
    npath = unicodedata.normalize("NFC", path)
    if npath.startswith("/"):
        raise ValueError(f"manifest path must be relative: {path!r}")
    if "\\" in npath:
        raise ValueError(f"manifest path must use '/', no backslash: {path!r}")
    if any(ord(c) < 32 or ord(c) == 127 for c in npath):
        raise ValueError(f"manifest path contains control chars: {path!r}")
    if npath != path:
        raise ValueError(f"manifest path not NFC-normalised: {path!r}")
    for seg in npath.split("/"):
        if seg in ("", ".", ".."):
            raise ValueError(f"manifest path has empty/. /.. segment: {path!r}")
    return npath


def file_manifest_hash(manifest_entries: Iterable[dict[str, Any]]) -> str:
    """file_manifest_hash = H("file_manifest", manifest_entries=<sorted list>)."""
    entries = list(manifest_entries)
    normalized: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("manifest entry must be an object")
        if set(entry.keys()) != {"path", "size", "file_sha256"}:
            raise ValueError(f"manifest entry keys must be exactly path/size/file_sha256: {entry}")
        path = _validate_relpath(entry["path"])
        if path in seen_paths:
            raise ValueError(f"duplicate manifest path: {path!r}")
        seen_paths.add(path)
        size = entry["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"manifest size must be non-negative int: {entry}")
        ensure_sha256_hex(entry["file_sha256"], what="manifest file_sha256")
        normalized.append({"path": path, "size": size, "file_sha256": entry["file_sha256"]})
    normalized.sort(key=lambda e: e["path"])
    return H("file_manifest", manifest_entries=normalized)


def file_manifest_hash_from_tree(entries: Iterable[tuple[str, int, str]]) -> str:
    """Convenience: build entries from ``(path, size, sha256)`` triples."""
    return file_manifest_hash(
        [{"path": p, "size": n, "file_sha256": h} for (p, n, h) in entries]
    )


def expected_id_set_hash(ids: Iterable[str]) -> str:
    """expected_id_set_hash = H("expected_id_set", ids=<sorted, deduped list>)."""
    items = list(ids)
    for item in items:
        ensure_sha256_hex(item, what="expected id")
    dedup = sorted(set(items))
    return H("expected_id_set", ids=dedup)


def root_entry_hash(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    stream_family: str,
    component_generation_id: str,
    root_key_commitment: str,
) -> str:
    """root_entry_hash per Plan §15.1."""
    ensure_sha256_hex(root_key_commitment, what="root_key_commitment")
    return H(
        "root_entry",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        phase=phase,
        stream_family=stream_family,
        component_generation_id=component_generation_id,
        root_key_commitment=root_key_commitment,
    )


__all__ = [
    "CanonicalizationError",
    "H",
    "config_hash",
    "ensure_sha256_hex",
    "expected_id_set_hash",
    "file_manifest_hash",
    "file_manifest_hash_from_tree",
    "is_sha256_hex",
    "root_entry_hash",
]
