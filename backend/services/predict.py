import datetime as dt
import json
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
shortage antitrust penalty scandal affair allegations alleged misconduct harassment resigns resign resignation ousted
fired indicted indictment charged subpoena subpoenaed settlement controversy backlash tariffs sanctions breach hack
hacked outage blasted slammed troubled""".split())

# things that can move a whole stock on their own: leadership scandals, legal trouble, fraud
SEVERE = set("""scandal affair allegations alleged misconduct harassment resigns resignation ousted indicted indictment
charged subpoena subpoenaed fraud probe investigation lawsuit sues sued antitrust recall hack hacked breach
sanctions ban banned bankruptcy""".split())

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


def is_severe(text):
    words = set(re.findall(r"[a-z']+", text.lower()))
    return bool(words & SEVERE)


# Finding out what is in the model folder, and saying so out loud when it does not load.
# Every failure sets a plain-english reason that is printed in the server window and shown
# in the app (under the summary), so "it is not loading" always has an answer.

_status = {"checked": False, "kind": None, "dir": MODEL_DIR, "base": None, "reason": ""}
_status_lock = threading.RLock()


def _note(msg):
    _status["reason"] = msg
    print("[MoneySprout model] " + msg, flush=True)


def _need(pkg, e):
    if isinstance(e, ImportError):
        return "%s is not installed (%s). Run: pip install %s" % (pkg, e, pkg)
    return "The model files are there but failed to load: %s: %s" % (type(e).__name__, e)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _find_model_dir():
    # the files may be right in the folder or one or two folders down (e.g. moneysprout-26-out/adapter)
    def has_model(d):
        try:
            n = os.listdir(d)
        except OSError:
            return False
        return "adapter_config.json" in n or "config.json" in n or any(x.lower().endswith(".gguf") for x in n)

    todo = [(MODEL_DIR, 0)]
    while todo:
        d, depth = todo.pop(0)
        if has_model(d):
            return d
        if depth < 2 and os.path.isdir(d):
            for x in sorted(os.listdir(d)):
                if os.path.isdir(os.path.join(d, x)) and not x.startswith("."):
                    todo.append((os.path.join(d, x), depth + 1))
    return None


def _inspect():
    # what kind of model is in the folder? (decided once, from the files)
    with _status_lock:
        if _status["checked"]:
            return _status["kind"]
        _status["checked"] = True
        try:
            names = [n for n in os.listdir(MODEL_DIR) if not n.startswith(".")] if os.path.isdir(MODEL_DIR) else []
        except OSError:
            names = []
        if not names:
            _note("The model folder is empty or missing (%s). Put the model files there." % MODEL_DIR)
            return None
        d = _find_model_dir()
        if not d:
            _note("No config.json, adapter_config.json or .gguf file found in %s (or the folders inside it). Found: %s"
                  % (MODEL_DIR, ", ".join(sorted(names)[:8])))
            return None
        _status["dir"] = d
        files = os.listdir(d)

        gguf = [n for n in files if n.lower().endswith(".gguf")]
        if gguf:
            _status.update(kind="gguf", base=os.path.join(d, gguf[0]))
        elif "adapter_config.json" in files:
            # a LoRA adapter, it sits on top of a base model that has to be named somewhere
            try:
                cfg = _read_json(os.path.join(d, "adapter_config.json"))
            except Exception as e:
                _note("adapter_config.json could not be read: %s" % e)
                return None
            base = None
            for where in (d, os.path.dirname(d)):
                f = os.path.join(where, "base_model.txt")
                if os.path.isfile(f):
                    lines = [l.strip() for l in open(f, encoding="utf-8").read().splitlines() if l.strip()]
                    if lines:
                        base = lines[0]
                        break
            base = base or cfg.get("base_model_name_or_path")
            if not base:
                _note("This is a LoRA adapter but I cannot tell which base model it was trained on. "
                      "Put the base model's name (like Qwen/Qwen2.5-1.5B-Instruct) in base_model.txt next to the adapter.")
                return None
            task = str(cfg.get("task_type") or "CAUSAL_LM").upper()
            kind = {"SEQ_CLS": "adapter_cls", "SEQ_2_SEQ_LM": "adapter_seq2seq"}.get(task, "adapter_causal")
            _status.update(kind=kind, base=base)
        else:
            try:
                cfg = _read_json(os.path.join(d, "config.json"))
            except Exception as e:
                _note("config.json could not be read: %s" % e)
                return None
            arch = (cfg.get("architectures") or [""])[0]
            mt = str(cfg.get("model_type") or "").lower()
            if "SequenceClassification" in arch:
                _status.update(kind="classifier")
            elif "CausalLM" in arch or "LMHeadModel" in arch:
                _status.update(kind="causal")
            elif "ConditionalGeneration" in arch or "Seq2Seq" in arch or mt in ("t5", "mt5", "bart", "pegasus", "led"):
                _status.update(kind="seq2seq")
            elif not arch and mt in ("gpt2", "gpt_neox", "llama", "mistral", "qwen2", "qwen3", "gemma", "gemma2", "phi", "phi3", "falcon", "opt"):
                _status.update(kind="causal")
            else:
                _note("config.json says architecture '%s' (type '%s'), which is not a text classifier or text writer I can use. Files: %s"
                      % (arch or "unknown", mt or "unknown", ", ".join(files[:8])))
                return None
        print("[MoneySprout model] found a %s model in %s%s" % (
            _status["kind"], d, (" (base: %s)" % _status["base"]) if _status["kind"].startswith("adapter") else ""), flush=True)
        return _status["kind"]


def model_note():
    # empty when everything is fine
    return _status["reason"]


def _load_hf(task):
    # returns (model, tokenizer) for a plain model folder or a LoRA adapter on its base model
    from transformers import (AutoTokenizer, AutoModelForCausalLM, AutoModelForSeq2SeqLM,
                              AutoModelForSequenceClassification)
    d, kind = _status["dir"], _status["kind"]
    auto = {"cls": AutoModelForSequenceClassification, "causal": AutoModelForCausalLM, "seq2seq": AutoModelForSeq2SeqLM}[task]
    try:
        tok = AutoTokenizer.from_pretrained(d)
    except Exception:
        tok = AutoTokenizer.from_pretrained(_status["base"])
    if kind.startswith("adapter"):
        from peft import PeftModel
        extra = {}
        if task == "cls":
            # a classification adapter needs to know how many labels its head has
            try:
                from safetensors import safe_open
                with safe_open(os.path.join(d, "adapter_model.safetensors"), framework="pt") as f:
                    for k in f.keys():
                        if k.endswith(("score.weight", "classifier.weight", "out_proj.weight")) and "lora" not in k:
                            extra["num_labels"] = f.get_tensor(k).shape[0]
                            break
            except Exception:
                pass
        base = auto.from_pretrained(_status["base"], torch_dtype="auto", **extra)
        model = PeftModel.from_pretrained(base, d)
        try:
            model = model.merge_and_unload()  # faster to run
        except Exception:
            pass
    else:
        model = auto.from_pretrained(d, torch_dtype="auto")
    return model, tok


def _load_model_engine():
    # Uses the ai in backend/model/moneysprout-26-out when it is a text classifier
    # (labels like positive / negative / neutral). Anything else -> None -> keyword scorer.
    kind = _inspect()
    if kind not in ("classifier", "adapter_cls"):
        return None
    try:
        from transformers import pipeline  # optional, only needed if you ship a model
        model, tok = _load_hf("cls")
        clf = pipeline("text-classification", model=model, tokenizer=tok, top_k=None, truncation=True)
    except Exception as e:
        _note(_need("peft transformers torch" if kind == "adapter_cls" else "transformers torch", e))
        return None

    def run(texts):
        out = []
        for res in clf(texts):
            scores = {str(r["label"]).lower(): float(r["score"]) for r in res}
            pos = next((v for k, v in scores.items() if k.startswith("pos") or k in ("bullish", "label_2")), None)
            neg = next((v for k, v in scores.items() if k.startswith("neg") or k in ("bearish", "label_0")), None)
            if pos is None and neg is None and set(scores) == {"label_0", "label_1"}:
                pos, neg = scores["label_1"], scores["label_0"]
            if pos is None or neg is None:
                raise ValueError("labels are %s, expected positive / negative" % sorted(scores))
            out.append(pos - neg)
        return out

    try:
        run(["test"])  # make sure the labels make sense before we trust it
    except Exception as e:
        _note("The classifier loaded but its labels did not work: %s" % e)
        return None
    return run


# a text-writing model writes the summary
_gen = {"tried": False, "fn": None}
_gen_lock = threading.Lock()


def _load_generator():
    kind = _inspect()
    if kind not in ("causal", "seq2seq", "adapter_causal", "adapter_seq2seq", "gguf"):
        return None

    if kind == "gguf":
        try:
            from llama_cpp import Llama
            llm = Llama(model_path=_status["base"], n_ctx=4096, verbose=False)
        except Exception as e:
            _note(_need("llama-cpp-python", e))
            return None

        def run_gguf(prompt):
            r = llm.create_chat_completion(messages=[{"role": "user", "content": prompt}], max_tokens=260, temperature=0)
            return (r["choices"][0]["message"]["content"] or "").strip()
        return run_gguf

    causal = kind in ("causal", "adapter_causal")
    try:
        from transformers import pipeline
        model, tok = _load_hf("causal" if causal else "seq2seq")
        gen = pipeline("text-generation" if causal else "text2text-generation", model=model, tokenizer=tok)
    except Exception as e:
        _note(_need("peft transformers torch" if kind.startswith("adapter") else "transformers torch", e))
        return None

    def run(prompt):
        text = prompt
        if causal and getattr(tok, "chat_template", None):
            try:
                text = tok.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
            except Exception:
                text = prompt
        opts = {"max_new_tokens": 260, "do_sample": False}
        if causal:
            opts["return_full_text"] = False
        res = gen(text, **opts)
        return (res[0].get("generated_text") or "").strip()

    return run


def _get_generator():
    with _gen_lock:
        if not _gen["tried"]:
            _gen["tried"] = True
            _gen["fn"] = _load_generator()
        return _gen["fn"]


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
    # newer headlines count more (about a 4 day half-ish life), and only a few
    # headlines means we are less sure, so the number is pulled toward 0
    now = now or time.time()
    wsum = 0.0
    ssum = 0.0
    severe_w = 0.0
    for it, s in zip(items, scores):
        age_days = max(0.0, (now - it["time"]) / 86400.0)
        w = math.exp(-age_days / 4.0)
        wsum += w
        ssum += w * s
        # an executive scandal / lawsuit / investigation is not cancelled out by ten
        # "stock rises" headlines, so negative ones like that get an extra push of their own
        if s < 0 and is_severe(it["title"]):
            severe_w += w
    if wsum <= 0:
        return 0.0
    base = (ssum / wsum) * (wsum / (wsum + 1.0))
    return max(-1.0, min(1.0, base - min(0.7, 0.3 * severe_w)))


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


def _vol(points):
    # (trend per step, typical swing per step) from the recent prices, as log returns
    closes = [p["c"] for p in points]
    n = len(closes)
    if n < 8:
        return None
    look = min(60, n - 1)
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(n - look, n) if closes[i - 1] > 0 and closes[i] > 0]
    if len(rets) < 5:
        return None
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    sigma = max(math.sqrt(var), 1e-5)
    # a trend alone should not be allowed to run away
    return max(-1.5 * sigma, min(1.5 * sigma, mu)), sigma


def forecast(points, sentiment, steps, end_log=None):
    """Future points after the last real one. Normally built from the trend + news mood.
    If end_log is given (the AI's target as a log return over all the steps), the line is
    bent to end there instead, and the shaded range still comes from how jumpy the stock is."""
    v = _vol(points)
    if not v:
        return []
    mu, sigma = v
    closes = [p["c"] for p in points]
    n = len(closes)

    # how much the news is allowed to take over: 0 when it is neutral, 1 when it is clearly one sided
    a = max(0.0, min(1.0, (abs(sentiment) - 0.10) / 0.50))
    news_drift = sentiment * 0.45 * sigma
    drift = (1.0 - a) * mu + a * news_drift

    step_ms = _median([points[i]["t"] - points[i - 1]["t"] for i in range(max(1, n - 20), n)])
    t = points[-1]["t"]
    start = closes[-1]
    price = start
    out = []
    for k in range(1, steps + 1):
        if end_log is None:
            # momentum fades a little the further out we go
            price *= math.exp(drift * (0.985 ** k))
        else:
            price = start * math.exp(end_log * k / steps)
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


HORIZON_TEXT = {"1D": "the next 45 minutes", "1W": "the next few trading hours", "1M": "the next 7 trading days",
                "3M": "the next 12 trading days", "6M": "the next 21 trading days", "1Y": "the next 30 trading days",
                "5Y": "the next 90 trading days", "MAX": "the next 26 weeks"}


def _parse_ai(text):
    # the model was asked for json, but small models wander, so be forgiving
    out = {"outlook": None, "change_pct": None, "confidence": None, "summary": None}
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            out["outlook"] = str(d.get("outlook") or "").lower() or None
            try:
                out["change_pct"] = float(str(d.get("change_pct")).replace("%", "").replace("+", ""))
            except (TypeError, ValueError):
                pass
            out["confidence"] = str(d.get("confidence") or "").lower() or None
            out["summary"] = (str(d.get("summary") or "").strip()) or None
        except ValueError:
            pass
    if out["outlook"] is None:
        low = text.lower()
        for word, val in (("bearish", "down"), ("negative", "down"), ("down", "down"), ("fall", "down"), ("bullish", "up"),
                          ("positive", "up"), ("up", "up"), ("rise", "up"), ("stable", "flat"), ("flat", "flat")):
            if re.search(r"\b" + word + r"\b", low):
                out["outlook"] = val
                break
    if out["change_pct"] is None:
        mm = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
        if mm:
            out["change_pct"] = float(mm.group(1))
    if out["outlook"] in ("positive", "bullish", "increase", "rise"):
        out["outlook"] = "up"
    elif out["outlook"] in ("negative", "bearish", "decrease", "fall"):
        out["outlook"] = "down"
    elif out["outlook"] in ("stable", "neutral", "sideways"):
        out["outlook"] = "flat"
    if out["outlook"] not in ("up", "down", "flat"):
        out["outlook"] = None
    if out["summary"] is None and not m:
        cleaned = _clean(text)
        out["summary"] = cleaned if len(cleaned) > 30 else None
    return out


def _ai_prompt(name, ticker, range_name, rows, counts, sentiment, recent_pct, sigma, stat_pct):
    top = sorted(rows, key=lambda n: abs(n["score"]) + (0.5 if n["severe"] else 0), reverse=True)[:15]
    lines = "\n".join("- %s%s (tone %+.2f)" % ("[SERIOUS] " if n["severe"] else "", n["title"], n["score"]) for n in top) or "- (no recent news)"
    return (
        "You are a careful stock analyst helper for beginners. Using ONLY the information below, predict where the price of %s (%s) "
        "is heading over %s. Weigh serious problems (leadership scandals, legal or regulatory trouble) heavily, "
        "and if the news is routine or mixed, say the stock is stable and continues its current trend.\n\n"
        "Recent headlines (%s):\n%s\n\n"
        "News mood score: %+.2f (from -1 bad to +1 good)\n"
        "Recent price move: %+.1f%%. Typical swing per step: %.2f%%.\n"
        "A simple trend-based estimate for the same period: %+.1f%%.\n\n"
        "Reply with ONLY a JSON object, no other text, like this:\n"
        '{"outlook": "up" or "down" or "flat", "change_pct": number (expected %% change over the period), '
        '"confidence": "low" or "medium" or "high", "summary": "4 to 5 short sentences explaining why, mentioning any executive or legal issues"}'
        % (name, ticker, HORIZON_TEXT.get(range_name, "the coming period"), counts, lines, sentiment, recent_pct, sigma * 100, stat_pct)
    )


def predict(ticker, range_name, progress=None, ai=False):
    """progress(step_id, status, detail) is called as it works, so the app can show what is happening.
    With ai=True the model (if it loads) makes the prediction and the summary too."""
    cb = progress or (lambda *a, **k: None)
    name = (market.company(ticker) or {}).get("name", ticker)

    cb("history", "running", "Downloading %s price history for %s..." % (range_name, name))
    h = market.history(ticker, range_name)
    pts = h["points"]
    steps = HORIZON.get(range_name, 20)
    cb("history", "done", "%d price points, latest close $%.2f" % (len(pts), pts[-1]["c"]))

    cb("trend", "running", "Measuring the recent trend and how jumpy the price is...")
    v = _vol(pts)
    if not v:
        raise market.MarketUnavailable("Not enough price history to predict from.")
    mu, sigma = v
    look = min(30, len(pts) - 1)
    recent_pct = (pts[-1]["c"] / pts[-1 - look]["c"] - 1) * 100
    cb("trend", "done", "Moved %+.1f%% over the last %d points. Typical swing %.2f%% per step." % (recent_pct, look, sigma * 100))

    cb("news", "running", "Searching Yahoo Finance and Google News (stock, earnings, executives, scandals and lawsuits, regulators)...")
    items = news.headlines(ticker, name)[:40]
    pubs = len(set(i["publisher"] for i in items if i["publisher"]))
    newest = ""
    if items:
        hrs = max(0, (time.time() - items[0]["time"]) / 3600)
        newest = ", newest is %s old" % ("%d minutes" % (hrs * 60) if hrs < 1 else "%.0f hours" % hrs if hrs < 48 else "%.0f days" % (hrs / 24))
    cb("news", "done" if items else "warn",
       ("Found %d headlines from %d publishers%s" % (len(items), pubs, newest)) if items
       else "No news came back (feeds may be down). Using the price trend only.")

    cb("score", "running", "Reading every headline and scoring it from bad to good (first time loads the scorer)...")
    engine, scores = score_headlines(items)
    s = combine(items, scores)
    lab = label_for(s)

    rows = [{"title": it["title"], "publisher": it["publisher"], "link": it["link"],
             "time": it["time"], "score": round(sc, 2), "severe": sc < 0 and is_severe(it["title"])}
            for it, sc in zip(items, scores)]
    pos = [r for r in rows if r["score"] >= 0.15]
    neg = [r for r in rows if r["score"] <= -0.15]
    mid = len(rows) - len(pos) - len(neg)
    severe = [r for r in neg if r["severe"]]
    cb("score", "done", "%d good, %d bad, %d neutral. Overall mood %+.2f (%s), scored by %s" % (len(pos), len(neg), mid, s, lab, engine))

    cb("flags", "running", "Checking for serious events like lawsuits, investigations or executive scandals...")
    if severe:
        cb("flags", "warn", "%d serious headline%s, for example: \"%s\"" % (len(severe), "" if len(severe) == 1 else "s", severe[0]["title"][:90]))
    else:
        cb("flags", "done", "None found")

    # best reasons first: strongest and newest
    def strength(r):
        age = max(0.0, (time.time() - r["time"]) / 86400.0)
        return abs(r["score"]) * math.exp(-age / 4.0) + (0.5 if r["severe"] else 0)

    drivers_pos = sorted(pos, key=strength, reverse=True)[:3]
    drivers_neg = sorted(neg, key=strength, reverse=True)[:3]
    counts = "%d positive, %d negative, %d neutral out of %d headlines" % (len(pos), len(neg), mid, len(rows))
    if not rows:
        why = "No recent news was found, so the line just follows the recent price trend (stable)."
    elif lab == "positive":
        why = "Positive because %d headlines are good news vs %d bad." % (len(pos), len(neg))
        if severe:
            why += " Watch out though: %d serious headline%s (leadership, legal or regulatory trouble) holds it back." % (len(severe), "" if len(severe) == 1 else "s")
    elif lab == "negative":
        why = "Negative because %d headlines are bad news vs %d good" % (len(neg), len(pos))
        if severe:
            why += ", including serious ones (leadership, legal or regulatory trouble) that outweigh the good news"
        why += "."
    elif pos and neg:
        why = "Stable because the good news (%d) and bad news (%d) roughly cancel out, so the line keeps following the recent trend." % (len(pos), len(neg))
    else:
        why = "Stable because the news is mostly routine and not clearly good or bad, so the line keeps following the recent trend."

    last = pts[-1]["c"]
    stat = forecast(pts, s, steps)
    stat_pct = (stat[-1]["c"] / last - 1) * 100

    # ---- the AI's own prediction ----
    ai_info = {"used": False, "outlook": None, "change_pct": None, "confidence": None,
               "stat_change_pct": round(stat_pct, 2), "note": ""}
    ai_summary = None
    future = stat
    if ai:
        cb("model", "running", "Loading the AI model. The first time this downloads the base model and can take several minutes...")
        gen = _get_generator()
        if not gen:
            note = model_note() or "No text-writing AI model is available."
            ai_info["note"] = note
            cb("model", "warn", "Not available: " + note)
            cb("ai", "skipped", "Using the trend + news forecast instead")
        else:
            cb("model", "done", "AI model ready")
            cb("ai", "running", "The AI is reading %d headlines and thinking about where the price is going..." % min(15, len(rows)))
            t0 = time.time()
            try:
                with _gen_lock:  # one at a time, these are heavy
                    raw = gen(_ai_prompt(name, ticker, range_name, rows, counts, s, recent_pct, sigma, stat_pct))
                res = _parse_ai(raw)
            except Exception as e:
                res = None
                ai_info["note"] = "The AI failed: %s" % e
                cb("ai", "warn", ai_info["note"] + ". Using the trend + news forecast instead.")
            if res is not None:
                ai_summary = res["summary"]
                ai_info.update(outlook=res["outlook"], confidence=res["confidence"])
                if res["outlook"] is None and res["change_pct"] is None:
                    ai_info["note"] = "The AI answered but I could not read a prediction from it."
                    cb("ai", "warn", ai_info["note"] + " Using the trend + news forecast instead.")
                else:
                    chg = res["change_pct"]
                    if chg is None:
                        chg = {"up": 1.0, "down": -1.0, "flat": 0.0}[res["outlook"]] * sigma * 100 * math.sqrt(steps)
                    # make the direction and the number agree
                    if res["outlook"] == "up":
                        chg = abs(chg)
                    elif res["outlook"] == "down":
                        chg = -abs(chg)
                    elif res["outlook"] == "flat":
                        chg = chg * 0.25
                    chg = max(-99.0, chg)
                    ai_end = math.log(1 + chg / 100.0)
                    # do not let a wild guess draw something impossible for this stock
                    cap = 2.5 * sigma * math.sqrt(steps)
                    ai_end = max(-cap, min(cap, ai_end))
                    # mostly the AI, a little of the real trend to keep it grounded
                    target = 0.75 * ai_end + 0.25 * math.log(1 + stat_pct / 100.0)
                    future = forecast(pts, s, steps, end_log=target)
                    ai_info.update(used=True, change_pct=round((math.exp(ai_end) - 1) * 100, 2))
                    cb("ai", "done", "AI says %s%s, about %+.1f%% (%.0fs)" % (
                        {"up": "UP", "down": "DOWN", "flat": "STABLE", None: "?"}[res["outlook"]],
                        (", " + res["confidence"] + " confidence") if res["confidence"] else "", ai_info["change_pct"], time.time() - t0))
    else:
        cb("model", "skipped", "Not used for this request")
        cb("ai", "skipped", "Not used for this request")

    cb("forecast", "running", "Drawing the predicted line and the likely range...")
    if not future:
        raise market.MarketUnavailable("Not enough price history to predict from.")
    end = future[-1]["c"]
    change = round((end - last) / last * 100, 2)
    cb("forecast", "done", "Ends around $%.2f (%+.1f%%)" % (end, change))

    out = {
        "ticker": ticker,
        "range": range_name,
        "points": future,
        "from_price": last,
        "to_price": end,
        "change_pct": change,
        "sentiment": {"score": round(s, 3), "label": lab, "engine": engine, "articles": len(items), "engine_note": model_note()},
        "why": why,
        "counts": counts,
        "drivers": {"positive": drivers_pos, "negative": drivers_neg},
        "news": rows,
        "ai": ai_info,
        "method": "ai" if ai_info["used"] else "trend+news",
        "disclaimer": "An estimate built from recent news and price trend. Not financial advice.",
    }
    if ai:
        if ai_summary and len(ai_summary) > 20:
            out["summary"] = {"text": ai_summary, "by": "moneysprout-26-out", "ai": True, "note": ""}
        else:
            if ai_info["used"] and not ai_summary:
                ai_info["note"] = ai_info["note"] or "The AI gave a prediction but no written summary."
            out["summary"] = {"text": _template_summary(out), "by": "template", "ai": False, "note": ai_info["note"] or model_note()}
        cb("summary", "done", "Summary ready" + ("" if out["summary"]["ai"] else " (auto-written, the AI did not write it)"))
    return out


# ---------- background jobs (so the app can show live progress) ----------

STEPS = [
    ("history", "Loading price history"),
    ("trend", "Measuring the price trend"),
    ("news", "Searching the news"),
    ("score", "Scoring every headline"),
    ("flags", "Checking for serious events"),
    ("model", "Loading the AI model"),
    ("ai", "AI makes its prediction and summary"),
    ("forecast", "Drawing the forecast"),
]
_jobs = {}
_jobs_lock = threading.Lock()
JOB_KEEP = 1800


def _clean_jobs():
    now = time.time()
    for k in [k for k, j in _jobs.items() if now - j["created"] > JOB_KEEP]:
        del _jobs[k]


def start_job(user_id, ticker, range_name):
    import uuid
    with _jobs_lock:
        _clean_jobs()
        # one at a time per person, if they already have one running give that back
        for k, j in _jobs.items():
            if j["user"] == user_id and not j["done"] and j["ticker"] == ticker and j["range"] == range_name:
                return k
        if sum(1 for j in _jobs.values() if j["user"] == user_id and not j["done"]) >= 2:
            return None
        jid = uuid.uuid4().hex
        job = {"user": user_id, "ticker": ticker, "range": range_name, "created": time.time(), "done": False,
               "error": None, "result": None, "lock": threading.Lock(),
               "steps": [{"id": i, "title": t, "status": "pending", "detail": ""} for i, t in STEPS]}
        _jobs[jid] = job

    def progress(step, status, detail=None):
        with job["lock"]:
            for st in job["steps"]:
                if st["id"] == step:
                    st["status"] = status
                    if detail is not None:
                        st["detail"] = detail

    def work():
        try:
            job["result"] = predict(ticker, range_name, progress=progress, ai=True)
        except market.MarketUnavailable as e:
            job["error"] = str(e) or "Market data is not available right now."
        except Exception as e:
            print("[MoneySprout predict] %s: %s" % (type(e).__name__, e), flush=True)
            job["error"] = "Something went wrong while predicting. Try again."
        job["done"] = True

    threading.Thread(target=work, daemon=True).start()
    return jid


def job_state(user_id, jid):
    job = _jobs.get(jid)
    if not job or job["user"] != user_id:
        return None
    with job["lock"]:
        steps = [dict(st) for st in job["steps"]]
    return {"done": job["done"], "error": job["error"], "steps": steps,
            "elapsed": int(time.time() - job["created"]), "result": job["result"] if job["done"] else None}


# ---------- the summary on the side ----------

_sum_cache = {}
SUM_TTL = 600


def _template_summary(p):
    move = "rise" if p["change_pct"] >= 0 else "fall"
    out = "%s (%s). Over the drawn period the price could %s about %.1f%%, to around $%.2f." % (
        p["why"].rstrip("."), p["counts"], move, abs(p["change_pct"]), p["to_price"])
    d = p["drivers"]
    if d["negative"]:
        out += ' Biggest worry: "%s".' % d["negative"][0]["title"]
    if d["positive"]:
        out += ' Biggest plus: "%s".' % d["positive"][0]["title"]
    return out


def _clean(text):
    text = re.sub(r"\s+", " ", text).strip()
    # drop a trailing half sentence if the model ran out of room
    if text and text[-1] not in ".!?" and "." in text:
        text = text[: text.rindex(".") + 1]
    return text


def summary(ticker, range_name):
    key = (ticker, range_name)
    hit = _sum_cache.get(key)
    if hit and time.time() - hit[0] < SUM_TTL:
        return hit[1]

    p = predict(ticker, range_name)
    name = (market.company(ticker) or {}).get("name", ticker)
    text, by = None, "template"

    gen = _get_generator()
    if gen:
        top = sorted(p["news"], key=lambda n: abs(n["score"]) + (0.5 if n["severe"] else 0), reverse=True)[:15]
        lines = "\n".join("- %s (tone %+.2f)" % (n["title"], n["score"]) for n in top) or "- (no recent news)"
        prompt = (
            "You are a careful stock market helper for beginners. Using ONLY the headlines below, write a summary of "
            "4 to 5 short sentences about %s (%s). Say clearly whether the outlook is positive, negative or stable and WHY. "
            "Mention any leadership, legal, regulatory or personal-conduct issues involving executives if they appear, "
            "and what could happen to the price. Do not invent facts. Do not give financial advice.\n\n"
            "Headlines (%s):\n%s\n\nNews mood: %s (%+.2f)\nPredicted move over the dashed period: %+.1f%% "
            "(from $%.2f to about $%.2f)\n\nSummary:"
            % (name, ticker, p["counts"], lines, p["sentiment"]["label"], p["sentiment"]["score"], p["change_pct"], p["from_price"], p["to_price"])
        )
        try:
            with _gen_lock:  # one at a time, these are heavy
                out = _clean(gen(prompt))
            if len(out) > 20:
                text, by = out, "moneysprout-26-out"
        except Exception:
            pass

    if not text:
        text = _template_summary(p)

    if by == "template" and not model_note():
        _note("The model did not return a usable summary (or it is not a text-writing model).")
    res = {"text": text, "by": by, "ai": by != "template", "note": "" if by != "template" else model_note()}
    _sum_cache[key] = (time.time(), res)
    return res
