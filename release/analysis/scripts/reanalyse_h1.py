#!/usr/bin/env python3
"""Read sealed H0/H1 evaluation JSONL; repair downstream H1 analysis only.
No PH, DGP, permutation, multiplier, scientific seed consumption or ledger writes.
NumPy is required only for the registered two-layer bootstrap.  Run on the
project's existing environment.  Inputs are never modified; output dir must be new.
"""
from __future__ import annotations
import argparse, collections, hashlib, hmac, json, math, re, struct, sys, zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any
from review_delivery import FEATURES, METHODS, classify
HEX=re.compile(r'^[0-9a-f]{64}$')

def need(ok: bool, msg: str) -> None:
    if not ok: raise ValueError(msg)

def canonical(v: Any) -> bytes:
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()

def real(v: Any, name: str) -> float:
    if isinstance(v,str) and re.fullmatch(r'f64:[0-9a-f]{16}',v):
        v=struct.unpack('>d',bytes.fromhex(v[4:]))[0]
    need(type(v) in (float,int) and math.isfinite(v),f'{name}: finite numeric value required')
    return float(v)

def integer(v: Any, name: str) -> int:
    need(type(v) is int,f'{name}: integer required');return v

def ident(v: Any,name: str) -> str:
    need(isinstance(v,str) and HEX.fullmatch(v) is not None,f'{name}: 64-hex required');return v

def corrected_location(k: int, W: int, stride: int, T: int) -> tuple[float,float,float]:
    # k is a WINDOW SPLIT INDEX, not raw time. Current registered ALT has tau=T//2.
    need(type(k) is int and type(W) is int and type(stride) is int and type(T) is int,'integer geometry required')
    need(W>0 and stride>0 and T>=W,'invalid geometry')
    M=(T-W)//stride+1;need(1<=k<M,'split outside window sequence')
    estimate=(k-.5)*stride+(W+1)/2
    truth=T//2+.5
    return estimate,truth,abs(estimate-truth)

def critical95(values):
    import numpy as np
    x=np.asarray(values,dtype=float)
    need(x.ndim==1 and len(x)>0 and np.all(np.isfinite(x)),'invalid null statistics')
    rank=math.ceil(.95*(len(x)+1))
    need(rank<=len(x),'too few null observations for registered rank')
    return float(np.partition(x,rank-1)[rank-1])

def percentile95(values):
    x=sorted(float(v) for v in values)
    need(len(x)>0 and all(math.isfinite(v) for v in x),'invalid bootstrap draws')
    return [x[math.ceil(.025*len(x))-1],x[math.ceil(.975*len(x))-1]]

def read_evaluations(path: Path, phase: str, d: dict) -> tuple[dict,dict]:
    import numpy as np
    plan=d['plan']['phases'][phase];seal=d[phase+'_run']['payload'];h=hashlib.sha256()
    groups={};ids=set();rows=0
    stable=('scenario_id','DGP_family','W','stride','T','M_expected','rho',
            'feature_config_hash','feature_generation_id','null_model_config_hash',
            'source_null_logical_cell_id')
    with path.open('rb') as fh:
        for line,raw in enumerate(fh,1):
            h.update(raw)
            if not raw.strip(): continue
            r=json.loads(raw);rows+=1
            need(r.get('phase')==phase,f'{phase} line {line}: wrong phase')
            need(r.get('expected_index_hash')==plan['index_hashes']['evaluation'],f'{phase}:{line}: wrong expected hash')
            eid=ident(r.get('evaluation_id'),'evaluation_id');need(eid not in ids,'duplicate evaluation_id');ids.add(eid)
            cid=r.get('logical_cell_id');fid=r.get('feature_id');mid=r.get('method_id')
            need(cid in plan['per_cell_replicates'] and fid in FEATURES and mid in METHODS,'unregistered cell/feature/method')
            n=plan['per_cell_replicates'][cid]['replicates'];rid=integer(r.get('replicate_id'),'replicate_id')
            need(1<=rid<=n,'replicate outside registered range')
            k=integer(r.get('exceed_count'),'exceed_count');need(0<=k<=999,'exceed_count outside 0..999')
            p=real(r.get('p_value'),'p');need(Decimal(str(p))==Decimal(k+1)/Decimal(1000),'p formula mismatch')
            reject=r.get('reject');need(type(reject) is bool and reject==(k<=49),'reject formula/type mismatch')
            # B is required-value 999 for M0 but FORBIDDEN for M1 (the schema omits
            # forbidden fields), so the check must follow the registered role.
            if mid=='M0_NAIVE_PERM_B999_V1':
                need(r.get('B')==999,'B differs from registered 999')
            else:
                need('B' not in r,'M1 must omit B (forbidden by schema)')
            stat=real(r.get('observed_statistic'),'observed_statistic');need(stat>=0,'negative observed statistic')
            cluster=ident(r.get('cluster_id'),'cluster_id');fsid=ident(r.get('feature_sufficient_id'),'feature_sufficient_id')
            did=ident(r.get('data_unit_id'),'data_unit_id')
            khat=integer(r.get('estimated_change_index'),'estimated_change_index')
            meta={t:r.get(t) for t in stable}
            for t in ['W','stride','T','M_expected']: integer(meta[t],t)
            need(meta['M_expected']==(meta['T']-meta['W'])//meta['stride']+1,'geometry M mismatch')
            if phase=='ALT':
                need(r.get('source_null_phase_seal_hash')==d['NULL_phase']['phase_seal_hash'],'wrong H0 source seal')
                truth=real(r.get('true_boundary_synthetic'),'true_boundary_synthetic')
                need(truth in (meta['T']//2,meta['T']//2+.5),'unknown true-boundary convention')
                olderr=real(r.get('localization_error_synthetic'),'old localization error')
            else:olderr=None
            g=groups.setdefault((cid,fid),{'meta':meta,'n':n,'methods':{},'rows':{}})
            need(g['meta']==meta and g['n']==n,'within-cell metadata changed')
            method_meta=(r.get('method_config_hash'),r.get('method_generation_id'))
            need(all(isinstance(t,str) and t for t in method_meta),'missing method identity')
            if mid in g['methods']:need(g['methods'][mid]==method_meta,'within-method metadata changed')
            g['methods'][mid]=method_meta
            byrep=g['rows'].setdefault(mid,{})
            need(rid not in byrep,'duplicate cell-feature-method replicate')
            byrep[rid]=(cluster,stat,khat,reject,olderr,fsid,did)
    need(h.hexdigest()==seal['ledger_content_hash'],f'{phase}: raw hash differs from seal')
    need(rows==plan['counts']['evaluation_rows'],f'{phase}: wrong row count')
    target={(c,f) for c in plan['per_cell_replicates'] for f in FEATURES}
    need(set(groups)==target,f'{phase}: missing/extra cell-feature')
    computed_set=hashlib.sha256(canonical({'domain':'owtda-id-v1','id_kind':'evaluation_id_set','ids':sorted(ids)})).hexdigest()
    need(computed_set==seal['evaluation_id_set_hash'],f'{phase}: ID-set differs from RUN seal')
    for key,g in groups.items():
        need(set(g['rows'])==set(METHODS),'method missing')
        rr=set(range(1,g['n']+1))
        for m in METHODS:need(set(g['rows'][m])==rr,'replicate set mismatch')
        first=g['rows'][METHODS[0]];second=g['rows'][METHODS[1]]
        for rid in rr:
            a=first[rid];b=second[rid]
            need(a[:3]==b[:3] and a[5:]==b[5:],'method input/statistic/ID pairing mismatch')
        order=sorted(rr,key=lambda rid:first[rid][0]);clusters=[first[rid][0] for rid in order]
        need(len(set(clusters))==g['n'],'duplicate cluster in a cell')
        g['clusters']=clusters;g['stat']=np.array([first[i][1] for i in order],dtype=float)
        g['khat']=np.array([first[i][2] for i in order],dtype=int)
        g['reject']={m:np.array([g['rows'][m][i][3] for i in order],dtype=bool) for m in METHODS}
        if phase=='ALT':g['old_error']=np.array([first[i][4] for i in order],dtype=float)
        del g['rows']
    return groups,{'path':str(path),'sha256':h.hexdigest(),'rows':rows,'evaluation_id_set_hash':computed_set,'pairing':'PASS','replicates':'EXACT_1_TO_REGISTERED_N'}

def h1_points(null: dict,alt: dict) -> tuple[list,dict]:
    import numpy as np
    rows=[]
    for (cell,fid),g in sorted(alt.items()):
        meta=g['meta'];src=(meta['source_null_logical_cell_id'],fid);need(src in null,'source H0 cell missing');ng=null[src]
        need(ng['meta']['DGP_family']=='N_CIRCLE','H1 source is not N_CIRCLE')
        for field in ['W','stride','T','M_expected','rho','feature_config_hash','feature_generation_id','null_model_config_hash']:
            need(meta[field]==ng['meta'][field],f'H1/H0 mismatch: {field}')
        for m in METHODS:need(g['methods'][m]==ng['methods'][m],'H1/H0 method config/generation mismatch')
        critical=critical95(ng['stat'])
        estimate=(g['khat']-.5)*meta['stride']+(meta['W']+1)/2
        truth=meta['T']//2+.5;error=np.abs(estimate-truth)
        good=error<=meta['W']/2
        methods={}
        for m in METHODS:
            rr=g['reject'][m];oldgood=g['old_error']<=meta['W']/2
            ci90,ci95,lab=classify(int(ng['reject'][m].sum()),ng['n'])
            methods[m]={'n':g['n'],'rejects':int(rr.sum()),'nominal_power':float(rr.mean()),
                'h0_type1':float(ng['reject'][m].mean()),'h0_calibration_class':lab,
                'joint_success':float(np.mean(rr & good)),
                'joint_membership_changed':int(np.sum((rr & good)!=(rr & oldgood))),
                'conditional_mae_rejected':float(np.mean(error[rr])) if rr.any() else None}
        rows.append({'logical_cell_id':cell,'source_null_logical_cell_id':src[0],'feature_id':fid,
            'scenario_id':meta['scenario_id'],'rho':meta['rho'],'stride':meta['stride'],'W':meta['W'],'T':meta['T'],
            'tau_true':truth,'c095_full_precision':critical,'critical_rank':math.ceil(.95*(ng['n']+1)),
            'size_standardized_power':float(np.mean(g['stat']>critical)),
            'raw_mae':float(np.mean(error)),'normalized_mae':float(np.mean(error/meta['T'])),
            'old_raw_mae':float(np.mean(g['old_error'])),'methods':methods})
    contrasts={}
    for scenario in ('shape_change','mean_shift'):
        means={f:sum(x['size_standardized_power'] for x in rows if x['scenario_id']==scenario and x['feature_id']==f)/4 for f in FEATURES}
        need(all(sum(x['scenario_id']==scenario and x['feature_id']==f for x in rows)==4 for f in FEATURES),'expected four cells per scenario/feature')
        contrasts[scenario]={'BPI_mean':means[FEATURES[0]],'MOMENTS_mean':means[FEATURES[1]],'difference':means[FEATURES[0]]-means[FEATURES[1]]}
    return rows,contrasts

def bootstrap_scenarios(null,alt,draw_null,draw_alt,iterations=2000):
    """Callbacks produce ONE index vector per layer, reused across all groups.
    Callbacks receive bootstrap_index=1..iterations and sample size.
    Input group arrays must be sorted by cluster_id; tests verify this invariant.
    """
    import numpy as np
    needed={ (g['meta']['source_null_logical_cell_id'],f) for (c,f),g in alt.items() }
    nkeys=sorted(needed);akeys=sorted(alt)
    nc=null[nkeys[0]]['clusters'];ac=alt[akeys[0]]['clusters']
    for key in nkeys:need(null[key]['clusters']==nc,'H0 cluster alignment differs')
    for key in akeys:need(alt[key]['clusters']==ac,'H1 cluster alignment differs')
    draws={sc:[] for sc in ('shape_change','mean_shift')}
    for b in range(1,iterations+1):
        ix0=np.asarray(draw_null(b,len(nc)));ix1=np.asarray(draw_alt(b,len(ac)))
        for ix,n in [(ix0,len(nc)),(ix1,len(ac))]:
            need(ix.shape==(n,) and np.issubdtype(ix.dtype,np.integer) and np.all((ix>=0)&(ix<n)),'invalid bootstrap indices')
        threshold={key:critical95(null[key]['stat'][ix0]) for key in nkeys}
        power={key:float(np.mean(g['stat'][ix1]>threshold[(g['meta']['source_null_logical_cell_id'],key[1])])) for key,g in alt.items()}
        for scenario in draws:
            diff=[]
            for cell,fid in akeys:
                if fid!=FEATURES[0] or alt[(cell,fid)]['meta']['scenario_id']!=scenario:continue
                diff.append(power[(cell,FEATURES[0])]-power[(cell,FEATURES[1])])
            need(len(diff)==4,'scenario does not have four paired cells')
            draws[scenario].append(float(np.mean(diff)))
    return {sc:{'bootstrap_iterations':iterations,'percentile95':percentile95(v),'replicate_differences':v} for sc,v in draws.items()}

def registered_drawers(context):
    import numpy as np
    # Values come from the existing analysis root and resolved plan IDs.
    for k in ['root_key_hex','analysis_id','null_bootstrap_plan_id','alt_bootstrap_plan_id']:
        ident(context.get(k),k); need(set(context[k]) != {'0'},f'{k}: placeholder value forbidden')
    need(context['null_bootstrap_plan_id']!=context['alt_bootstrap_plan_id'],'bootstrap plan roles must be separated')
    def make(plan_key,role,stratum):
        def draw(b,n):
            payload={'domain':'owtda-seed-v1','stream_kind':'analysis_bootstrap','analysis_id':context['analysis_id'],
                'bootstrap_plan_id':context[plan_key],'bootstrap_index':b,'resample_role':role,'stratum_id':stratum}
            seed=hmac.new(bytes.fromhex(context['root_key_hex']),canonical(payload),hashlib.sha256).digest()[:16]
            rng=np.random.Generator(np.random.PCG64DXSM(int.from_bytes(seed,'big')))
            return rng.integers(0,n,size=n,dtype=np.int64,endpoint=False)
        return draw
    return make('null_bootstrap_plan_id','NULL_QUANTILE','N_CIRCLE_MASTER'),make('alt_bootstrap_plan_id','ALT_POWER','CIRCLE_BASED_H1_MASTER')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for a in ['delivery','h0-eval','h1-eval','out-dir']:ap.add_argument('--'+a,required=True,type=Path)
    ap.add_argument('--bootstrap-context',type=Path,help='Existing analysis root and resolved analysis/plan IDs; no date-based seed default.')
    a=ap.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    try:
        with zipfile.ZipFile(a.delivery) as z:
            d={'plan':json.loads(z.read('plan/PLAN_SUMMARY.json'))}
            for phase,folder in [('NULL','h0_run'),('ALT','h1_run')]:
                for kind in ['run','phase']:
                    obj=json.loads(z.read(f'{folder}/{kind.upper()}_SEAL.json'))
                    need(hashlib.sha256(canonical(obj['payload'])+b'\n').hexdigest()==obj[kind+'_seal_hash'],'seal self hash mismatch')
                    d[phase+'_'+kind]=obj
        h0,r0=read_evaluations(a.h0_eval,'NULL',d);h1,r1=read_evaluations(a.h1_eval,'ALT',d)
        points,diffs=h1_points(h0,h1)
        result={'analysis_only':True,'formal_ledgers_modified':False,'delivery_sha256':digest(a.delivery),
            'script_sha256':digest(Path(__file__)),'sources':{'H0':r0,'H1':r1},'percell':points,'scenario_differences':diffs,
            'bootstrap_status':'NOT_RUN_NO_CONTEXT'}
        if a.bootstrap_context:
            context=json.loads(a.bootstrap_context.read_text(encoding='utf-8'));draw0,draw1=registered_drawers(context)
            result['bootstrap']=bootstrap_scenarios(h0,h1,draw0,draw1)
            result['bootstrap_status']='COMPLETE';result['bootstrap_context_sha256']=digest(a.bootstrap_context)
            result['analysis_id']=context['analysis_id']
        h0rows=[]
        for (cell,f),g in sorted(h0.items()):
            for m in METHODS:
                k=int(g['reject'][m].sum());a90,a95,lab=classify(k,g['n'])
                h0rows.append({'logical_cell_id':cell,'feature_id':f,'method_id':m,**g['meta'],'n':g['n'],'rejects':k,
                    'rejection_rate':k/g['n'],'wilson90':a90,'wilson95':a95,'classification':lab})
        (a.out_dir/'H0_POINTWISE.json').write_text(json.dumps(h0rows,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        (a.out_dir/'H1_REANALYSIS.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        print(json.dumps({'status':'ANALYSIS_COMPLETE','bootstrap_status':result['bootstrap_status'],'out':str(a.out_dir)}))
    except Exception as exc:
        (a.out_dir/'ANALYSIS_FAILED.json').write_text(json.dumps({'status':'FAILED','exception':type(exc).__name__,'message':str(exc),'formal_ledgers_modified':False},indent=2),encoding='utf-8')
        raise
if __name__=='__main__':main()
