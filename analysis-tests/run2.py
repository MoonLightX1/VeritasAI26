import sys, math, random, json, time
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from services import predict as P
from headlines import H

# turn things off one at a time on the headline set
def pred_of(t, use_judge=True, use_neg=True):
    s=P._lexicon_score(t)
    if use_judge:
        s,rel,_=P.judge(t,s)
    else: rel=True
    if not rel: return "irrelevant"
    return {"positive":"good","negative":"bad","neutral":"neutral"}[P.label_for(s)]
def acc(**kw): return sum(1 for t,tr in H if pred_of(t,**kw)==tr)/len(H)
print("full",acc(),"no judge",acc(use_judge=False))
# majority baseline
from collections import Counter
c=Counter(tr for _,tr in H); print(c, max(c.values())/len(H))
# wilson
def wilson(k,n,z=1.96):
    p=k/n; d=1+z*z/n; ce=(p+z*z/(2*n))/d; hw=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return ce-hw,ce+hw
print("wilson 55/63",wilson(55,63))
print("wilson good/bad 37/40",wilson(37,40))

# check the forecast range on fake random stocks
def make_points(rets, start=100.0):
    pts=[]; p=start; t=1_700_000_000_000
    pts.append({"t":t,"c":p})
    for r in rets:
        p*=math.exp(r); t+=86400_000
        pts.append({"t":t,"c":p})
    return pts

def trial(seed, steps=30, hist=250, sigma=0.02, dist="normal", sent=0.0, shock=False):
    rng=random.Random(seed)
    def draw(sg):
        if dist=="normal": return rng.gauss(0,sg)
        # student t, 3 dof scaled to same std
        z=rng.gauss(0,1); chi=sum(rng.gauss(0,1)**2 for _ in range(3))
        t=z/math.sqrt(chi/3); return t*sg/math.sqrt(3)
    hr=[draw(sigma) for _ in range(hist)]
    fr=[draw(sigma*(2.5 if shock else 1.0)) for _ in range(steps)]
    pts=make_points(hr)
    f=P.forecast(pts,sent,steps)
    last=pts[-1]["c"]
    path=[last]
    for r in fr: path.append(path[-1]*math.exp(r))
    actual=path[1:]
    inside=sum(1 for a,x in zip(actual,f) if x["lo"]<=a<=x["hi"])/steps
    end_in = f[-1]["lo"]<=actual[-1]<=f[-1]["hi"]
    pred_up = f[-1]["c"]>last
    act_up = actual[-1]>last
    return inside,end_in,pred_up==act_up,(f[-1]["c"]/last-1),(actual[-1]/last-1)

def run(name,N=1500,**kw):
    ins=0;ends=0;dirs=0;errs=[];naive=[]
    for s in range(N):
        a,b,c,pf,ac=trial(s,**kw); ins+=a;ends+=b;dirs+=c;errs.append(abs(pf-ac));naive.append(abs(ac))
    r={"name":name,"band_cov_all_steps":ins/N,"band_cov_final":ends/N,"direction":dirs/N,
       "mae_model":sum(errs)/N,"mae_flat":sum(naive)/N}
    print(r); return r
out=[]
out.append(run("normal returns, no news",dist="normal"))
out.append(run("fat tails (t3), no news",dist="fat"))
out.append(run("vol shock after calm (2.5x)",dist="normal",shock=True))
out.append(run("normal returns, strong good news (+0.8)",dist="normal",sent=0.8))
out.append(run("normal returns, strong bad news (-0.8)",dist="normal",sent=-0.8))
json.dump(out,open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"res2.json"),"w"))
