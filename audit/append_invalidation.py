"""Append one invalidation event (plus its reason object) to the append-only chain.

Unlike ``build_governance_registries.py`` (which *creates* the chains), this tool
only appends: it writes ``governance/reasons/<change_id>.json``, then CAS-appends a
single event against the current tip of ``INVALIDATION_REGISTRY.jsonl``
(``chains.append_cas``), so an already-committed chain can never be rewritten.

Usage::

    python audit/append_invalidation.py --change-id INV_V11_FREEZE_TAG \
        --target "freeze tag v1.1-freeze-owtda-cal-r1" \
        --replacement "freeze tag v1.2-freeze-owtda-cal-r1" \
        --statement "..." --evidence governance/CHANGELOG.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import chains

GOV = REPO / "governance"
REGISTRY = GOV / "INVALIDATION_REGISTRY.jsonl"
REASONS = GOV / "reasons"
HASH_FIELD = "event_hash"


def main() -> int:
    parser = argparse.ArgumentParser(description="append one invalidation event")
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--replacement", required=True)
    parser.add_argument("--statement", required=True)
    parser.add_argument("--evidence", nargs="*", default=[])
    parser.add_argument("--extra", default=None, help="JSON object with extra fields")
    args = parser.parse_args()

    reason: dict[str, Any] = {
        "schema_version": 1,
        "kind": "governance_reason",
        "reason_code": args.change_id,
        "statement": args.statement,
        "evidence": list(args.evidence),
    }
    if args.extra:
        reason.update(json.loads(args.extra))
    REASONS.mkdir(parents=True, exist_ok=True)
    reason_path = REASONS / f"{args.change_id}.json"
    reason_text = json.dumps(reason, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    reason_path.write_bytes(reason_text.encode("utf-8"))
    reason_hash = hashlib.sha256(reason_text.encode("utf-8")).hexdigest()

    tip = chains.read_tip(str(REGISTRY), hash_field=HASH_FIELD)
    if tip is None:
        raise SystemExit(f"BLOCKED: {REGISTRY.name} has no events to append to")
    at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    event = {
        "schema_version": 1,
        "event_type": "INVALIDATION",
        "invalidation_id": f"INV-{at[:10]}-appended",
        "at_utc": at,
        "change_id": args.change_id,
        "target": args.target,
        "reason_object_hash": reason_hash,
        "replacement": args.replacement,
        # F-R1-4: the chain's own linkage field must be written too, otherwise
        # verify_chain (which enforces prev_event_hash == previous tip) breaks.
        "prev_event_hash": tip,
    }
    new_tip = chains.append_cas(
        str(REGISTRY), event, expected_tip=tip, hash_field=HASH_FIELD
    )
    print(json.dumps(
        {
            "change_id": args.change_id,
            "reason_file": str(reason_path.relative_to(REPO)).replace("\\", "/"),
            "reason_object_hash": reason_hash,
            "previous_tip": tip,
            "new_tip": new_tip,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
