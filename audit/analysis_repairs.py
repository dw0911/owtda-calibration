# ruff: noqa  (audit-package verbatim: not subject to repo style lint)
"""Read-only manuscript analysis helpers. No scientific data or random draws generated.

primary_from_draws requires actual registered cluster-bootstrap draws. It does
not reconstruct paired uncertainty from cell totals or invent zero tail counts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Sequence


def finite_number(x: object) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError('Expected a finite number, excluding booleans')
    return float(x)


def nearest_rank(values: Sequence[float], probability: float) -> float:
    if not values or not 0 < probability <= 1:
        raise ValueError('Nonempty values and probability in (0,1] required')
    ordered = sorted(finite_number(v) for v in values)
    return ordered[math.ceil(probability * len(ordered)) - 1]


def primary_from_draws(estimate: float, threshold: float,
                       draws: Sequence[float], *, expected_n: int = 10000) -> dict:
    """Registered unstudentized cluster-bootstrap tail rule and basic CI.

    The added one prevents zero Monte Carlo p values. This calculation alone
    does not make an unstudentized bootstrap exact in finite samples.
    """
    estimate, threshold = finite_number(estimate), finite_number(threshold)
    if len(draws) != expected_n or expected_n < 1:
        raise ValueError(f'Expected exactly {expected_n} original bootstrap draws')
    values = [finite_number(v) for v in draws]
    extreme = sum(v-estimate >= estimate-threshold for v in values)
    return {'estimate': estimate, 'threshold': threshold,
            'bootstrap_iterations': len(values), 'extreme_count': extreme,
            'p_boot_one_sided': (extreme+1)/(len(values)+1),
            'basic_ci95': [2*estimate-nearest_rank(values, .975),
                           2*estimate-nearest_rank(values, .025)],
            'scope': 'recomputed from supplied draws; original draw generation not certified here'}


def holm(pvalues: Sequence[float]) -> list[float]:
    p = [finite_number(x) for x in pvalues]
    if not p or any(not 0 <= x <= 1 for x in p):
        raise ValueError('Nonempty p values in [0,1] required')
    order = sorted(range(len(p)), key=lambda i: (p[i], i))
    result = [0.0] * len(p); running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p)-rank)*p[index])
        result[index] = min(1.0, running)
    return result


def decode_rho(x: object) -> float:
    if isinstance(x, str) and x.startswith('f64:'):
        return struct.unpack('>d', bytes.fromhex(x[4:]))[0]
    return float(x)


def full_heatmap_grid(rows: list[dict], budget: str) -> tuple[list[tuple], list[tuple], list[list[float]]]:
    if budget not in ('FIXED_M', 'FIXED_T'):
        raise ValueError('Unknown budget')
    rs = [r for r in rows if (r['M_expected']==192 if budget=='FIXED_M' else r['T']==3120)]
    # rho and physical geometry are retained. Never overwrite a duplicate key.
    rowkeys = sorted({(r['DGP_family'], decode_rho(r['rho']), r['stride'],r['T'],r['M_expected']) for r in rs})
    colkeys = sorted({(r['feature_id'],r['method_id']) for r in rs})
    lookup = {}
    for r in rs:
        key = ((r['DGP_family'],decode_rho(r['rho']),r['stride'],r['T'],r['M_expected']),
               (r['feature_id'],r['method_id']))
        if key in lookup:
            raise ValueError(f'Duplicate heatmap key: {key}')
        n,k = r['n'],r['rejects']
        if type(n) is not int or type(k) is not int or not 0 <= k <= n or n<=0:
            raise ValueError('Invalid counts')
        lookup[key] = k/n
    if len(rowkeys)!=16 or len(colkeys)!=4 or len(lookup)!=64:
        raise ValueError('Expected complete 16 x 4 budget panel')
    try: matrix = [[lookup[(rk,ck)] for ck in colkeys] for rk in rowkeys]
    except KeyError as exc: raise ValueError('Missing heatmap cell') from exc
    return rowkeys,colkeys,matrix


def h1_scenario_summary(h1: dict) -> list[dict]:
    """All displayed means use the same four conditions within each scenario.

    Raw MAE is not averaged across T in this main table. Per-cell raw MAE is
    retained separately. Difference CIs cannot be used as feature mean CIs.
    """
    out=[]
    for scenario in ('shape_change','mean_shift'):
        for feature in ('BPI','MOMENTS'):
            rows=[r for r in h1['percell'] if r['scenario_id']==scenario and r['feature_id'].startswith(feature+'_')]
            keys={(decode_rho(r['rho']),r['stride'],r['T'],(r['T']-r['W'])//r['stride']+1) for r in rows}
            if len(rows)!=4 or len(keys)!=4:
                raise ValueError('Expected four unique conditions per scenario-feature')
            result={'scenario':scenario,'feature':feature,'cells':4,
                    'estimand':'equal-weight mean over the same four registered conditions',
                    'size_standardized_power':sum(r['size_standardized_power'] for r in rows)/4,
                    'mean_normalized_mae':sum(r['normalized_mae'] for r in rows)/4}
            for method in ('M0','M1'):
                ids=[k for k in rows[0]['methods'] if k.startswith(method+'_')]
                if len(ids)!=1: raise ValueError('Ambiguous method')
                mid=ids[0]
                for field in ('h0_type1','nominal_power','joint_success'):
                    result[f'{method}_{field}']=sum(r['methods'][mid][field] for r in rows)/4
            out.append(result)
    return out


def mean_vif(width: int, stride: int, windows: int) -> float:
    if any(type(x) is not int or x < 1 for x in (width,stride,windows)):
        raise ValueError('Positive integer geometry required')
    return 1+2*sum((1-h/windows)*max(1-h*stride/width,0)
                   for h in range(1, min(windows, math.ceil(width/stride))))


def main() -> None:
    p=argparse.ArgumentParser(description='Recompute P1-P3 from EXISTING 10,000-draw arrays. No MC/PH.')
    p.add_argument('--draws',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    source=a.draws.read_bytes(); data=json.loads(source)
    # Input: {"P1":{"estimate":...,"draws":[...]},"P2":...,"P3":...}
    if set(data)!={'P1','P2','P3'}: raise ValueError('Exactly P1, P2, P3 are required')
    results={k:primary_from_draws(data[k]['estimate'],threshold,data[k]['draws'])
             for k,threshold in [('P1',.10),('P2',.10),('P3',.01)]}
    adj=holm([results[k]['p_boot_one_sided'] for k in ('P1','P2','P3')])
    for k,padj in zip(('P1','P2','P3'),adj): results[k]['p_holm']=padj
    out={'source_draws_sha256':hashlib.sha256(source).hexdigest(),
         'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'original_cluster_draw_generation_requires_separate_verification':True,
         'results':results}
    # Exclusive output: historic summaries and raw ledgers are never overwritten.
    with a.out.open('x',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False)

if __name__=='__main__': main()
