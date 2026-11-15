import os
import sys, time, json
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from services import predict as P
now=time.time()
def items(titles, age_days=0.5): return [{"title":t,"time":now-age_days*86400} for t in titles]
good=["Apple beats earnings expectations as iPhone sales climb"]*10
sev=["Alphabet CEO accused of misconduct, board opens probe"]
def comb(ts):
    its=items(ts); sc=[P._lexicon_score(t) for t in ts]
    sc=[P.judge(t,s)[0] for t,s in zip(ts,sc)]
    return round(P.combine(its,sc,now),3), [round(x,2) for x in sc][:3]
print("10 good only", comb(good))
print("10 good + 1 severe", comb(good+sev))
print("1 good", comb(good[:1]))
print("3 good", comb(good[:3]))
print("20 good", comb(good*2))
print("10 bad", comb(["Intel misses revenue estimates, shares tumble"]*10))
# old vs new
its=[{"title":"x","time":now-d*86400} for d in (0,4,8)]
print("weights 0,4,8 days:",[round(__import__('math').exp(-d/4),3) for d in (0,4,8)])

# parse_ai cases
cases={
 "clean json":'{"outlook":"up","change_pct":3.2,"confidence":"medium","summary":"Earnings were strong. Demand is up. Analysts upgraded it."}',
 "json with chatter":'Sure! Here you go:\n{"outlook": "down", "change_pct": "-4.5%", "confidence": "low", "summary": "Lawsuit news weighs on the stock. Watch the probe."}\nHope that helps',
 "no json, words only":"The outlook is bearish because of the investigation, roughly -2% over the period.",
 "words only, stable":"Looks stable and flat, nothing big in the news.",
 "garbage":"asdf qwer zxcv",
 "empty":"",
 "contradiction":'{"outlook":"up","change_pct":-6,"confidence":"high","summary":"The stock will go down a lot because of the scandal and fraud probe."}',
 "positive word":'{"outlook":"positive","change_pct":1.5,"confidence":"high","summary":"Good quarter ahead for the company overall."}',
 "word trap":"The company said earnings were up but the stock could fall hard.",
}
res={}
for k,v in cases.items():
    r=P._parse_ai(v); res[k]=r; print(k,"->",r["outlook"],r["change_pct"],r["confidence"],(r["summary"] or "")[:40])
json.dump(res,open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"res3.json"),"w"))
