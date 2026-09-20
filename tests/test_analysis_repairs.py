# ruff: noqa  (audit-package verbatim: not subject to repo style lint)
from pathlib import Path
import math,sys,json
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'audit'))
from analysis_repairs import nearest_rank,primary_from_draws,holm,full_heatmap_grid,h1_scenario_summary,mean_vif

def test_p_never_zero_and_conditional_holm():
    ps=[primary_from_draws(t,c,[t]*10000)['p_boot_one_sided'] for t,c in [(.5354,.1),(.533,.1),(.0266,.01)]]
    assert ps==[1/10001]*3
    assert holm(ps)==[3/10001]*3

def test_primary_tail_boundary_and_basic():
    r=primary_from_draws(.5,.25,[.25,.5,.75,1],expected_n=4)
    assert r['extreme_count']==2 and r['p_boot_one_sided']==3/5
    assert r['basic_ci95']==[0,.75]

@pytest.mark.parametrize('values,p,result',[([4,1,3,2],.5,2),([4,1,3,2],1,4),(list(range(2000)),.025,49),(list(range(2000)),.975,1949)])
def test_nearest_rank(values,p,result): assert nearest_rank(values,p)==result

@pytest.mark.parametrize('bad',[float('nan'),float('inf'),True,'0.1'])
def test_draws_reject_invalid(bad):
    with pytest.raises(ValueError): primary_from_draws(.5,.1,[bad],expected_n=1)

def test_reject_wrong_draw_count():
    with pytest.raises(ValueError): primary_from_draws(.5,.1,[.5]*9999)

def test_holm_order_and_monotonic():
    assert holm([.2,.001,.01])==pytest.approx([.2,.003,.02])

@pytest.mark.parametrize('W,s,M',[(64,16,192),(64,8,383),(64,64,48),(12,4,3),(12,5,8),(4,1,2),(5,7,4)])
def test_vif_matches_covariance_quadratic_form(W,s,M):
    direct=sum(max(W-abs(i-j)*s,0)/W for i in range(M) for j in range(M))/M
    assert mean_vif(W,s,M)==pytest.approx(direct,abs=1e-12)
    if W%s==0 and M>=W//s:
        q=W//s
        assert mean_vif(W,s,M)==pytest.approx(q-(q*q-1)/(3*M))

def make_grid():
    rows=[]
    for family in ('N_AR','N_CIRCLE'):
        for rho in (0,.8):
            for stride in (8,16,32,64):
                for feature in ('BPI','MOMENTS'):
                    for method in ('M0','M1'):
                        rows.append(dict(DGP_family=family,rho=rho,stride=stride,T=64+191*stride,M_expected=192,feature_id=feature,method_id=method,n=2500,rejects=125))
    return rows

def test_preserve_all_rho_geometry():
    rk,ck,m=full_heatmap_grid(make_grid(),'FIXED_M')
    assert len(rk)==16 and len(ck)==4 and sum(len(row) for row in m)==64
    assert {row[1] for row in rk}=={0,.8}

def test_reject_duplicate_grid():
    rows=make_grid()
    with pytest.raises(ValueError): full_heatmap_grid(rows+[rows[0]],'FIXED_M')

def test_reject_missing_grid():
    with pytest.raises(ValueError): full_heatmap_grid(make_grid()[:-1],'FIXED_M')

def test_equal_marginal_counts_do_not_determine_paired_variance():
    # Both datasets have identical marginal rates; paired difference variance differs.
    x=[0,0,1,1];y1=[0,0,1,1];y2=[1,1,0,0]
    assert sum(y1)==sum(y2)
    assert sum((a-b)**2 for a,b in zip(x,y1)) != sum((a-b)**2 for a,b in zip(x,y2))

@pytest.mark.parametrize('values,k',[([1.,3.,7.],1),([1.,3.,7.],2),([0.,1.,2.,4.],2)])
def test_finite_population_bridge_variance(values,k):
    import itertools
    M=len(values);mean=sum(values)/M
    draws=[sum(x-mean for x in order[:k])/math.sqrt(M) for order in itertools.permutations(values)]
    var=sum(v*v for v in draws)/len(draws)
    s2=sum((v-mean)**2 for v in values)/M
    assert var==pytest.approx(k*(M-k)/(M*(M-1))*s2)

def test_h1_summary_derives_M_when_absent():
    cells=[]
    for sc in ('shape_change','mean_shift'):
        for f in ('BPI','MOMENTS'):
            for rho in (0,.8):
                for s in (16,64):
                    cells.append(dict(scenario_id=sc,feature_id=f+'_V1',rho=rho,stride=s,W=64,T=64+191*s,size_standardized_power=.5,normalized_mae=.1,methods={m+'_V1':dict(h0_type1=.05,nominal_power=.5,joint_success=.4) for m in ('M0','M1')}))
    results=h1_scenario_summary({'percell':cells})
    assert len(results)==4 and all(x['size_standardized_power']==.5 for x in results)
