#!/usr/bin/env python3
"""Read-only review of the 20260918 summary delivery. No Monte Carlo or PH.
The reported raw-ledger checks remain local evidence, not raw replay here.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, zipfile
from pathlib import Path
FEATURES=('BPI_FIXED20_H01_SIGMA005_GAMMA1_V1','MOMENTS_MEAN_COV_FROB_V1')
METHODS=('M0_NAIVE_PERM_B999_V1','M1_DMB_R1_TRI_EXTIID_B999_V1')
def sha(b): return hashlib.sha256(b).hexdigest()
def canon(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()+b'\n'
def wilson(k,n,z):
 p=k/n;den=1+z*z/n;c=(p+z*z/(2*n))/den
 h=z/den*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
 return [max(0.,c-h),min(1.,c+h)]
def classify(k,n):
 a=wilson(k,n,1.6448536269514722);b=wilson(k,n,1.959963984540054)
 if a[0]>=.035 and a[1]<=.065: lab='POINTWISE_PRACTICALLY_CALIBRATED'
 elif b[1]<.035:lab='MATERIAL_CONSERVATISM'
 elif b[0]>.065:lab='MATERIAL_ANTI_CONSERVATISM'
 else:lab='BOUNDARY_OR_INDETERMINATE'
 return a,b,lab

def review(archive:Path,cell_map:dict):
 with zipfile.ZipFile(archive) as z:
  names=z.namelist(); assert len(names)==len(set(names)); assert z.testzip() is None
  files={n:z.read(n) for n in names if not n.endswith('/')}
 def read(n):return json.loads(files[n])
 plan=read('plan/PLAN_SUMMARY.json');ar=read('summary/audit_result.json');pc=read('summary/percell_analysis.json')
 issues=[];checks={};h0={};h1={};classified=[];counts={}
 seals={}
 for phase,folder in [('NULL','h0_run'),('ALT','h1_run')]:
  run=read(f'{folder}/RUN_SEAL.json');ph=read(f'{folder}/PHASE_SEAL.json');seals[phase]=(run,ph)
  checks[f'{phase}_run_self_hash']=sha(canon(run['payload']))==run['run_seal_hash']
  checks[f'{phase}_phase_self_hash']=sha(canon(ph['payload']))==ph['phase_seal_hash']
  checks[f'{phase}_phase_parent_run']=ph['payload']['ordered_source_run_seal_hashes']==[run['run_seal_hash']]
  for role,run_key,ph_key in [('evaluation','expected_index_hash','active_evaluation_index_hash'),('data','expected_data_index_hash','active_data_index_hash'),('feature','expected_feature_index_hash','active_feature_index_hash')]:
   checks[f'{phase}_{role}_plan_seal_binding']=plan['phases'][phase]['index_hashes'][role]==run['payload'][run_key]==ph['payload'][ph_key]
  checks[f'{phase}_metadata_cell_map']=set(cell_map[phase])==set(plan['phases'][phase]['per_cell_replicates'])
  label='H0' if phase=='NULL' else 'H1'
  for typ,key in [('eval','ledger_content_hash'),('feature','feature_ledger_content_hash')]:
   local=ar['checks'][f'{label}_{typ}'];rh=run['payload'][key]
   checks[f'{label}_{typ}_reported_raw_hash_binding']=local['sha256']==rh
   checks[f'{label}_{typ}_reported_counts']=local['rows']==plan['phases'][phase]['counts']['evaluation_rows' if typ=='eval' else 'feature_rows']
  groups=ar['checks'][f'{label}_eval']['groups'];key_counts=collections.Counter()
  for g in groups:
   key=(g['logical_cell_id'],g['feature_id'],g['method_id']);key_counts[key]+=1
   expect=plan['phases'][phase]['per_cell_replicates'].get(key[0],{}).get('replicates')
   if not (type(g['n']) is int and type(g['rejects']) is int and 0<=g['rejects']<=g['n']):issues.append([label,key,'illegal counts'])
   if g['n']!=expect or g['replicate_unique']!=expect:issues.append([label,key,'cell count'])
   if abs(g['rejection_rate']-g['rejects']/g['n'])>1e-14:issues.append([label,key,'rate arithmetic'])
   (h0 if phase=='NULL' else h1)[key]=g
   if phase=='NULL':
    ci90,ci95,lab=classify(g['rejects'],g['n'])
    classified.append({**g,**cell_map[phase][key[0]],'wilson90':ci90,'wilson95':ci95,'calibration_class':lab})
  target={(c,f,m) for c in plan['phases'][phase]['per_cell_replicates'] for f in FEATURES for m in METHODS}
  checks[f'{phase}_group_keys_exact_unique']=set(key_counts)==target and all(v==1 for v in key_counts.values())
  checks[f'{phase}_group_rows_sum']=sum(g['n'] for g in groups)==plan['phases'][phase]['counts']['evaluation_rows']
 checks['ALT_parent_NULL']=seals['ALT'][1]['payload']['parent_phase_seal_hash']==seals['NULL'][1]['phase_seal_hash']
 enriched=[];source_checks=[]
 for x in pc:
  k=(x['logical_cell_id'],x['feature_id']);geo=cell_map['ALT'][k[0]];source=x['source_null_logical_cell_id'];srcgeo=cell_map['NULL'].get(source)
  good=srcgeo is not None and srcgeo['DGP_family']=='N_CIRCLE' and all(srcgeo[t]==geo[t] for t in ['rho','W','stride','T','M'])
  for m,y in x['methods'].items():
   hg=h0[(source,k[1],m)];ag=h1[(*k,m)]
   for field,value in [('h0_type1',hg['rejection_rate']),('nominal_power',ag['rejection_rate']),('n',ag['n'])]:
    if abs(y[field]-value)>1e-12:issues.append([k,m,field,y[field],value])
   if not (0<=y['joint_success']<=y['nominal_power']<=1):issues.append([k,m,'joint outside power'])
   # Correcting tau to tau+.5 changes each absolute error by at most .5.
   if abs(y['raw_mae']-ag['localization_mean'])>.5050001:issues.append([k,m,'MAE exceeds possible correction'])
  source_checks.append({'logical_cell_id':k[0],'feature_id':k[1],'source_geometry_matches':good})
  enriched.append({**x,'rho':geo['rho'],'DGP_family':geo['DGP_family'],'M':geo['M']})
 contrasts={}
 for sc in ['shape_change','mean_shift']:
  means={f:sum(x['size_standardized_power'] for x in pc if x['scenario_id']==sc and x['feature_id']==f)/4 for f in FEATURES}
  contrasts[sc]={'cell_count':4,'BPI_mean':means[FEATURES[0]],'MOMENTS_mean':means[FEATURES[1]],'difference':means[FEATURES[0]]-means[FEATURES[1]],'CI':'NOT_RECOVERABLE_FROM_UPLOADED_SUMMARIES'}
 bootstrap=read('summary/bootstrap_power_diff.json')
 global_diff=sum(d['difference'] for d in contrasts.values())/2
 def rate(family,rho,stride,M,T,method,feature=FEATURES[0]):
  found=[g['rejection_rate'] for g in classified if g['DGP_family']==family and g['rho']==rho and g['stride']==stride and g['M']==M and g['T']==T and g['method_id']==method and g['feature_id']==feature]
  assert len(found)==1;return found[0]
 point={}
 for label,f in [('BPI',FEATURES[0]),('MOMENTS',FEATURES[1])]:
  a=[];b=[];c=[]
  for family in ['N_AR','N_CIRCLE']:
   v16=rate(family,'0',16,192,3120,METHODS[0],f)
   a.append(v16-rate(family,'0',64,192,12288,METHODS[0],f))
   b.append(v16-rate(family,'0',64,48,3120,METHODS[0],f))
   c.append(rate(family,'0',64,192,12288,METHODS[1],f))
  point[label]={'P1_point':sum(a)/2,'P2_point':sum(b)/2,'P3_point':.05-sum(c)/2,'inference':'NO_CI_OR_P_VALUE_COMPUTED_FROM_CELL_TOTALS'}
 for f in FEATURES:
  for m in METHODS:
   subset=[g for g in classified if g['feature_id']==f and g['method_id']==m]
   counts[f'{f}/{m}']={'cells':len(subset),'min_rate':min(g['rejection_rate'] for g in subset),'max_rate':max(g['rejection_rate'] for g in subset),'labels':dict(collections.Counter(g['calibration_class'] for g in subset)),'pointwise_only':True}
 return {'input_sha256':sha(archive.read_bytes()),'input_files':{n:{'bytes':len(b),'sha256':sha(b)} for n,b in files.items()},'evidence_scope':'summary/metadata recomputation; raw ledgers not delivered', 'checks':checks,'arithmetic_join_issues':issues,'local_stream_report_pass':ar['pass'],'source_join_geometry_checks':source_checks,'H0_calibration_counts':counts,'H0_cells':classified,'H1_cells_reported':enriched,'H1_scenario_contrasts':contrasts,'H1_pooled_difference_recomputed':global_diff,'uploaded_bootstrap':bootstrap,'primary_contrast_points':point,'raw_ledger_recomputed_here':False}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--delivery',required=True,type=Path);ap.add_argument('--cell-map',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
 result=review(a.delivery,json.loads(a.cell_map.read_text(encoding='utf-8')))
 with a.out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
 print(json.dumps({'checks':len(result['checks']),'false_checks':[k for k,v in result['checks'].items() if not v],'join_issues':len(result['arithmetic_join_issues']),'out':str(a.out)},ensure_ascii=False))
if __name__=='__main__':main()
