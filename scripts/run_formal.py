"""§9 step 10 entry: the FORMAL_H0 admission gate (no computation happens here).

This script exists so that "start the formal phase" cannot be a side effect of a
loop somewhere: it validates the certificate against the frozen plan and the seed
registry, records the decision, and stops.  Dispatch is the shared
``execute_plan`` path, which admits FORMAL_H0 only with the same three bindings --
and that path is not wired for formal units yet, so this script never claims a run
took place.

Usage::

    python scripts/run_formal.py --plan <PLAN_DIR> --certificate <JSON> \
        [--seed-registry <JSON>] --out <EVIDENCE_DIR>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal.formal_admission import (
    CERTIFICATE_FILE,
    check_g4_h0_certificate,
    load_plan_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="FORMAL_H0 admission gate (§9 step 10)")
    parser.add_argument("--plan", required=True, help="plan directory (step 5 output)")
    parser.add_argument("--certificate", default=None,
                        help=f"G4_H0 certificate JSON (default: <plan>/../{CERTIFICATE_FILE})")
    parser.add_argument("--seed-registry", default=None, help="seed registry JSON")
    parser.add_argument("--out", required=True, help="evidence directory (outside the repo)")
    args = parser.parse_args()

    plan = load_plan_summary(args.plan)
    certificate = args.certificate or str(Path(args.plan).parent / CERTIFICATE_FILE)
    decision = check_g4_h0_certificate(
        certificate_path=certificate, plan_summary=plan,
        seed_registry_path=args.seed_registry,
    )

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    (out / "FORMAL_ADMISSION.json").write_text(
        json.dumps({"requested_phase": "H0", **decision}, ensure_ascii=False, indent=2,
                   sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": decision["status"], "codes": decision["codes"],
                      "plan_totals": plan.get("totals")}, ensure_ascii=False))
    return 0 if decision["admitted"] else 1


if __name__ == "__main__":
    sys.exit(main())
