"""Collect the verifiable Git freeze identity (audit P0-1).

Writes ``<root>/revision/`` exactly as the audit prescribed, **outside the repo**
so that producing the cleanliness proof cannot itself dirty the worktree:

    OWTDA-CAL-R1.bundle, git_bundle_verify.txt, git_fsck_full.txt,
    git_rev_parse_HEAD.txt, git_show_ref_tags.txt, git_log_graph.txt,
    git_status_porcelain_v1.txt, git_stash_list.txt,
    identity_check_<UTC>.json, source_manifest.json, source_tree_hash.txt

Acceptance (exit non-zero otherwise): ``git_status_porcelain_v1.txt`` and
``git_stash_list.txt`` are zero bytes, the bundle verifies standalone,
``identity_check.all_pass`` is true, the source manifest recomputes from the
frozen commit, and the original freeze tag has not moved.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from owtda_cal import freeze

BUNDLE = "OWTDA-CAL-R1.bundle"
FREEZE_TAG = "v1.0-freeze-owtda-cal-r1"
FROZEN_TAG_REVISION = "e16222f"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, check=False
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="collect git freeze identity evidence")
    parser.add_argument("--root", required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    root = Path(args.root).expanduser() / "revision"
    root.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {}

    bundle = root / BUNDLE
    create = _git("bundle", "create", str(bundle), "--all")
    results["bundle_created"] = create.returncode == 0

    verify = _git("bundle", "verify", str(bundle))
    (root / "git_bundle_verify.txt").write_bytes(verify.stdout + verify.stderr)
    results["bundle_verify_ok"] = verify.returncode == 0
    results["bundle_bytes"] = bundle.stat().st_size if bundle.exists() else 0

    fsck = _git("fsck", "--full", "--strict")
    (root / "git_fsck_full.txt").write_bytes(fsck.stdout + fsck.stderr)
    results["fsck_clean"] = fsck.returncode == 0 and b"error" not in fsck.stdout.lower()

    head = _git("rev-parse", "HEAD").stdout
    (root / "git_rev_parse_HEAD.txt").write_bytes(head)
    results["head"] = head.decode().strip()

    (root / "git_show_ref_tags.txt").write_bytes(_git("show-ref", "--tags").stdout)
    (root / "git_log_graph.txt").write_bytes(
        _git("log", "--graph", "--oneline", "--decorate", "-n", "80").stdout
    )

    status = _git("status", "--porcelain=v1").stdout
    (root / "git_status_porcelain_v1.txt").write_bytes(status)
    stash = _git("stash", "list").stdout
    (root / "git_stash_list.txt").write_bytes(stash)
    results["status_bytes"] = len(status)
    results["stash_bytes"] = len(stash)
    results["worktree_clean"] = len(status) == 0
    results["stash_empty"] = len(stash) == 0

    tag_rev = _git("rev-list", "-n", "1", FREEZE_TAG).stdout.decode().strip()
    results["freeze_tag"] = FREEZE_TAG
    results["freeze_tag_revision"] = tag_rev
    results["freeze_tag_unmoved"] = tag_rev.startswith(FROZEN_TAG_REVISION)

    identity = subprocess.run(
        [args.python, "audit/validate_identity.py", "--out-dir", str(root)],
        cwd=str(REPO), capture_output=True, text=True, check=False,
    )
    results["identity_check_exit"] = identity.returncode
    checks = sorted(root.glob("identity_check_*.json"))
    identity_payload = (
        json.loads(checks[-1].read_text(encoding="utf-8")) if checks else {}
    )
    results["identity_check_file"] = checks[-1].name if checks else None
    results["identity_all_pass"] = bool(identity_payload.get("all_pass"))

    manifest = json.loads(
        (REPO / "governance/FREEZE_MANIFEST.json").read_text(encoding="utf-8")
    )
    entries = manifest["source_tree_manifest"]
    recomputed = freeze.source_tree_hash(entries)
    (root / "source_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "source_manifest",
                "recorded_source_tree_hash": manifest["source_tree_hash"],
                "recomputed_source_tree_hash": recomputed,
                "verified": recomputed == manifest["source_tree_hash"],
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "source_tree_hash.txt").write_text(
        manifest["source_tree_hash"] + "\n", encoding="utf-8"
    )
    results["source_tree_hash_verified"] = recomputed == manifest["source_tree_hash"]

    acceptance = {
        "status_and_stash_empty": results["worktree_clean"] and results["stash_empty"],
        "bundle_verifies": results["bundle_verify_ok"],
        "fsck_clean": results["fsck_clean"],
        "identity_check_all_pass": results["identity_all_pass"],
        "source_manifest_recomputed": results["source_tree_hash_verified"],
        "freeze_tag_unmoved": results["freeze_tag_unmoved"],
    }
    results["acceptance"] = acceptance
    results["all_pass"] = all(acceptance.values())
    results["collected_at_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (root / "REVISION_ACCEPTANCE.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for key, value in acceptance.items():
        print(f"[{'PASS' if value else 'FAIL'}] {key}")
    print(f"head={results['head']} all_pass={results['all_pass']}")
    return 0 if results["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
