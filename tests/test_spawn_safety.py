"""Dispatch entry points must be spawn-safe on Windows.

The work-unit channel uses ``ProcessPoolExecutor``; on Windows the children are
started with ``spawn``, which re-imports the parent's ``__main__`` module.  An entry
script without an ``if __name__ == "__main__"`` guard is therefore re-executed inside
every child -- observed for real on 2026-09-16, when an unguarded check script died
with ``WORKER_EXIT x4`` and the phase correctly refused to seal.

The same constraint applied to the historical ``ordered_map`` path; this test pins it
so a new entry point cannot silently reintroduce the failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

ENTRY_POINTS = (
    "audit/run_smoke_s03.py",
    "audit/run_lifecycle_fixture.py",
    "audit/collect_verification.py",
    "scripts/run_final_sequence.py",
    "scripts/run_formal.py",
    "scripts/run_smoke_via_execution.py",
    "scripts/export_release_evidence.py",
    "scripts/promote_smoke_evidence.py",
)

GUARD = 'if __name__ == "__main__"'


@pytest.mark.parametrize("relative", ENTRY_POINTS)
def test_entry_point_is_spawn_safe(relative: str) -> None:
    path = REPO / relative
    if not path.is_file():
        pytest.skip(f"{relative} is not present in this checkout")
    text = path.read_text(encoding="utf-8")
    # the guard may be written with or without spaces and with either quote style;
    # normalise both so a formatting variant is not reported as a missing guard
    normalized = text.replace(" ", "").replace("'", '"')
    assert 'if__name__=="__main__"' in normalized, (
        f"{relative} may be re-executed inside every spawned work-unit child; "
        f"add an {GUARD!r} guard around its dispatch code"
    )


def test_the_dispatch_channel_really_spawns_children() -> None:
    """A guard only matters if children are spawned -- confirm the channel does."""
    import subprocess
    import sys

    program = (
        "import os, sys; sys.path.insert(0, 'src');\n"
        "from owtda_cal.workunit import run_units;\n"
        # ``str`` is a builtin, hence picklable: a function defined inside ``-c``
        # lives in ``__main__`` and cannot be unpickled in a spawned child.
        "result = run_units([1, 2], func=str, workers=2);\n"
        "print(result.is_complete(), '|', result.parts, '|', os.getpid())\n"
    )
    done = subprocess.run([sys.executable, "-c", program], cwd=str(REPO),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    assert done.returncode == 0, done.stderr[-500:]
    complete, parts, _parent = (field.strip() for field in done.stdout.split("|"))
    assert complete == "True"
    assert parts == "['1', '2']"
