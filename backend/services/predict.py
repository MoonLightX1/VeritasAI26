import datetime as dt
import math
import os
import re
import threading
import time

from config import BASE_DIR
from services import market, news

# How the prediction works
# 1. grab recent news for the company and score every headline from -1 (bad) to +1 (good)
# 2. turn that into one number for the company, newer headlines count more
# 3. work out the price trend and how jumpy the stock is from its recent history
# 4. draw the future line:
#      - news is neutral / mixed -> the line just keeps following the current trend (stable)
#      - news is clearly good    -> the line leans up
#      - news is clearly bad     -> the line leans down
#    plus a shaded range that gets wider the further out we look.
# This is an estimate for learning, not financial advice, and it says so in the api answer.

MODEL_DIR = os.path.join(BASE_DIR, "model", "moneysprout-26-out")

# ---------- sentiment ----------

POS = set("""beat beats surge surges soar soars jump jumps rally rallies rise rises rose gain gains gained up upgrade upgrades
upgraded record strong stronger growth grow grows profit profits profitable boost boosts bullish outperform outperforms
win wins won approval approved launch launches partnership expands expansion breakthrough buy raises raised optimistic
tops topped higher best demand soaring climbs climb positive success""".split())

NEG = set("""miss misses fall falls fell drop drops dropped plunge plunges plunged slump slumps tumble tumbles sink sinks
sank down downgrade downgrades downgraded lawsuit sues sued probe investigation fine fined recall recalls weak weaker loss
losses layoffs layoff cut cuts bearish underperform decline declines declined warning warns warn fraud ban banned
delay delays delayed lower worst fear fears risk risks concern concerns crash crashes selloff negative fails failed
shortage antitrust penalty""".split())

NEGATORS = {"not", "no", "never", "without", "fails", "failed", "isn't", "wasn't", "won't", "doesn't"}

_engine = {"name": None, "fn": None}
_engine_lock = threading.Lock()


def _lexicon_score(text):
    words = re.findall(r"[a-z']+", text.lower())
    total = 0.0
    hits = 0
    for i, w in enumerate(words):
        val = 1 if w in POS else -1 if w in NEG else 0
        if not val:
            continue
        # "not good" flips it
        if i > 0 and words[i - 1] in NEGATORS:
            val = -val
        total += val
        hits += 1
    if not hits:
        return 0.0
    # squash so one loud word does not max it out
    return max(-1.0, min(1.0, total / (hits + 1.0) * 1.6))


def _load_model_engine():
    # Uses the ai in backend/model/moneysprout-26-out if it is there and loads.
    # It is expected to be a huggingface style text classifier (config.json + weights)
    # whose labels say positive / negative / neutral. Anything else -> None -> lexicon.
    if not os.path.isfile(os.path.join(MODEL_DIR, "config.json")):
        return None
    try:
        from transformers import pipeline  # optional, only needed if you ship a model
        clf = pipeline("text-classification", model=MODEL_DIR, tokenizer=MODEL_DIR, top_k=None, truncation=True)
    except Exception:
        return None

    def run(texts):
        out = []
        for res in clf(texts):
            scores = {str(r["label"]).lower(): float(r["score"]) for r in res}
            pos = next((v for k, v in scores.items() if k.startswith("pos") or k in ("bullish", "label_2")), None)
            neg = next((v for k, v in scores.items() if k.startswith("neg") or k in ("bearish", "label_0")), None)
            if pos is None or neg is None:
                raise ValueError("model labels not understood")
            out.append(pos - neg)
        return out

    try:
        run(["test"])  # make sure the labels make sense before we trust it
    except Exception:
        return None
    return run


def _get_engine():
    with _engine_lock:
        if _engine["fn"] is None:
            fn = _load_model_engine()
            if fn:
                _engine.update(name="moneysprout-26-out", fn=fn)
            else:
                _engine.update(name="keyword fallback", fn=lambda texts: [_lexicon_score(t) for t in texts])
        return _engine["name"], _engine["fn"]


def score_headlines(items):
    name, fn = _get_engine()
    if not items:
        return name, []
    try:
        scores = fn([i["title"] for i in items])
    except Exception:
        # model died on us, do not take the page down with it
        name = "keyword fallback"
        scores = [_lexicon_score(i["title"]) for i in items]
    return name, scores


def combine(items, scores, now=None):
    # newer headlines count more (about a 3 day half-ish life), and only a few
    # headlines means we are less sure, so the number is pulled toward 0
    now = now or time.time()
    wsum = 0.0
    ssum = 0.0
    for it, s in zip(items, scores):
        age_days = max(0.0, (now - it["time"]) / 86400.0)
        w = math.exp(-age_days / 3.0)
        wsum += w
        ssum += w * s
    if wsum <= 0:
        return 0.0
    return (ssum / wsum) * (wsum / (wsum + 1.0))


def label_for(s):
    if s >= 0.15:
        return "positive"
    if s <= -0.15:
        return "negative"
    return "neutral"


# ---------- forecast ----------

# how many steps ahead to draw for each chart range
HORIZON = {"1D": 45, "1W": 26, "1M": 7, "3M": 12, "6M": 21, "1Y": 30, "5Y": 90, "MAX": 26}


def _next_time(t_ms, step_ms):
    step = step_ms
    t = t_ms + step
    if step < 20 * 3600 * 1000:
        # intraday: just keep going on the same spacing
        return t
    if step <= 3 * 86400 * 1000:
        # daily: skip saturdays and sundays
        while dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).weekday() >= 5:
            t += 86400 * 1000
    return t


def forecast(points, sentiment, steps):
    closes = [p["c"] for p in points]
    n = len(closes)
    if n < 8:
        return []
    look = min(60, n - 1)
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(n - look, n) if closes[i - 1] > 0 and closes[i] > 0]
    if len(rets) < 5:
        return []
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    sigma = max(math.sqrt(var), 1e-5)
    # a trend alone should not be allowed to run away
    mu = max(-1.5 * sigma, min(1.5 * sigma, mu))

    # how much the news is allowed to take over: 0 when it is neutral, 1 when it is clearly one sided
    a = max(0.0, min(1.0, (abs(sentiment) - 0.10) / 0.50))
    news_drift = sentiment * 0.45 * sigma
    drift = (1.0 - a) * mu + a * news_drift

    step_ms = _median([points[i]["t"] - points[i - 1]["t"] for i in range(max(1, n - 20), n)])
    t = points[-1]["t"]
    price = closes[-1]
    out = []
    for k in range(1, steps + 1):
        # momentum fades a little the further out we go
        price *= math.exp(drift * (0.985 ** k))
        t = _next_time(t, step_ms)
        spread = 1.28 * sigma * math.sqrt(k)  # roughly an 80% range
        out.append({
            "t": int(t),
            "c": round(price, 2),
            "lo": round(price * math.exp(-spread), 2),
            "hi": round(price * math.exp(spread), 2),
        })
    return out


def _median(xs):
    xs = sorted(x for x in xs if x > 0)
    if not xs:
        return 86400000
    return xs[len(xs) // 2]


def predict(ticker, range_name):
    h = market.history(ticker, range_name)
    pts = h["points"]

    items = news.headlines(ticker)[:12]
    engine, scores = score_headlines(items)
    s = combine(items, scores)
    lab = label_for(s)

    future = forecast(pts, s, HORIZON.get(range_name, 20))
    if not future:
        raise market.MarketUnavailable("Not enough price history to predict from.")

    last = pts[-1]["c"]
    end = future[-1]["c"]
    change = round((end - last) / last * 100, 2)

    if lab == "neutral":
        why = "News is mixed or quiet, so the line keeps following the recent trend."
    elif lab == "positive":
        why = "Recent news looks positive, so the line leans up."
    else:
        why = "Recent news looks negative, so the line leans down."

    return {
        "ticker": ticker,
        "range": range_name,
        "points": future,
        "from_price": last,
        "to_price": end,
        "change_pct": change,
        "sentiment": {"score": round(s, 3), "label": lab, "engine": engine, "articles": len(items)},
        "why": why,
        "news": [
            {"title": it["title"], "publisher": it["publisher"], "link": it["link"],
             "time": it["time"], "score": round(sc, 2)}
            for it, sc in zip(items, scores)
        ],
        "disclaimer": "An estimate built from recent news and price trend. Not financial advice.",
    }
