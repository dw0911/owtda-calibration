"""F-R1-1: the amendment/invalidation chains must be **append-only**.

The builder used to truncate and re-render both chains from its internal list, so
an event appended by another tool was silently dropped — ``INV_V12_SOURCE_ANCHOR``
was lost that way.  These tests pin the replacement behaviour: existing events are
preserved byte-for-byte (their hashes must not change), new events are appended,
and a conflicting re-render fails closed instead of rewriting history.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "audit"))

import build_governance_registries as bgr

from owtda_cal import chains


def _events(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _external_append(path: Path, change_id: str) -> str:
    """Mimic audit/append_invalidation.py: an event the builder does not know."""
    tip = chains.read_tip(str(path), hash_field="event_hash")
    return chains.append_cas(
        str(path),
        {"schema_version": 1, "change_id": change_id, "at_utc": "2026-01-01T00:00:00Z"},
        expected_tip=tip,
        hash_field="event_hash",
    )


class TestAppendOnlyChain:
    def test_external_event_survives_a_rebuild(self, tmp_path: Path):
        path = tmp_path / "chain.jsonl"
        bgr._write_chain(path, [{"schema_version": 1, "change_id": "A"}])
        external = _external_append(path, "EXT")

        tips = bgr._write_chain(
            path, [{"schema_version": 1, "change_id": "A"}, {"schema_version": 1, "change_id": "B"}]
        )

        events = _events(path)
        assert [e["change_id"] for e in events] == ["A", "EXT", "B"]
        assert events[1]["event_hash"] == external
        assert len(tips) == 3

    def test_existing_events_keep_their_bytes(self, tmp_path: Path):
        path = tmp_path / "chain.jsonl"
        bgr._write_chain(path, [{"schema_version": 1, "change_id": "A", "at_utc": "t1"}])
        before = _events(path)[0]
        # A re-render carrying a different envelope timestamp must not touch it.
        bgr._write_chain(
            path, [{"schema_version": 1, "change_id": "A", "at_utc": "t2-different"}]
        )
        after = _events(path)[0]
        assert after == before

    def test_rebuild_is_idempotent(self, tmp_path: Path):
        path = tmp_path / "chain.jsonl"
        events = [{"schema_version": 1, "change_id": "A"}, {"schema_version": 1, "change_id": "B"}]
        first = bgr._write_chain(path, events)
        second = bgr._write_chain(path, events)
        assert first == second
        assert len(_events(path)) == 2

    def test_conflicting_content_fails_closed(self, tmp_path: Path):
        path = tmp_path / "chain.jsonl"
        bgr._write_chain(path, [{"schema_version": 1, "change_id": "A", "scope": "x"}])
        with pytest.raises(SystemExit) as excinfo:
            bgr._write_chain(
                path, [{"schema_version": 1, "change_id": "A", "scope": "y"}]
            )
        assert "append-only" in str(excinfo.value)
        assert len(_events(path)) == 1

    def test_envelope_fields_do_not_count_as_conflicts(self, tmp_path: Path):
        path = tmp_path / "chain.jsonl"
        bgr._write_chain(path, [{"schema_version": 1, "change_id": "A", "amendment_id": "AM-1"}])
        bgr._write_chain(path, [{"schema_version": 1, "change_id": "A", "amendment_id": "AM-2"}])
        assert len(_events(path)) == 1


class TestDeliveredChains:
    def test_committed_chains_are_hash_linked(self):
        for name in ("AMENDMENT_REGISTRY.jsonl", "INVALIDATION_REGISTRY.jsonl"):
            events = _events(REPO / "governance" / name)
            assert events, name
            tip = None
            for event in events:
                stored = event.pop("event_hash")
                assert event["prev_event_hash"] == tip, name
                assert chains.event_hash(event) == stored, name
                tip = stored

    def test_known_change_ids_are_present(self):
        amendments = {
            e["change_id"] for e in _events(REPO / "governance/AMENDMENT_REGISTRY.jsonl")
        }
        assert {"AM_PARALLELISM_DECOUPLING", "AM_TOOLING_SCOPE"} <= amendments
        invalidations = {
            e["change_id"] for e in _events(REPO / "governance/INVALIDATION_REGISTRY.jsonl")
        }
        # the event that the truncating writer dropped before the fix
        assert "INV_V12_SOURCE_ANCHOR" in invalidations
