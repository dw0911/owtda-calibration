"""Independent R4 regressions. No formal Monte Carlo or PH computation."""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import Future
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'audit')]
import verify_release_contracts as release

from owtda_cal.execution import ExecutionError, create_execution_root, execute_plan
from owtda_cal.executor import execute_units
from owtda_cal.formal_admission import check_g4_h0_certificate
from owtda_cal.resource_policy import (
    evaluate_capacity,
    load_policy,
    policy_sha256,
    preflight_capacity,
)

G=2**30

def _row(i=0):
    return {'schema_version': 1,'run_id': 'AUDIT-TEST','policy_sha256': policy_sha256(),'seq': i,
                'monotonic_ns': i*10**9,'ok': True,'error': None,'stage': 'start' if i==0 else 'teardown',
                'commit_total_bytes': 10*G,'commit_limit_bytes': 100*G,
                'physical_total_bytes': 32*G,'physical_available_bytes': 16*G,'rss_tree_bytes': G}

@pytest.mark.parametrize('field,value',[
    ('seq',99),('monotonic_ns',-1),('run_id','OTHER'),('policy_sha256','0'*64),
    ('physical_total_bytes',0),('physical_available_bytes',999*G),('seq',True),
    ('run_id',None),('error','FAILED_READ'),
])
def test_invalid_capacity_stream_never_passes(field,value):
    rows=[_row(),_row(1)];rows[1][field]=value
    assert evaluate_capacity(rows,policy=load_policy())['verdict']!='PASS'

def test_duplicate_capacity_sample_never_passes():
    assert evaluate_capacity([_row(),_row()],policy=load_policy())['verdict']!='PASS'

def test_valid_paired_capacity_stream_passes():
    assert evaluate_capacity([_row(),_row(1)],policy=load_policy())['verdict']=='PASS'

def test_counter_pair_not_mixed():
    rows=[_row(),_row(1)]
    rows[0].update(commit_total_bytes=90*G,commit_limit_bytes=100*G)
    rows[1].update(commit_total_bytes=90*G,commit_limit_bytes=200*G)
    assert evaluate_capacity(rows,policy=load_policy())['verdict']=='FAIL'

@pytest.mark.parametrize('variant',['missing_physical','zero_limit','missing_volumes','wrong_workers'])
def test_incomplete_preflight_never_admits(variant):
    kw={'baseline_commit_bytes': G,'delta_commit_bytes': G,'commit_limit_bytes': 100*G,
            'physical_available_bytes': 16*G,'physical_total_bytes': 32*G,
            'volumes': [{'name':'TEST','free_bytes':100*G,'required_bytes':G}],
            'workers': load_policy()['limits']['workers'],'policy': load_policy()}
    if variant=='missing_physical':kw.pop('physical_available_bytes')
    if variant=='zero_limit':kw.update(baseline_commit_bytes=0,delta_commit_bytes=0,commit_limit_bytes=0)
    if variant=='missing_volumes':kw.pop('volumes')
    if variant=='wrong_workers':kw['workers']=999
    assert not preflight_capacity(**kw)['passed']

def test_worker_failure_stops_new_dispatch():
    submitted=[]
    def submit(u,i):
        submitted.append(i);f=Future()
        if i==0:f.set_exception(MemoryError('injected'))
        else:f.set_result(i)
        return f
    result=execute_units([0,1,2],submit=submit,window_size=1)
    assert submitted==[0]
    assert result['terminal_state']=='FAILED'
    assert len(result['records'])==3

def test_stop_checked_for_each_submit_and_after_last_result():
    class Monitor:stop_requested=threading.Event()
    m=Monitor();submitted=[]
    def submit(u,i):
        submitted.append(i);m.stop_requested.set();f=Future();f.set_result(i);return f
    result=execute_units([0,1,2],submit=submit,monitor=m,window_size=3)
    assert submitted==[0]
    assert result['stop_latched'] is True
    assert result['terminal_state']!='COMPLETE'

def test_submit_exception_is_preserved_in_result():
    def submit(u,i):raise MemoryError('submit failed')
    result=execute_units([0,1],submit=submit,window_size=1)
    assert result['terminal_state']=='FAILED'
    assert result['errors_by_class']['RESOURCE_ALLOCATION_ERROR']==1
    assert len(result['records'])==2

def _submit(u,i):
    f=Future();f.set_result(i);return f

def test_resume_does_not_overwrite_completed_plan(tmp_path):
    plan={'identity_domain':'TEST','units':[{'unit_id':'a'}]}
    execute_plan(plan,mode='TEST',submit=_submit,evidence_root=tmp_path,execution_id='audit',test_seed_domain=True,test_id_domain=True)
    path=tmp_path/'executions/audit/plan/plan.json';before=path.read_bytes()
    with pytest.raises(ExecutionError):
        execute_plan({'identity_domain':'TEST','units':[{'unit_id':'b'}]},mode='TEST',submit=_submit,evidence_root=tmp_path,execution_id='audit',resume=True,test_seed_domain=True,test_id_domain=True)
    assert path.read_bytes()==before

@pytest.mark.parametrize('execution_id',['../escape','x/y','x\\y','..'])
def test_execution_root_is_contained(tmp_path,execution_id):
    with pytest.raises(ExecutionError):create_execution_root(tmp_path,execution_id)

def test_formal_boolean_flags_cannot_dispatch(tmp_path, monkeypatch):
    # Re-audit 2026-09-16 (Block A): the formal adapter now exists, so the
    # unconditional refusal is gone -- but boolean flags alone must still never
    # dispatch when the adapter is absent.  The probe is pinned here.
    import owtda_cal.execution as execution_module
    monkeypatch.setattr(execution_module, '_formal_adapter_available', lambda: False)
    result=execute_plan({'identity_domain':'FORMAL','units':[{'unit_id':'AUDIT-ONLY'}]},mode='FORMAL_H0',submit=_submit,evidence_root=tmp_path,execution_id='formal-probe',g4_h0_certificate=True,expected_indices_bound=True,seed_registry_bound=True)
    assert result['terminal_state']=='REFUSED'

def test_minimal_unbound_certificate_refused(tmp_path):
    p=tmp_path/'cert.json';p.write_text(json.dumps({'kind':'g4_h0_certificate','phase':'H0','status':'FROZEN'}))
    decision=check_g4_h0_certificate(certificate_path=p,plan_summary={'formal_scale':True,'phases':{'NULL':{'index_hashes':{'evaluation':'a'*64}}}})
    assert not decision['admitted']

def test_nonobject_certificate_is_a_refusal_not_crash(tmp_path):
    p=tmp_path/'cert.json';p.write_text('[]')
    decision=check_g4_h0_certificate(certificate_path=p,plan_summary={'formal_scale':True,'phases':{'NULL':{'index_hashes':{'evaluation':'a'*64}}}})
    assert not decision['admitted']

def test_c1_empty_manifest_files_cannot_pass(tmp_path):
    for n in ['SCIENTIFIC_MANIFEST','EXECUTION_MANIFEST','VALIDATION_MANIFEST']:(tmp_path/(n+'.json')).write_text('{}')
    (tmp_path/'MANIFEST_BUNDLE.json').write_text('{"plan_binding":{"formal_scale":true,"totals":{"evaluations":331200}}}')
    assert release.check_c1(tmp_path,{'formal_scale':True})['status']!='PASS'

def test_c3_summary_without_fault_records_cannot_pass(tmp_path):
    (tmp_path/'SUMMARY.json').write_text('{"checks":10,"failed":[],"platform":"win32"}')
    assert release.check_c3(tmp_path)['status']!='PASS'

def test_c4_summary_without_actual_payload_cannot_pass(tmp_path):
    (tmp_path/'LIFECYCLE_FIXTURE.json').write_text(json.dumps({'set_equality':{'identical':True,'committed':list('abcdefgh')},'verdict':{'ledger_is_the_committed_payload':True,'analysis_reads_the_actual_ledger':True}}))
    assert release.check_c4(tmp_path)['status']!='PASS'

def test_c5_summary_without_run_measurement_cannot_pass(tmp_path):
    (tmp_path/'preflight').mkdir();(tmp_path/'budget').mkdir()
    (tmp_path/'preflight/preflight.json').write_text('{"passed":true}')
    (tmp_path/'budget/budget.json').write_text('{"status":"APPROVED_ESTIMATE","bound_plan":{"formal_scale":true}}')
    assert release.check_c5(tmp_path,{'formal_scale':True})['status']!='PASS'

def test_junit_identity_substitution_is_detected(tmp_path):
    (tmp_path/'collection_manifest.json').write_text(json.dumps({'collected_count':1,'node_ids':['tests/test_a.py::test_a']}))
    (tmp_path/'validation_exit_codes.json').write_text('{"pytest_full":0}')
    (tmp_path/'pytest_full.xml').write_text('<testsuite><testcase classname="tests.test_a" name="unrelated_test"/></testsuite>')
    _count,codes=release._test_evidence(tmp_path)
    assert codes
