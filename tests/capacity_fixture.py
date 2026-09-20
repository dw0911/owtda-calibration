"""Synthetic RAW capacity evidence for unit tests; never used by a real run."""
import hashlib
import json
import uuid
from pathlib import Path

from owtda_cal.resource_policy import policy_sha256


def bind_test_raw(record: dict, directory: Path) -> dict:
    block = record.get('capacity_sampling')
    if not block:
        return record
    run_id = 'TEST-' + uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (run_id + '.jsonl')
    gap = block.get('max_gap_milliseconds', 1000) * 1000000
    rows = [{'schema_version': 1, 'run_id': run_id, 'policy_sha256': policy_sha256(), 'seq': i,
                 'monotonic_ns': i*gap, 'ok': True, 'error': None, 'stage': 'start' if i==0 else 'teardown',
                 'commit_total_bytes': block['commit_total_peak_bytes'], 'commit_limit_bytes': block['commit_limit_bytes'],
                 'physical_total_bytes': block['physical_total_bytes'], 'physical_available_bytes': block['physical_available_min_bytes'],
                 'rss_tree_bytes': record['peak_total_rss_bytes']} for i in (0,1)]
    blob=b''.join((json.dumps(row,sort_keys=True)+'\n').encode() for row in rows)
    path.write_bytes(blob)
    record.update(run_id=run_id, capacity_raw_path=str(path), capacity_raw_relative_path=path.name,
                  capacity_raw_sha256=hashlib.sha256(blob).hexdigest(),capacity_policy_sha256=policy_sha256(),
                  capacity_coverage_scope='FULL_SCIENTIFIC_LIFECYCLE',protected_start_ns=0,protected_end_ns=gap)
    block['samples']=2
    return record
