import os
import sys, math, random, json
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from services import predict as P
# one fixed seed, same calm history for both panels. panel B has a volatility shock after the history.
def build(seed=11, hist=120, steps=30, sigma=0.015, shock=1.0):
    rng=random.Random(seed)
    hr=[rng.gauss(0,sigma) for _ in range(hist)]
    fr=[rng.gauss(0,sigma*shock) for _ in range(steps)]
    pts=[]; p=100.0; t=1_700_000_000_000; pts.append({"t":t,"c":p})
    for r in hr: p*=math.exp(r); t+=86400_000; pts.append({"t":t,"c":p})
    f=P.forecast(pts,0.0,steps)
    last=pts[-1]["c"]; path=[]; a=last
    for r in fr: a*=math.exp(r); path.append(a)
    ins=sum(1 for x,y in zip(path,f) if y["lo"]<=x<=y["hi"])
    return {"hist":[round(x["c"],2) for x in pts[-60:]],
            "mid":[round(x["c"],2) for x in f],"lo":[x["lo"] for x in f],"hi":[x["hi"] for x in f],
            "actual":[round(x,2) for x in path],"inside":ins,"steps":steps}
A=build(); B=build(shock=3.0)
print(A["inside"],B["inside"])
json.dump({"calm":A,"shock":B},open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"fan.json"),"w"))
