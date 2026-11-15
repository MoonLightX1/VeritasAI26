import os
import sys, json
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from services import predict as P
from headlines import H
rows=[]
for t,truth in H:
    s=P._lexicon_score(t)
    s2,rel,note=P.judge(t,s)
    lab=P.label_for(s2) if rel else "irrelevant"
    pred={"positive":"good","negative":"bad","neutral":"neutral","irrelevant":"irrelevant"}[lab]
    rows.append((t,truth,pred,round(s2,2)))
classes=["good","bad","neutral","irrelevant"]
cm={a:{b:0 for b in classes} for a in classes}
for t,tr,pr,s in rows: cm[tr][pr]+=1
n=len(rows); ok=sum(1 for r in rows if r[1]==r[2])
print("n",n,"acc",ok/n)
for c in classes:
    tp=cm[c][c]; fn=sum(cm[c].values())-tp; fp=sum(cm[o][c] for o in classes)-tp
    print(c,"support",tp+fn,"prec",tp/(tp+fp) if tp+fp else None,"rec",tp/(tp+fn))
for a in classes: print(a,cm[a])
print("--- errors")
for t,tr,pr,s in rows:
    if tr!=pr: print(tr,"->",pr,s,"|",t)
# direction only on good vs bad
gb=[r for r in rows if r[1] in("good","bad")]
print("good/bad only acc, counting neutral as wrong:",sum(1 for r in gb if r[1]==r[2])/len(gb))
json.dump({"rows":rows,"cm":cm},open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"res1.json"),"w"))
