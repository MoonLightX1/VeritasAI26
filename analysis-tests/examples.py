# examples for the code analysis page
# run from this folder: python examples.py
# the adapter blocks need the adapter folder (set ADAPTER_DIR or use backend/model/moneysprout-26-out)
# the last block only runs with LOAD_MODEL=1, it loads the 3B model and is slow

import os, sys, math, time, json, random, struct, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, HERE)
from services import predict as P
from services import news

ADAPTER = os.environ.get("ADAPTER_DIR") or os.path.join(HERE, "..", "backend", "model", "moneysprout-26-out")


# example: keyword score
# three headlines, good then bad then boring
heads = [
    "Apple beats earnings expectations as iPhone sales climb",
    "Tesla recalls thousands of vehicles over safety defect",
    "Apple to hold annual developer conference in June",
]
for h in heads:
    print(round(P._lexicon_score(h), 2), h)


# example: not flips a word
# "not" right before a word flips it
print(P._lexicon_score("Ford sales strong"))
print(P._lexicon_score("Ford sales not strong"))


# example: one loud word cannot max it out
# one hit stays below 1, it takes a pile of hits to get there
print(P._lexicon_score("Nvidia surges"))
print(P._lexicon_score("Nvidia surges soars rallies climbs"))


# example: good and bad cancel
# this is the known bug, "downgraded" is -1 and "growth" is +1
print(P._lexicon_score("Netflix downgraded by analysts on slowing growth"))
print(P._lexicon_score("Spotify shares drop as subscriber growth disappoints"))


# example: quoted titles
# stuff in quotes is a title, not news
t = '"The Affair" returns with a dark new season, trailer released'
print(repr(P.strip_titles(t)))
print(P._lexicon_score(t))
print(P.judge(t, P._lexicon_score(t)))


# example: judge on a few
# judge gives back (score, counts or not, note)
for t in ["Best Netflix shows to binge this weekend",
          "Alphabet CEO accused of misconduct, board opens probe",
          "Apple to hold annual developer conference in June"]:
    s = P._lexicon_score(t)
    print(P.judge(t, s), "|", t)


# example: serious or not
# serious means it can move the whole stock by itself
for t in ["Meta fined by regulators in new privacy ruling",
          "Tesla CEO affair rumors swirl",
          "Alphabet hit with antitrust lawsuit",
          "Apple unveils new iPhone"]:
    print(P.is_severe(t), "|", t)


# example: labels
# 0.15 is the line between neutral and not neutral
for s in [-0.5, -0.15, -0.14, 0, 0.14, 0.15, 0.6]:
    print(s, P.label_for(s))


# example: recency weights
# older headlines count less
for d in [0, 1, 2, 4, 8, 16]:
    print(d, "days old counts", round(math.exp(-d / 4.0), 2))


# example: combine piles
# same very positive headline, half a day old, more and more of them
now = 1_700_000_000

def pile(n, score=1.0, hours=12):
    items = [{"title": "Company shares rise on strong demand", "time": now - hours * 3600} for _ in range(n)]
    return items, [score] * n

for n in [1, 3, 10, 20]:
    items, scores = pile(n)
    print(n, "headlines ->", round(P.combine(items, scores, now=now), 3))


# example: one scandal
# ten great headlines and one executive scandal
items, scores = pile(10)
items.append({"title": "Alphabet CEO accused of misconduct, board opens probe", "time": now - 12 * 3600})
scores.append(-0.85)
print(round(P.combine(items, scores, now=now), 3))


# example: no headlines
# nothing to read means a mood of zero
print(P.combine([], []))


# example: trend and swing
# fake stock, 120 days of random moves around 1.5 percent
def make_points(seed=11, days=120, sigma=0.015):
    rng = random.Random(seed)
    p, t = 100.0, 1_700_000_000_000
    pts = [{"t": t, "c": p}]
    for _ in range(days):
        p *= math.exp(rng.gauss(0, sigma))
        t += 86400_000
        pts.append({"t": t, "c": p})
    return pts

pts = make_points()
trend, swing = P._vol(pts)
print("trend per day", round(trend * 100, 3), "percent")
print("swing per day", round(swing * 100, 3), "percent")


# example: the forecast line
# lo and hi are the shaded range
f = P.forecast(pts, 0.0, 30)
print("start", round(pts[-1]["c"], 2))
for k in [0, 1, 9, 29]:
    print("day", k + 1, "lo", f[k]["lo"], "line", f[k]["c"], "hi", f[k]["hi"])


# example: news mood moves the line
# same prices, only the mood changes
for s in [-0.8, 0.0, 0.8]:
    f = P.forecast(pts, s, 30)
    print("news mood", s, "-> ends at", f[-1]["c"])


# example: forecast with an AI target
# end_log is the AI's target as a log return, the line has to land on it
f = P.forecast(pts, 0.0, 30, end_log=math.log(1.05))
print("asked for +5 percent, got", round((f[-1]["c"] / pts[-1]["c"] - 1) * 100, 2), "percent")


# example: how wide the range gets
# 1.28 is the number for an 80 percent range
for k in [1, 5, 10, 30]:
    print("step", k, "range is plus or minus", round(1.28 * swing * math.sqrt(k) * 100, 1), "percent")


# example: reading AI answers
# small models ramble, the parser has to cope
tests = [
    '{"outlook": "up", "change_pct": "+3.2%", "confidence": "medium", "summary": "Strong demand."}',
    'Sure! Here you go: {"outlook": "down", "change_pct": -4.5, "confidence": "low", "summary": "Lawsuit risk."} hope that helps',
    "I think this is bearish, maybe -2% over the period",
    "the stock looks stable and flat",
    "asdf qwer zxcv",
    "",
]
for t in tests:
    r = P._parse_ai(t)
    print(r["outlook"], r["change_pct"], r["confidence"], "|", t[:40])


# example: direction and number disagree
# same fix predict() does, the direction word wins
raw = '{"outlook": "up", "change_pct": -6, "confidence": "high", "summary": "Shares will fall hard after the lawsuit."}'
res = P._parse_ai(raw)
chg = res["change_pct"]
if res["outlook"] == "up":
    chg = abs(chg)
print("model said", res["outlook"], "and", res["change_pct"], "-> app uses", chg)
print("model's own summary:", res["summary"])


# example: AI double check with a pretend AI
# fake_ai stands in for the model
def fake_ai(prompt):
    print(prompt.split("\n\n")[1])
    return '{"1": "irrelevant", "2": "bad", "3": "good"}'

titles = ["Netflix downgraded by analysts on slowing growth",
          "Best Netflix shows to binge this weekend",
          "Coca-Cola delivers better than expected earnings"]
t0 = time.time()
items = [{"title": t, "time": t0} for t in titles]
scores, rel, notes = [], [], []
for t in titles:
    s, r, n = P.judge(t, P._lexicon_score(t))
    scores.append(s); rel.append(r); notes.append(n)
print("before", scores, rel)
print(P._ai_verify(fake_ai, "Netflix", items, scores, rel, notes))
print("after ", scores, rel)


# example: AI answer we cannot read
# verify gives back None and the keyword result stays
print(P._ai_verify(lambda p: "no idea lol", "Netflix", items, scores, rel, notes))


# example: AI blend and cap
# the AI is trusted 75 percent, the trend 25, and a cap stops wild guesses
sigma = 0.02
steps = 30
stat_pct = 1.0
for ai_pct in [6.0, 60.0, -60.0]:
    ai_end = math.log(1 + ai_pct / 100)
    cap = 2.5 * sigma * math.sqrt(steps)
    ai_end = max(-cap, min(cap, ai_end))
    target = 0.75 * ai_end + 0.25 * math.log(1 + stat_pct / 100)
    print("AI says", ai_pct, "-> capped", round((math.exp(ai_end) - 1) * 100, 1), "-> final", round((math.exp(target) - 1) * 100, 1))


# example: same story twice
# dedupe only looks at the first 70 letters, after cleaning
a = "Apple beats earnings expectations as iPhone sales climb"
b = "APPLE BEATS earnings expectations as iPhone sales climb!!"
c = "Apple earnings top estimates on strong iPhone demand"
print(repr(news._norm(a)))
print("a and b same story:", news._norm(a) == news._norm(b))
print("a and c same story:", news._norm(a) == news._norm(c))


# example: whole headline test
# the real 63 headline test in a few lines
from headlines import H
names = {"positive": "good", "negative": "bad", "neutral": "neutral", "irrelevant": "irrelevant"}
right = 0
for t, truth in H:
    s, rel_ok, _ = P.judge(t, P._lexicon_score(t))
    lab = P.label_for(s) if rel_ok else "irrelevant"
    right += names[lab] == truth
print("with rules:", right, "of", len(H))


# example: headline test without the rules
# same test but skip judge()
right = sum(names[P.label_for(P._lexicon_score(t))] == truth for t, truth in H)
print("without rules:", right, "of", len(H))


# example: error bars
# wilson interval, a range for what the real accuracy could be
def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half

lo, hi = wilson(55, 63)
print("55 of 63 ->", round(lo * 100, 1), "to", round(hi * 100, 1))


# example: why more headlines helps
# same 87 percent, but a bigger test makes the range smaller
for n in [63, 200, 1000]:
    k = round(0.873 * n)
    lo, hi = wilson(k, n)
    print(n, "headlines ->", round(lo * 100, 1), "to", round(hi * 100, 1))


# example: coin flip check
# with 1500 trials a coin flip wobbles about this much
print(round(math.sqrt(0.5 * 0.5 / 1500) * 100, 2), "percent")


# example: adapter config
# the small json next to the adapter weights
cfg = json.load(open(os.path.join(ADAPTER, "adapter_config.json")))
for k in ["base_model_name_or_path", "peft_type", "task_type", "r", "lora_alpha", "lora_dropout"]:
    print(k, "=", cfg[k])
print("target_modules =", sorted(cfg["target_modules"]))


# example: inside the adapter file
# safetensors starts with a json header, so we can count things without torch
f = open(os.path.join(ADAPTER, "adapter_model.safetensors"), "rb")
n = struct.unpack("<Q", f.read(8))[0]
header = json.loads(f.read(n))
header.pop("__metadata__", None)
total = sum(math.prod(v["shape"]) for v in header.values())
layers = {int(re.search(r"layers\.(\d+)\.", k).group(1)) for k in header}
print("tensors:", len(header))
print("layers:", len(layers))
print("numbers inside:", total, "(about", round(total / 1e6, 1), "million)")
print("dtype:", {v["dtype"] for v in header.values()})
for k in ["q_proj", "down_proj"]:
    a = header["base_model.model.model.layers.0.%s.lora_A.weight" % ("mlp." + k if k == "down_proj" else "self_attn." + k)]
    b = header["base_model.model.model.layers.0.%s.lora_B.weight" % ("mlp." + k if k == "down_proj" else "self_attn." + k)]
    print(k, "A", a["shape"], "B", b["shape"])


# example: how much of the model is that
# base model is about 3 billion numbers, the adapter is a tiny slice
print(round(total / 3.09e9 * 100, 2), "percent of Qwen2.5-3B")


# example: predict.py finds the adapter
# we point predict.py at the adapter folder and ask what it sees
P.MODEL_DIR = ADAPTER
P._status.update(checked=False, kind=None, dir=ADAPTER, base=None, reason="")
print("kind:", P._inspect())
print("base:", P._status["base"])


# example: loading it
# only runs if LOAD_MODEL=1. with no torch installed you get the plain english reason
if os.environ.get("LOAD_MODEL") == "1":
    gen = P._get_generator()
    print("generator:", gen)
    print("note:", P.model_note())
else:
    print("skipped, set LOAD_MODEL=1 to try")
