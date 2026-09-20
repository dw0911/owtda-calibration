# ruff: noqa  (audit-package verbatim: not subject to repo style lint)
"""Read-only byte/canonical/index checks; does not execute any scientific trial."""
from pathlib import Path
import json,hashlib,sys
R=Path(sys.argv[1]); O=Path(sys.argv[2]); O.mkdir(exist_ok=True,parents=True)
def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
summary=json.loads((R/'governance/active_index_summary.json').read_text()); results=[]
for sealfile in sorted((R/'artifacts/summaries').glob('PHASE_SEAL_*.json')):
 seal=json.loads(sealfile.read_text()); p=seal['payload'];phase=p['phase'];rev=sealfile.stem.removeprefix('PHASE_SEAL_')
 seal_ok=hashlib.sha256(canon(p)+b'\n').hexdigest()==seal['phase_seal_hash']
 for kind,idkey,lkey,setkind in [('DATA','data_unit_id','logical_data_key','data_unit_id_set'),('FEATURE','feature_sufficient_id','logical_feature_key','feature_sufficient_id_set'),('EVALUATION','evaluation_id','logical_evaluation_key','evaluation_id_set')]:
  f=R/f'governance/ACTIVE_{kind}_INDEX_{rev}.jsonl'; bsha=hashlib.sha256();csha=hashlib.sha256(); ids=set(); keys=set();sources=set();n=0; last=None;ordered=True
  with f.open('rb') as stream:
   for line in stream:
    bsha.update(line);j=json.loads(line);csha.update(canon(j)+b'\n');n+=1;ids.add(j[idkey]);keys.add(j[lkey]);sources.add(j['source_run_seal_hash']);ordered &= last is None or last<j[lkey];last=j[lkey]
  kh=kind.lower()+'_index_hash'; target=p['active_'+kh];idh=hashlib.sha256(canon({'domain':'owtda-id-v1','id_kind':setkind,'ids':sorted(ids)})).hexdigest()
  result={'phase':phase,'kind':kind,'file':str(f.relative_to(R)),'n':n,'unique_ids':len(ids),'unique_logical_keys':len(keys),'logical_keys_strictly_ordered':ordered,'count_matches':n==summary[phase][kind.lower()+'_rows'],'raw_sha256':bsha.hexdigest(),'canonical_sha256':csha.hexdigest(),'declared_index_hash':target,'raw_hash_matches':bsha.hexdigest()==target,'canonical_reserialization_matches':csha.hexdigest()==target,'source_seals_match':sources==set(p['ordered_source_run_seal_hashes']),'phase_self_hash':seal_ok,'id_set_hash':idh}
  if setkind+'_hash' in p:result['idset_matches']=idh==p[setkind+'_hash']
  results.append(result)
(O/'active_index_checks.json').write_text(json.dumps({'scope':'active index bytes, not actual scientific ledgers','total_index_rows':sum(x['n'] for x in results),'results':results},indent=2))
print(json.dumps(results,indent=2))
