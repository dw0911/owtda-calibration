"""The FORMAL_H0 admission gate (task pack §4.1, §9 step 10).

``execute_plan`` admits FORMAL_H0 only when the certificate, the expected indices
and the seed registry are all bound.  This module is the pure decision behind
that: it never dispatches, never computes, and never turns a missing binding into
a warning.

Refusal codes are attributable so a failure can be diagnosed without reading the
prose:

``CERTIFICATE_MISSING`` / ``CERTIFICATE_UNPARSEABLE`` / ``CERTIFICATE_WRONG_KIND``
``PLAN_NOT_FORMAL_SCALE`` / ``PLAN_UNBOUND_EVALUATION_INDEX``
``CERTIFICATE_PLAN_BINDING_MISMATCH`` (the certificate names a different plan)
``CERTIFICATE_PHASE_MISMATCH`` / ``CERTIFICATE_NOT_FROZEN``
``SEED_REGISTRY_MISSING`` / ``SEED_REGISTRY_HASH_MISMATCH``
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CERTIFICATE_KIND = "g4_h0_certificate"
CERTIFICATE_FILE = "G4_H0_CERTIFICATE.json"
ADMITTED = "ADMITTED_PENDING_DISPATCH"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_g4_h0_certificate(
    *,
    certificate_path: str | Path,
    plan_summary: dict[str, Any],
    seed_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Decide whether FORMAL_H0 may start; always explains itself."""
    reasons: list[dict[str, str]] = []

    def refuse(code: str, where: str, detail: str) -> None:
        reasons.append({"code": code, "where": where, "detail": detail})

    if not plan_summary.get("formal_scale"):
        refuse("PLAN_NOT_FORMAL_SCALE", "plan", (
            "the plan was built with a replicate override; a reduced plan can never "
            "enter formal admission"))

    plan_hashes = {
        phase: report["index_hashes"]["evaluation"]
        for phase, report in (plan_summary.get("phases") or {}).items()
    }
    if not plan_hashes:
        refuse("PLAN_UNBOUND_EVALUATION_INDEX", "plan",
               "the plan summary carries no evaluation index hash")

    certificate_file = Path(certificate_path)
    certificate: dict[str, Any] = {}
    if not certificate_file.is_file():
        refuse("CERTIFICATE_MISSING", str(certificate_file), "absent")
    else:
        try:
            certificate = json.loads(certificate_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - a broken certificate is a finding
            refuse("CERTIFICATE_UNPARSEABLE", str(certificate_file), str(exc))
        else:
            if certificate.get("kind") != CERTIFICATE_KIND:
                refuse("CERTIFICATE_WRONG_KIND", str(certificate_file),
                       f"kind={certificate.get('kind')!r}")
            if str(certificate.get("phase", "")).upper() not in ("H0", "NULL"):
                refuse("CERTIFICATE_PHASE_MISMATCH", str(certificate_file),
                       f"phase={certificate.get('phase')!r}")
            if certificate.get("status") != "FROZEN":
                refuse("CERTIFICATE_NOT_FROZEN", str(certificate_file),
                       f"status={certificate.get('status')!r}")
            declared = certificate.get("evaluation_index_hashes") or {}
            if declared and plan_hashes and declared != plan_hashes:
                refuse("CERTIFICATE_PLAN_BINDING_MISMATCH", str(certificate_file),
                       f"certificate {sorted(declared)} != plan {sorted(plan_hashes)}")

    registry_path = Path(seed_registry_path) if seed_registry_path else None
    if registry_path is not None:
        if not registry_path.is_file():
            refuse("SEED_REGISTRY_MISSING", str(registry_path), "absent")
        else:
            actual = _sha256_file(registry_path)
            declared = certificate.get("seed_registry_sha256")
            if not declared:
                refuse("SEED_REGISTRY_HASH_MISMATCH", str(registry_path),
                       "the certificate declares no seed_registry_sha256")
            elif declared != actual:
                refuse("SEED_REGISTRY_HASH_MISMATCH", str(registry_path),
                       f"{str(declared)[:16]}... != {actual[:16]}...")

    return {
        "status": ADMITTED if not reasons else "REFUSED",
        "admitted": not reasons,
        "reasons": reasons,
        "codes": [r["code"] for r in reasons],
        "plan_evaluation_index_hashes": plan_hashes,
        "certificate": str(certificate_file),
        "seed_registry": str(registry_path) if registry_path else None,
        "note": (
            "admission is not a run: dispatch happens through execute_plan once the "
            "formal unit path is wired"
        ),
    }


def load_plan_summary(plan_dir: str | Path) -> dict[str, Any]:
    path = Path(plan_dir) / "PLAN_SUMMARY.json"
    if not path.is_file():
        raise FileNotFoundError(f"no plan summary at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "ADMITTED",
    "CERTIFICATE_FILE",
    "CERTIFICATE_KIND",
    "check_g4_h0_certificate",
    "load_plan_summary",
]
