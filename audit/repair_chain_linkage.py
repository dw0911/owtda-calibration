"""Repair missing/mismatched ``prev_event_hash`` linkage in an append-only chain.

F-R1-4: the first version of ``audit/append_invalidation.py`` appended events
*without* ``prev_event_hash``, so ``build_governance_registries.verify_chain``
(which enforces ``prev_event_hash == previous tip``) would raise on the next run.
The event content is otherwise intact; this tool rewrites **only** the events whose
linkage is wrong, recomputing their hash with the canonical serialiser, and prints
before/after hashes so the repair itself is auditable.  It is a no-op on a healthy
chain, and it never touches event content other than the linkage field.

Usage::

    python audit/repair_chain_linkage.py --registry governance/INVALIDATION_REGISTRY.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import chains
from owtda_cal.canonical import canonical_json_bytes


def repair(path: Path, *, hash_field: str = "event_hash") -> list[dict[str, Any]]:
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    changes: list[dict[str, Any]] = []
    stored: list[dict[str, Any]] = []
    tip: str | None = None
    for event in events:
        body = {k: v for k, v in event.items() if k != hash_field}
        if body.get("prev_event_hash") != tip:
            previous = body.get("prev_event_hash", "<absent>")
            body["prev_event_hash"] = tip
            new_hash = chains.event_hash(body)
            changes.append(
                {
                    "change_id": body.get("change_id"),
                    "old_hash": event[hash_field],
                    "old_prev_event_hash": previous,
                    "new_prev_event_hash": tip,
                    "new_hash": new_hash,
                }
            )
            body[hash_field] = new_hash
        else:
            # untouched events keep their stored hash byte-for-byte
            body[hash_field] = event[hash_field]
        tip = body[hash_field]
        stored.append(body)
    if changes:
        payload = b"".join(canonical_json_bytes(e) + b"\n" for e in stored)
        path.write_bytes(payload)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="repair chain linkage (F-R1-4)")
    parser.add_argument("--registry", required=True)
    args = parser.parse_args()
    path = Path(args.registry)
    if not path.is_absolute():
        path = REPO / path
    changes = repair(path)
    if not changes:
        print(f"{path.name}: linkage already correct (no change)")
        return 0
    for change in changes:
        print(
            f"{path.name}: repaired {change['change_id']} "
            f"{change['old_hash'][:12]} -> {change['new_hash'][:12]} "
            f"(prev {str(change['old_prev_event_hash'])[:12]} -> "
            f"{str(change['new_prev_event_hash'])[:12]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
