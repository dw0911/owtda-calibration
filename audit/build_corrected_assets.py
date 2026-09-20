# ruff: noqa  (audit-package verbatim: not subject to repo style lint)
"""Rebuild manuscript assets from accepted summary bytes only. No MC/PH calls."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,struct
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from analysis_repairs import full_heatmap_grid,h1_scenario_summary,decode_rho


def dump_table(out: Path, name: str, rows: list[dict]) -> None:
    (out/(name+'.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def render(h0: list[dict],h1: dict,out: Path) -> dict:
    dump_table(out,'H0_ALL_112', [{**r,'rho':decode_rho(r['rho'])} for r in h0])
    coverage={}
    for budget,stem,title in [('FIXED_M','Figure3_fixedM_CORRECTED','Fixed window count: M = 192'),('FIXED_T','Figure4_fixedT_CORRECTED','Fixed observation budget: T = 3120')]:
        keys,cols,mat=full_heatmap_grid(h0,budget)
        fig,ax=plt.subplots(figsize=(9.5,9.4))
        im=ax.imshow(np.array(mat),vmin=0,vmax=1,aspect='auto',interpolation='nearest')
        ax.set_xticks(range(4),[f"{f.split('_')[0]} / {m.split('_')[0]}" for f,m in cols])
        ax.set_yticks(range(16),[f'{g} | rho={r:g} | s={s} | T={t} | M={m}' for g,r,s,t,m in keys],fontsize=9)
        ax.set_title(title+'\nBoth rho levels retained; no condition averaged or overwritten')
        cb=fig.colorbar(im,ax=ax,pad=.03);cb.set_label('Type-I rejection rate (full scale 0 to 1)')
        fig.tight_layout()
        for ext in ('png','pdf','svg'): fig.savefig(out/(stem+'.'+ext),dpi=180)
        plt.close(fig)
        values=[]
        for rk,line in zip(keys,mat):
            for ck,value in zip(cols,line): values.append(dict(DGP=rk[0],rho=rk[1],stride=rk[2],T=rk[3],M=rk[4],feature=ck[0],method=ck[1],rejection_rate=value))
        dump_table(out,stem+'_DATA',values)
        coverage[budget]={'rows':16,'columns':4,'values':64,'rho_levels':[0,.8],'color_range':[0,1]}
    scenario=h1_scenario_summary(h1);dump_table(out,'H1_SCENARIO_SAME_FOUR_CONDITIONS',scenario)
    cellrows=[]
    for r in h1['percell']:
        o={k:r[k] for k in ('scenario_id','logical_cell_id','source_null_logical_cell_id','feature_id','stride','T','M','W','critical_rank','c095_full_precision','tau_true','size_standardized_power','raw_mae','normalized_mae') if k in r}
        o['rho']=decode_rho(r['rho']);o['n']=1600;o['M']=(r['T']-r['W'])//r['stride']+1
        for m,metrics in r['methods'].items():
            for field,v in metrics.items():o[m.split('_')[0]+'_'+field]=v
        cellrows.append(o)
    # Align all columns for portable CSV; source JSON rows remain fully attributed.
    fields=sorted(set().union(*(r.keys() for r in cellrows)))
    dump_table(out,'H1_ALL_16_GEOMETRY_COMPLETE',[{f:r.get(f) for f in fields} for r in cellrows])
    bootrows=[]
    for sc in ('shape_change','mean_shift'):
        rs=[x for x in scenario if x['scenario']==sc]
        means={x['feature']:x['size_standardized_power'] for x in rs}
        vals=sorted(h1['bootstrap'][sc]['replicate_differences']);low=vals[49];high=vals[1949]
        bootrows.append(dict(scenario=sc,BPI=means['BPI'],MOMENTS=means['MOMENTS'],difference=means['BPI']-means['MOMENTS'],lower95=low,upper95=high,bootstrap_draws=2000,estimand='BPI minus MOMENTS, equal mean over four conditions'))
    dump_table(out,'H1_SCENARIO_DIFFERENCES',bootrows)
    fig,ax=plt.subplots(figsize=(8,3.3))
    theta=np.array([x['difference'] for x in bootrows]);lo=np.array([x['lower95'] for x in bootrows]);hi=np.array([x['upper95'] for x in bootrows])
    ax.errorbar(theta,[1,0],xerr=np.vstack([theta-lo,hi-theta]),fmt='o',capsize=5)
    ax.axvline(0,linestyle='--',linewidth=1)
    ax.set_yticks([1,0],['Shape change','Mean shift']);ax.set_xlim(-1.02,1.02)
    ax.set_xlabel('Difference in size-standardized power: BPI minus MOMENTS')
    ax.set_title('Scenario-specific effects with paired 95% bootstrap intervals')
    fig.tight_layout()
    for ext in ('png','pdf','svg'):fig.savefig(out/('Figure7_difference_CORRECTED.'+ext),dpi=180)
    plt.close(fig)
    # Simple LaTeX tables without inserting raw aggregate inference into a frozen manuscript.
    lines=[r'\begin{tabular}{llrrrr}',r'\toprule',r'场景 & 表示 & 标准化功效 & 平均归一化MAE & 联合成功M0 & 联合成功M1 \\',r'\midrule']
    names={'shape_change':'形状变化','mean_shift':'均值平移'}
    for x in scenario:
        lines.append(f"{names[x['scenario']]} & {x['feature']} & {x['size_standardized_power']:.4f} & {x['mean_normalized_mae']:.5f} & {x['M0_joint_success']:.4f} & {x['M1_joint_success']:.4f} "+r'\\')
    lines.extend([r'\bottomrule',r'\end{tabular}'])
    (out/'Table_H1_COMMON_ESTIMAND.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {'heatmap_coverage':coverage,'H1_scenario_rows':scenario,'H1_full_rows':len(cellrows),'H1_diff_rows':bootrows,'formal_MC_executed':False}


def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--h0',type=Path,required=True);p.add_argument('--h1',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    h0=json.loads(a.h0.read_text(encoding='utf-8-sig'));h1=json.loads(a.h1.read_text(encoding='utf-8-sig'))
    info=render(h0,h1,a.out)
    info['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.h0,a.h1)}
    info['script_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('analysis_repairs.py')]}
    (a.out/'BUILD_REPORT.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
