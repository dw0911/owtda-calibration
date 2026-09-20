"""Additional R4 regression and integration tests. Synthetic engineering inputs only."""
from __future__ import annotations

import hashlib
import json
import sys
import threading
from concurrent.futures import Future
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'audit')]
import resource_sampler
import verify_release_contracts as release

from owtda_cal.executor import execute_units
from owtda_cal.formal_admission import check_g4_h0_certificate
from owtda_cal.manifests import execution_manifest, validation_manifest

G=2**30

@pytest.mark.parametrize('field',['command','environment','policy'])
def test_execution_manifest_binds_all_fields(tmp_path,field):
    entry=tmp_path/'entry.py';entry.write_text('x=1\n')
    kw={'entries': [entry],'command': ['python','entry.py'],'environment': {'OMP_NUM_THREADS':'1'},'policy_sha256': 'a'*64,'root': tmp_path}
    before=execution_manifest(**kw)
    if field=='command':kw['command']=['python','different.py']
    elif field=='environment':kw['environment']={'OMP_NUM_THREADS':'2'}
    else:kw['policy_sha256']='b'*64
    assert execution_manifest(**kw)['manifest_hash']!=before['manifest_hash']

@pytest.mark.parametrize('field',['exit_code','stdout','approved_skips','collected_nodeids'])
def test_validation_manifest_binds_evidence(tmp_path,field):
    test=tmp_path/'test_example.py';test.write_text('def test_example(): pass\n')
    kw={'test_files': [test],'root': tmp_path,'exit_code': 0}
    before=validation_manifest(**kw)
    kw.update({field:{'exit_code':1,'stdout':b'changed','approved_skips':['x::test_y'],'collected_nodeids':[{'classname':'x','name':'test_y'}]}[field]})
    assert validation_manifest(**kw)['manifest_hash']!=before['manifest_hash']


def test_missing_raw_resource_cannot_fall_back_to_summary(tmp_path):
    resource={'run_id':'TEST','capacity_sampling':{'incomplete':False,'samples':10,'commit_total_peak_bytes':G,'commit_limit_bytes':100*G,'physical_total_bytes':32*G,'physical_available_min_bytes':16*G},
              'peak_total_rss_bytes':G,'capacity_raw_path':str(tmp_path/'missing.jsonl'),
              'resource_allocation_failures':0,'evidence_bytes_written':1,'disk_free_before_bytes':100*G}
    decision=resource_sampler.resource_verdict(resource,unexplained_errors=0)
    assert decision['passed'] is False
    assert decision['status']=='INCOMPLETE'


def test_existing_capacity_stream_is_not_appended(tmp_path,monkeypatch):
    path=tmp_path/'raw.jsonl';path.write_bytes(b'old-evidence\n')
    monkeypatch.setattr(resource_sampler,'performance_info',lambda:{'commit_total_bytes': G,'commit_limit_bytes': 100*G,'physical_total_bytes': 32*G,'physical_available_bytes': 16*G})
    monkeypatch.setattr(resource_sampler,'_tree_rss_bytes',lambda:G)
    monitor=resource_sampler.CapacityMonitor(run_id='TEST',raw_path=path)
    try:
        with pytest.raises(FileExistsError):monitor.start()
    finally:
        if monitor._thread is not None:monitor.stop()
    assert path.read_bytes()==b'old-evidence\n'


def test_unsettled_future_is_not_reported_as_observed_worker_exit():
    class Monitor:stop_requested=threading.Event()
    monitor=Monitor()
    pending=Future();pending.set_running_or_notify_cancel()
    def submit(u,i):monitor.stop_requested.set();return pending
    outcome=execute_units([1],submit=submit,monitor=monitor,grace_seconds=0,poll_interval=0)
    assert outcome['terminal_state']=='INCOMPLETE'
    assert outcome['unsettled_indices']==[0]
    assert outcome['errors_by_class']['WORKER_EXIT']==0
    assert outcome['safe_to_seal'] is False
    pending.set_result(1)  # synthetic future cleanup; no process was started


def test_malformed_certificate_with_registry_is_attributable(tmp_path):
    cert=tmp_path/'certificate.json';cert.write_text('[]')
    registry=tmp_path/'seeds.json';registry.write_text('{}')
    out=check_g4_h0_certificate(certificate_path=cert,plan_summary={'formal_scale':True},seed_registry_path=registry)
    assert out['admitted'] is False
    assert 'CERTIFICATE_UNPARSEABLE' in out['codes']


def test_malformed_junit_is_a_reported_failure(tmp_path):
    (tmp_path/'collection_manifest.json').write_text('{"node_ids":["tests/test_x.py::test_x"],"collected_count":1}')
    (tmp_path/'validation_exit_codes.json').write_text('{"pytest":0}')
    (tmp_path/'pytest_full.xml').write_text('<broken')
    count,codes=release._test_evidence(tmp_path)
    assert count is None and 'JUNIT_UNPARSEABLE' in codes


def test_budget_missing_selected_storage_is_incomplete():
    from owtda_cal.budget import build_budget, derive_counts
    schema={k:1 for k in ('evaluation_row_bytes','feature_row_bytes','data_unit_bytes','index_entry_bytes','event_row_bytes','resource_row_bytes','manifest_bytes')}
    schema.update(store_full_feature_matrices=True,store_summaries=False,store_ph_diagrams=False,store_resampling_stats=False)
    profile={'compute_seconds_per_evaluation': 1,'serialize_seconds_per_evaluation': 1,'merge_seconds_per_phase': 1,'seal_seconds_per_phase': 1,'recovery_seconds': 1}
    out=build_budget(counts=derive_counts(),serialization_schema=schema,profile=profile,storage_policy={'copies':{'final':1},'coexisting_stages':['final']},volumes=[{'free_bytes':100*G}])
    assert out['status']=='INCOMPLETE'
    assert any('feature_matrix_bytes' in m for m in out['missing'])


def test_analysis_final_seal_binds_bytes_and_repeat_cannot_overwrite(tmp_path):
    from run_lifecycle_fixture import FixtureError, finalize_analysis
    row={'evaluation_id':'TEST-ONLY','feature_id':'moments','method_id':'M0'}
    (tmp_path/'ledger.jsonl').write_text(json.dumps(row)+'\n')
    kw={'out_dir': tmp_path,'ledger_file': 'ledger.jsonl','phase_seal_hashes': ['a'*64],'analysis_seal_hash': 'b'*64,'source_run_seal_hashes': ['c'*64]}
    out=finalize_analysis(**kw)
    seal=json.loads((tmp_path/out['analysis_result_seal']).read_text())
    assert seal['output_sha256']==hashlib.sha256((tmp_path/'analysis_output.json').read_bytes()).hexdigest()
    before=(tmp_path/'analysis_input.json').read_bytes()
    with pytest.raises(FixtureError):finalize_analysis(**kw)
    assert before==(tmp_path/'analysis_input.json').read_bytes()


def test_portable_export_preserves_bytes_and_refuses_overwrite(tmp_path):
    from export_release_evidence import export_parts
    source=tmp_path/'source';source.mkdir();(source/'evidence.bin').write_bytes(bytes(range(256)))
    out=tmp_path/'delivery';manifest=export_parts({'run':source},out)
    assert (out/'run/evidence.bin').read_bytes()==(source/'evidence.bin').read_bytes()
    assert manifest['admission_issued'] is False
    with pytest.raises(FileExistsError):export_parts({'run':source},out)


def test_portable_export_refuses_output_inside_source(tmp_path):
    from export_release_evidence import export_parts
    with pytest.raises(ValueError):export_parts({'run':tmp_path},tmp_path/'child')


def test_sequence_refuses_existing_plan_without_deleting_evidence(tmp_path):
    import run_final_sequence as sequence
    p=tmp_path/'plan';p.mkdir();(p/'sentinel').write_bytes(b'original-plan')
    with pytest.raises(FileExistsError):
        sequence._plan_step(tmp_path)
    assert (p/'sentinel').read_bytes()==b'original-plan'


def test_formal_cli_never_confuses_bound_template_with_dispatch(tmp_path,monkeypatch):
    import run_formal
    monkeypatch.setattr(run_formal,'load_plan_summary',lambda p:{'formal_scale':True,'totals':{}})
    monkeypatch.setattr(run_formal,'check_g4_h0_certificate',lambda **kw:{'admitted':True,'status':'ADMITTED_PENDING_DISPATCH','codes':[]})
    # Re-audit 2026-09-16 (Block A): a bound template (certificate passes) must
    # still not dispatch when the real adapter is absent -- the two are distinct.
    monkeypatch.setattr(run_formal,'_formal_adapter_available',lambda: False)
    out=tmp_path/'out'
    monkeypatch.setattr(sys,'argv',['run_formal.py','--plan','unused','--out',str(out)])
    assert run_formal.main()==1
    decision=json.loads((out/'FORMAL_ADMISSION.json').read_text())
    assert decision['certificate_bindings_verified'] is True
    assert decision['admitted'] is False
    assert decision['status']=='FORMAL_RUNNER_NOT_IMPLEMENTED'
