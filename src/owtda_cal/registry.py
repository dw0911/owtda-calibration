"""Registry entry builders/validators (Plan §15.1-§15.3).

Implements strict append-only registries:
  * SEED_REGISTRY entries (compound key unique, root key commitment,
    ``root_entry_hash`` via the §15.1 formula);
  * COMPONENT_REGISTRY entries (component kinds and generations);
  * SECRET_COMMITMENT_REGISTRY entries (candidate-manifest / ground-truth salts);
  * ``registry_snapshot_hash`` over the sorted deduped entry hashes.

Only validation/build logic lives here; no formal registry file is written
before the freeze batch (B14).
"""

from __future__ import annotations

from collections.abc import Iterable

from .identity import (
    H,
    ensure_sha256_hex,
    is_sha256_hex,
    root_entry_hash,
)
from .seeding import root_key_commitment

SECRET_KIND_CANDIDATE = "CANDIDATE_MANIFEST_SALT"
SECRET_KIND_TRUTH = "GROUND_TRUTH_SALT"
SECRET_KINDS = (SECRET_KIND_CANDIDATE, SECRET_KIND_TRUTH)

# stream_family -> allowed phase (Plan §15.2 table)
FAMILY_PHASES = {
    "smoke": {"SMOKE_NULL", "SMOKE_ALT"},
    "null_data": {"NULL"},
    "null_M0": {"NULL"},
    "null_M1": {"NULL"},
    "h1_data": {"ALT"},
    "h1_M0": {"ALT"},
    "h1_M1": {"ALT"},
    "real_task": {"REAL_TASK_BUILD"},
    "real_task_id_salt": {"REAL_TASK_BUILD"},
    "real_M0": {"REAL_PREDICTION"},
    "real_M1": {"REAL_PREDICTION"},
    "analysis_bootstrap": {"ANALYSIS"},
}

_SMOKE_PHASES = {"SMOKE_NULL", "SMOKE_ALT"}
_FORMAL_PHASES = {"NULL", "ALT", "REAL_TASK_BUILD", "REAL_PREDICTION"}


def assert_family_phase_allowed(stream_family: str, phase: str) -> None:
    allowed = FAMILY_PHASES.get(stream_family)
    if allowed is None:
        raise ValueError(f"unknown stream_family {stream_family!r}")
    if phase not in allowed:
        raise ValueError(
            f"stream_family {stream_family!r} not allowed for phase {phase!r}"
        )


def assert_smoke_formal_separation(phase: str, stream_family: str) -> None:
    """smoke phases may not use formal root families and vice versa."""
    if phase in _SMOKE_PHASES and stream_family != "smoke":
        raise ValueError(f"smoke phase {phase!r} must use stream_family 'smoke'")
    if phase in _FORMAL_PHASES and stream_family == "smoke":
        raise ValueError(f"formal phase {phase!r} must not use stream_family 'smoke'")


def seed_entry(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    phase: str,
    stream_family: str,
    component_generation_id: str,
    root_key_hex: str | None = None,
    secret_ref: str | None = None,
) -> dict:
    """Build a strict SEED_REGISTRY entry (root key or isolated secret_ref)."""
    if (root_key_hex is None) == (secret_ref is None):
        raise ValueError("exactly one of root_key_hex/secret_ref required")
    commitment = root_key_commitment(root_key_hex) if root_key_hex is not None else None
    entry_hash = root_entry_hash(
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        phase=phase,
        stream_family=stream_family,
        component_generation_id=component_generation_id,
        root_key_commitment=commitment if commitment is not None else "0" * 64,
    )
    return {
        "project_id": project_id,
        "protocol_id": protocol_id,
        "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "phase": phase,
        "stream_family": stream_family,
        "component_generation_id": component_generation_id,
        "root_key_hex": root_key_hex,
        "secret_ref": secret_ref,
        "root_key_commitment": commitment,
        "root_entry_hash": entry_hash,
    }


def validate_seed_registry(entries: Iterable[dict]) -> list[dict]:
    """Validate SEED_REGISTRY: unknown fields, compound-key uniqueness."""
    seen: set[tuple] = set()
    out = []
    for e in entries:
        expect = {
            "project_id", "protocol_id", "freeze_id", "evidence_generation_id",
            "phase", "stream_family", "component_generation_id", "root_key_hex",
            "secret_ref", "root_key_commitment", "root_entry_hash",
        }
        if set(e) != expect:
            raise ValueError(f"seed entry fields mismatch: {sorted(set(e) ^ expect)}")
        key = (
            e["project_id"], e["protocol_id"], e["freeze_id"],
            e["evidence_generation_id"], e["phase"], e["stream_family"],
            e["component_generation_id"],
        )
        if key in seen:
            raise ValueError(f"duplicate seed registry compound key: {key}")
        seen.add(key)
        ensure_sha256_hex(e["root_entry_hash"], what="root_entry_hash")
        if e["root_key_commitment"] is not None:
            ensure_sha256_hex(e["root_key_commitment"], what="root_key_commitment")
        out.append(e)
    return out


def component_entry(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    component_kind: str,
    stable_id: str,
    component_generation_id: str,
    config_hash: str,
    code_file_manifest_hash: str,
) -> dict:
    for h in (config_hash, code_file_manifest_hash):
        ensure_sha256_hex(h, what="component hash")
    entry_hash = H(
        "component_registry_entry",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        component_kind=component_kind,
        stable_id=stable_id,
        component_generation_id=component_generation_id,
        config_hash=config_hash,
        code_file_manifest_hash=code_file_manifest_hash,
    )
    return {
        "project_id": project_id,
        "protocol_id": protocol_id,
        "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "component_kind": component_kind,
        "stable_id": stable_id,
        "component_generation_id": component_generation_id,
        "config_hash": config_hash,
        "code_file_manifest_hash": code_file_manifest_hash,
        "component_registry_entry_hash": entry_hash,
    }


def validate_component_registry(entries: Iterable[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for e in entries:
        key = (
            e["project_id"], e["protocol_id"], e["freeze_id"],
            e["evidence_generation_id"], e["component_kind"], e["stable_id"],
            e["component_generation_id"],
        )
        if key in seen:
            raise ValueError(f"duplicate component key: {key}")
        seen.add(key)
        ensure_sha256_hex(e["component_registry_entry_hash"])
        out.append(e)
    return out


def secret_commitment_entry(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    task_index_generation_id: str,
    secret_kind: str,
    secret_ref: str,
    secret_commitment: str,
) -> dict:
    if secret_kind not in SECRET_KINDS:
        raise ValueError(f"secret_kind must be one of {SECRET_KINDS}")
    ensure_sha256_hex(secret_commitment, what="secret_commitment")
    entry_hash = H(
        "secret_commitment_entry",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        task_index_generation_id=task_index_generation_id,
        secret_kind=secret_kind,
        secret_commitment=secret_commitment,
    )
    return {
        "project_id": project_id,
        "protocol_id": protocol_id,
        "freeze_id": freeze_id,
        "evidence_generation_id": evidence_generation_id,
        "task_index_generation_id": task_index_generation_id,
        "secret_kind": secret_kind,
        "secret_ref": secret_ref,
        "secret_commitment": secret_commitment,
        "secret_entry_hash": entry_hash,
    }


def validate_secret_registry(entries: Iterable[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for e in entries:
        key = (
            e["project_id"], e["protocol_id"], e["freeze_id"],
            e["evidence_generation_id"], e["task_index_generation_id"],
            e["secret_kind"],
        )
        if key in seen:
            raise ValueError(f"duplicate secret key: {key}")
        seen.add(key)
        ensure_sha256_hex(e["secret_entry_hash"])
        ensure_sha256_hex(e["secret_commitment"])
        out.append(e)
    return out


def registry_snapshot_hash(entry_hashes: Iterable[str]) -> str:
    """H('registry_snapshot', entry_hashes=<sorted deduped 64-hex list>)."""
    items = list(entry_hashes)
    for h in items:
        if not is_sha256_hex(h):
            raise ValueError(f"entry hash must be 64 hex: {h!r}")
    return H("registry_snapshot", entry_hashes=sorted(set(items)))


__all__ = [
    "SECRET_KIND_CANDIDATE",
    "SECRET_KIND_TRUTH",
    "SECRET_KINDS",
    "FAMILY_PHASES",
    "assert_family_phase_allowed",
    "assert_smoke_formal_separation",
    "seed_entry",
    "validate_seed_registry",
    "component_entry",
    "validate_component_registry",
    "secret_commitment_entry",
    "validate_secret_registry",
    "registry_snapshot_hash",
]
