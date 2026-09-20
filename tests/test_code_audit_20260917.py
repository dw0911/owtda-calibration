"""Non-scientific regression probes: no official DGP, PH, or MC samples."""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
import threading
from concurrent.futures import Future
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audit"))
import numpy as np
import pytest
import resource_sampler as rs
from run_formal_phase import run_formal_phase_lifecycle

from owtda_cal import (
 cells,
 dgp,
 execution,
 executor,
 formal,
 planbuild,
 scope,
 workunit,
)

F={'project_id':'AUDIT-TEST','protocol_id':'AUDIT-ONLY','freeze_id':hashlib.sha256(b'code-audit-test-freeze').hexdigest(),'evidence_generation_id':'G01','component_generations':{'data_generation_id':'D01','method_generation_id':{'M0':'M01','M1':'M01'}}}
CS=[('NULL',c) for c in scope.h0_null_cells()]+[('ALT',c) for c in scope.h1_alt_cells()]

def identity_rows(phase,cell):
 ctx=formal.formal_context(F,phase)
 fam=cell.family if phase=='NULL' else dgp.DGP_FAMILY_H1
 dmh=formal._formal_data_model_hash(fam,cell.rho) if phase=='NULL' else dgp.data_model_config_hash(dgp.h1_data_model_spec(cell.scenario,cell.rho))
 mid=cells.master_replicate_id(project_id=F['project_id'],protocol_id=F['protocol_id'],freeze_id=F['freeze_id'],evidence_generation_id=F['evidence_generation_id'],phase=phase,DGP_family=fam,replicate_id=1)
 for feat in scope.FEATURE_IDS:
  a=formal.formal_cell_identity(ctx=ctx,cell=cell,family=fam,master_replicate_id=mid,data_model_config_hash=dmh,feature_id=feat)
  b=cells.base_series_id(master_replicate_id=mid,data_generation_id='D01',DGP_family=fam,rho=cell.rho,raw_length=cell.T,data_model_config_hash=dmh)
  du=cells.data_unit_id(base_series_id=b,physical_cell_id=a['physical_cell_id'],data_generation_id='D01')
  yield ctx,a,b,du,feat

@pytest.mark.parametrize('phase,cell',CS,ids=[f'{p}-{getattr(c,"family",getattr(c,"scenario",""))}-{c.rho}-s{c.stride}-T{c.T}' for p,c in CS])
def test_all_cells_bind_prefix_length(phase,cell):
 for _,a,b,du,_ in identity_rows(phase,cell):
  assert a['base_series_id']==b
  assert a['data_unit_id']==du

@pytest.mark.parametrize('phase',['NULL','ALT'])
def test_plan_and_adapter_joint_identity(phase,tmp_path):
 kwargs={k:F[k] for k in ['project_id','protocol_id','freeze_id','evidence_generation_id']}
 planbuild.build_phase_plan(out_dir=tmp_path,phase=phase,replicate_override=1,data_generation_id='D01',**kwargs)
 rows={r['logical_evaluation_key']:r for r in (json.loads(s) for s in (tmp_path/phase/'expected_evaluation_index.jsonl').read_text().splitlines())}
 found=0
 for p,c in CS:
  if p!=phase:continue
  for ctx,a,b,du,feat in identity_rows(p,c):
   for key,(mid,_) in formal.METHOD_BY_KEY.items():
    ae=formal.formal_evaluation_identity(ctx=ctx,data_unit_id=a['data_unit_id'],logical_data_key=a['logical_data_key'],feature_id=feat,feature_sufficient_id=a['feature_sufficient_id'],method_id=mid,method_config_hash_value=formal.METHOD_CONFIG_HASH_BY_KEY[key])
    er=rows[ae['logical_evaluation_key']]
    assert er['evaluation_id']==ae['evaluation_id']
    assert er['data_unit_id']==du
    assert er['feature_sufficient_id']==a['feature_sufficient_id']
    found+=1
 assert found==len(rows)

def test_full_scale_missing_generation_rejected(tmp_path,monkeypatch):
 monkeypatch.setattr(scope,'R0_H0',1) # pure small index probe; no data generated
 with pytest.raises(ValueError):
  planbuild.build_phase_plan(out_dir=tmp_path,phase='NULL',**{k:F[k] for k in ['project_id','protocol_id','freeze_id','evidence_generation_id']})

def test_full_scale_zero_freeze_rejected(tmp_path,monkeypatch):
 monkeypatch.setattr(scope,'R0_H0',1)
 with pytest.raises(ValueError):
  planbuild.build_phase_plan(out_dir=tmp_path,phase='NULL',data_generation_id='D01',project_id='p',protocol_id='q',freeze_id='0'*64,evidence_generation_id='G01')

@pytest.mark.parametrize('mode,flags',[('FORMAL_H0',{'g4_h0_certificate':True,'expected_indices_bound':True,'seed_registry_bound':True}),('FORMAL_H1',{'null_evidence_dependency':True,'independent_authorization':True})])
def test_boolean_evidence_never_authorizes_callback(mode,flags,tmp_path):
 called=[]
 def submit(unit,index):
  called.append(index);f=Future();f.set_result('AUDIT_DUMMY');return f
 result=execution.execute_plan({'identity_domain':'FORMAL','units':[{'unit_id':'AUDIT-DUMMY'}]},mode=mode,submit=submit,evidence_root=tmp_path,execution_id='TEST-BOOL',**flags)
 assert result['terminal_state']=='REFUSED'
 assert not called

@pytest.mark.parametrize('terminal,stop',[('FAILED',True),('INCOMPLETE',True),('COMPLETE',True),('FAILED',False),('INCOMPLETE',False)])
def test_workunit_completion_requires_successful_terminal(terminal,stop):
 r=workunit.WorkUnitResult(payloads=[{}],outcome={'completed':1,'failed':0,'cancelled':0,'terminal_state':terminal,'stop_latched':stop})
 assert not r.is_complete()

def test_workunit_valid_complete_preserved():
 r=workunit.WorkUnitResult(payloads=[{}],outcome={'completed':1,'failed':0,'cancelled':0,'terminal_state':'COMPLETE','stop_latched':False})
 assert r.is_complete()

@pytest.fixture
def counters(monkeypatch):
 G=2**30
 monkeypatch.setattr(rs,'performance_info',lambda:{'commit_total_bytes':8*G,'commit_limit_bytes':64*G,'physical_total_bytes':32*G,'physical_available_bytes':24*G})
 monkeypatch.setattr(rs,'_tree_rss_bytes',lambda:G)

@pytest.mark.parametrize('failure_site',['runner','persist'])
def test_exception_closes_transferred_monitor(tmp_path,counters,failure_site):
 holder={}
 def boom(**kw):raise OSError('TEST-FAILURE')
 def hook(m,r):raise OSError('TEST-PERSIST-FAILURE')
 runner=boom if failure_site=='runner' else lambda **k: object()
 try:
  with pytest.raises(OSError):
   rs.sample_run(runner,evidence_root=tmp_path,run_id='AUDIT-CLEANUP',keep_open=True,monitor_holder=holder,on_compute_done=hook if failure_site=='persist' else None)
  m=holder['monitor']
  assert m._closed
  assert not m._thread.is_alive()
  assert m.rows()[-1]['stage']=='teardown'
 finally:
  if holder.get('monitor') and not holder['monitor']._closed:holder['monitor'].stop()

def test_empty_wrapper_cannot_certify_full_lifecycle(tmp_path,counters):
 def empty(**kwargs):return formal.FormalResult('NULL',0,0,0,0,0,0,[])
 with pytest.raises(RuntimeError,match='FORMAL_PRODUCTION_PIPELINE_INCOMPLETE'):
  run_formal_phase_lifecycle(phase='NULL',manifest={},seed_registry={},workers=1,replicate_limit=1,root=tmp_path,run_id='AUDIT-EMPTY',runner=empty)
 assert not list(tmp_path.rglob('*'))

def test_concurrent_sample_seq_allocation_is_serialized(tmp_path,counters):
 m=rs.CapacityMonitor(run_id='AUDIT-CONCURRENCY',raw_path=tmp_path/'unused.jsonl')
 real_lock=m._lock;second=threading.Event();first=threading.Event();gate_lock=threading.Lock();n=[0]
 class Gate:
  def __enter__(self):
   with gate_lock:
    order=n[0];n[0]+=1
   if order==0:
    first.set();second.wait(.15)
   elif order==1:second.set()
   real_lock.acquire();return self
  def __exit__(self,*args):real_lock.release()
 m._lock=Gate();errors=[]
 def writer():
  try:m._write_sample(stage='compute')
  except Exception as e:errors.append(repr(e))  # noqa: BLE001 - collect any writer failure
 a=threading.Thread(target=writer);a.start();assert first.wait(1)
 b=threading.Thread(target=writer);b.start();a.join(2);b.join(2)
 m._lock=real_lock
 assert not a.is_alive() and not b.is_alive()
 assert not errors
 assert [r['seq'] for r in m.rows()]==[0,1]
 assert m.rows()[0]['monotonic_ns']<=m.rows()[1]['monotonic_ns']

class DummyMaster:
 def raw_prefix_1d(self,n):return np.zeros(n)
 def raw_prefix(self,n):return np.zeros((n,2))

@pytest.mark.parametrize('phase',['NULL','ALT'])
def test_scientific_errors_keep_identity_class_and_partial(phase,monkeypatch):
 ctx=formal.formal_context(F,phase)
 p={'rho':scope.RHO_LEVELS[0],'replicate':1,'feature_id':scope.FEATURE_IDS[0],'root_keys':{'data':'1'*64,'M0':'2'*64,'M1':'3'*64},'ctx':ctx}
 if phase=='NULL':p['family']=scope.H0_FAMILIES[0]
 else:p['scenario']=scope.SCENARIO_ALT_SHAPE
 monkeypatch.setattr(dgp,'generate_null_master',lambda **k:DummyMaster())
 monkeypatch.setattr(dgp,'generate_h1_master',lambda **k:DummyMaster())
 monkeypatch.setattr(formal,'feature_matrix_for_windows',lambda w,**k:np.zeros((len(w),2)))
 monkeypatch.setattr(formal,'calibrate_m0',lambda *a,**k:{'observed_statistic':0.,'exceed_count':999,'p_value':1.,'reject':False})
 def fail(*a,**kw):raise MemoryError('AUDIT-ONLY-ERROR')
 monkeypatch.setattr(formal,'calibrate_m1',fail)
 fn=formal.process_formal_master_feature if phase=='NULL' else formal.process_formal_alt_feature
 with pytest.raises(RuntimeError) as exc:fn(p)
 error=exc.value
 assert error.error_class=='RESOURCE_ALLOCATION_ERROR'
 assert len(error.partial_result['rows'])==1
 assert len(error.details['evaluation_id'])==64
 restored=pickle.loads(pickle.dumps(error))
 assert restored.details==error.details
 f=Future();f.set_exception(restored)
 out=executor.execute_units([{'id':'TEST'}],submit=lambda u,i:f,window_size=1)
 assert out['terminal_state']=='FAILED'
 assert out['records'][0]['payload']==error.partial_result
 assert out['records'][0]['error_class']=='RESOURCE_ALLOCATION_ERROR'
