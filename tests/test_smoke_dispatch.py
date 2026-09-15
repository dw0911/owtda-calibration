"""The smoke dispatch wrapper's wiring (step 8 of the freeze).

Re-audit 2026-09-15: attempt 9 dispatched ``SMOKE_NULL`` and ``SMOKE_ALT`` through
``execute_plan`` and the second phase died immediately, because
``audit/run_smoke_s03.py`` creates its execution root **exclusively** and both
subprocesses were left at the default id ``smoke-<generation>``.  The failure was
invisible: only ``error_class=TASK_EXCEPTION`` reached the disk.

These tests pin the command construction, which is what the earlier ``--stub``
validation did *not* cover: the stub never touches an execution root.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _wrapper():
    """Import ``scripts/run_smoke_via_execution.py`` as a module."""
    path = REPO / "scripts" / "run_smoke_via_execution.py"
    spec = importlib.util.spec_from_file_location("smoke_dispatch_wrapper", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestPhaseCommand:
    def test_each_phase_gets_its_own_execution_root_id(self, tmp_path):
        module = _wrapper()
        null = module.phase_command(
            phase="SMOKE_NULL", out=tmp_path, workers=8, replicates=None,
            dispatch_id="smoke-8w-a10", stub=False,
        )
        alt = module.phase_command(
            phase="SMOKE_ALT", out=tmp_path, workers=8, replicates=None,
            dispatch_id="smoke-8w-a10", stub=False,
        )
        null_id = null[null.index("--execution-id") + 1]
        alt_id = alt[alt.index("--execution-id") + 1]
        assert null_id != alt_id
        assert "SMOKE_NULL" in null_id and "SMOKE_ALT" in alt_id
        assert null_id.startswith("smoke-8w-a10")

    def test_the_id_is_a_legal_windows_directory_name(self, tmp_path):
        module = _wrapper()
        for phase in ("SMOKE_NULL", "SMOKE_ALT"):
            command = module.phase_command(
                phase=phase, out=tmp_path, workers=8, replicates=None,
                dispatch_id="smoke-8w-a10", stub=False,
            )
            identity = command[command.index("--execution-id") + 1]
            assert not (set(identity) & set('<>:"/\\|?*'))

    def test_the_phase_and_root_reach_the_underlying_script(self, tmp_path):
        module = _wrapper()
        command = module.phase_command(
            phase="SMOKE_ALT", out=tmp_path, workers=8, replicates=None,
            dispatch_id="smoke-8w-a10", stub=False,
        )
        assert command[0] == sys.executable
        assert command[1].endswith("run_smoke_s03.py")
        assert command[command.index("--root") + 1] == str(tmp_path)
        assert command[command.index("--phase") + 1] == "SMOKE_ALT"
        assert command[command.index("--workers") + 1] == "8"
        assert "--resume" not in command

    def test_replicates_are_passed_through_only_when_asked(self, tmp_path):
        module = _wrapper()
        without = module.phase_command(
            phase="SMOKE_ALT", out=tmp_path, workers=8, replicates=None,
            dispatch_id="smoke-8w-a10", stub=False,
        )
        with_replicates = module.phase_command(
            phase="SMOKE_ALT", out=tmp_path, workers=8, replicates=2,
            dispatch_id="smoke-8w-a10", stub=False,
        )
        assert "--replicates" not in without
        assert with_replicates[with_replicates.index("--replicates") + 1] == "2"

    def test_the_stub_does_not_claim_an_execution_root(self, tmp_path):
        module = _wrapper()
        command = module.phase_command(
            phase="SMOKE_ALT", out=tmp_path, workers=8, replicates=None,
            dispatch_id="smoke-8w-a10", stub=True,
        )
        assert "-c" in command and "--execution-id" not in command
        assert str(tmp_path / "dispatch_SMOKE_ALT.json") in command
