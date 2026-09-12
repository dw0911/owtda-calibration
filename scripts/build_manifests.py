"""Build the three manifests for the joint-fix version (task pack §7, C1).

Produces, into ``<out>/manifests/``:

* ``SCIENTIFIC_MANIFEST.json``  -- the science and configuration files,
* ``EXECUTION_MANIFEST.json``   -- entries, their import closure, command,
  environment, interpreter and the executable policy hash,
* ``VALIDATION_MANIFEST.json``  -- test sources, collection identities, approved
  skips, JUnit result, exit code and output digests,
* ``MANIFEST_BUNDLE.json``      -- the three hashes plus the plan binding.

Usage::

    python scripts/build_manifests.py <out-dir-outside-the-repo> \
        [--junit FILE] [--collected FILE] [--plan PLAN_SUMMARY.json] \
        [--approved-skip IDENTITY ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal.manifests import build_manifest_bundle
from owtda_cal.resource_policy import load_policy, policy_sha256

#: The delivered entry points of this version.  Their import closure is what the
#: execution manifest records -- the audit's point was that a runner change must
#: not be able to hide behind a folder name.
ENTRIES = (
    "scripts/run_final_sequence.py",
    "scripts/run_formal.py",
    "scripts/verify_fault_points.py",
    "scripts/run_attack_regression.py",
    "audit/run_smoke_s03.py",
    "audit/run_lifecycle_fixture.py",
    "audit/collect_verification.py",
    "audit/validate_schemas.py",
)
CONFIGS = ("governance/RESOURCE_POLICY_EXECUTABLE.json", "governance/RESOURCE_POLICY_V2.json",
           "governance/FREEZE_MANIFEST.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="build the §7 manifests")
    parser.add_argument("out", help="output directory (outside the repo)")
    parser.add_argument("--junit", default=None)
    parser.add_argument("--collected", default=None)
    parser.add_argument("--plan", default=None)
    parser.add_argument("--approved-skip", action="append", default=[])
    args = parser.parse_args()

    load_policy()  # refuses an unbound or non-integer policy
    science = sorted(p for p in (REPO / "src" / "owtda_cal").glob("*.py"))
    tests = sorted(p for p in (REPO / "tests").glob("*.py"))
    junit = Path(args.junit).read_text(encoding="utf-8", errors="replace") \
        if args.junit and Path(args.junit).is_file() else None
    collected = json.loads(Path(args.collected).read_text(encoding="utf-8")) \
        if args.collected and Path(args.collected).is_file() else None

    bundle = build_manifest_bundle(
        root=REPO, out_dir=Path(args.out).expanduser() / "manifests",
        entries=[REPO / e for e in ENTRIES], command=sys.argv,
        policy_sha256=policy_sha256(),
        science_files=science, config_files=[REPO / c for c in CONFIGS],
        test_files=tests, roots=[REPO / "src", REPO / "audit", REPO / "scripts"],
        junit_xml=junit, collected_nodeids=collected,
        approved_skips=args.approved_skip,
        plan_summary_path=args.plan,
    )
    print(json.dumps({
        "bundle_hash": bundle["bundle_hash"],
        "scientific_files": len(bundle["scientific_manifest"]["files"]),
        "execution_closure": len(bundle["execution_manifest"]["files"]),
        "validation_files": len(bundle["validation_manifest"]["test_files"]),
        "unapproved_skips": bundle["validation_manifest"]["unapproved_skips"],
        "plan_bound": bundle["plan_binding"] is not None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
