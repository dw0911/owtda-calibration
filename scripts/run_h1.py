#!/usr/bin/env python3
"""Level 3 entry point for the H1/ALT phase.

Registered H1 covers both alternative constructions (shape change and mean shift) in one
frozen ALT plan; this entry therefore only fixes the phase and reuses ``scripts/run_h0.py``.

  python scripts/run_h1.py --plan <dir> --certificate <json> --out <dir> [--dry-run]
"""

from __future__ import annotations

import sys

from run_h0 import main

if __name__ == "__main__":
    sys.exit(main(default_phase="ALT"))
