import datetime as dt
import json
import math
import os
import re
import threading
import time

from config import BASE_DIR
from services import market, news

# how it works
# 1. score each headline from -1 (bad) to +1 (good)
# 2. mix them into one mood number, newer ones count more
# 3. get the price trend and how jumpy the stock is
# 4. draw the line, with a range that gets wider the further out it goes
# just a guess, not financial advice

MODEL_DIR = os.path.join(BASE_DIR, "model", "moneysprout-26-out")

# sentiment

POS = set("""beat beats surge surges soar soars jump jumps rally rallies rise rises rose gain gains gained up upgrade upgrades
upgraded record strong stronger growth grow grows profit profits profitable boost boosts bullish outperform outperforms
win wins won approval approved launch launches partnership expands expansion breakthrough buy raises raised optimistic
tops topped higher best demand soaring climbs climb positive success""".split())

NEG = set("""miss misses fall falls fell drop drops dropped plunge plunges plunged slump slumps tumble tumbles sink sinks
sank down downgrade downgrades downgraded lawsuit sues sued probe investigation fined recall recalls weak weaker loss
losses layoffs layoff cut cuts bearish underperform decline declines declined warning warns warn fraud ban banned
delay delays delayed lower worst fear fears risk risks concern concerns crash crashes selloff negative fails failed
shortage antitrust penalty scandal allegations alleged misconduct harassment resigns resign resignation ousted
fired indicted indictment charged subpoena subpoenaed settlement controversy backlash tariffs sanctions breach hack
hacked outage blasted slammed troubled""".split())

# stuff that can move a whole stock: scandals, legal trouble, fraud
SEVERE = set("""scandal allegations alleged misconduct harassment resigns resignation ousted indicted indictment
charged subpoena subpoenaed fraud probe investigation lawsuit sues sued antitrust recall hack hacked breach
sanctions ban banned bankruptcy""".split())

NEGATORS = {"not", "no", "never", "without", "fails", "failed", "isn't", "wasn't", "won't", "doesn't"}

_engine = {"name": None, "fn": None}
_engine_lock = threading.Lock()


# context rules: a scary word is not always bad news (a trailer for "The Affair" is not a scandal)
# skip quoted titles and entertainment, and only count a personal scandal if an exec is in it
_QUOTED = re.compile(r"[\u201c\"][^\u201d\"]{2,}[\u201d\"]|\u2018[^\u2019]{2,}\u2019|(?<![\w])'[^']{2,}'(?![\w])")
ENTERTAINMENT = set("""trailer teaser movie movies film films episode episodes premiere premieres sequel prequel actor actress
cast docuseries soundtrack streaming-release miniseries""".split())
BUSINESS = set("""stock stocks shares share earnings revenue profit profits investors investor analyst analysts lawsuit sues sued
antitrust investigation regulators ftc sec doj ceo cfo shareholders valuation guidance forecast acquisition acquires
merger layoffs recall tariffs""".split())
ROLES = re.compile(r"\b(ceo|cfo|cto|coo|executive|exec|founder|co-founder|chairman|chair|president|chief|boss|director|billionaire|owner)\b", re.I)
PERSONAL = re.compile(r"\b(affair|affairs|extramarital|misconduct|harassment|scandal|allegations?|accused)\b", re.I)


def strip_titles(text):
    return _QUOTED.sub(" ", text)


def personal_scandal(text):
    clean = strip_titles(text)
    return bool(ROLES.search(clean) and PERSONAL.search(clean))


def judge(title, score):
    """(score, relevant, note) after the context rules."""
    words = set(re.findall(r"[a-z\-]+", strip_titles(title).lower()))
    if words & ENTERTAINMENT and not (words & BUSINESS):
        return 0.0, False, "About a show, film or trailer, not the company's business"
    if personal_scandal(title):
        return min(score, -0.85), True, "Executive scandal"
    return score, True, ""


def _lexicon_score(text):
    clean = strip_titles(text)
    if personal_scandal(text):
        return -0.85
    words = re.findall(r"[a-z']+", clean.lower())
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
    words = set(re.findall(r"[a-z']+", strip_titles(text).lower()))
    return bool(words & SEVERE) or personal_scandal(text)


# what is in the model folder
# if it fails to load we save the reason and show it in the app

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
    # files can be in the folder or a folder or two down
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
    # what kind of model is it (checked once)
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
            # LoRA adapter, needs a base model named somewhere
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
    # returns (model, tokenizer)
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
            # classifier adapter needs the label count
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
    # uses the model in backend/model/moneysprout-26-out if it is a classifier
    # anything else returns None and we use the keyword scorer
    kind = _inspect()
    if kind not in ("classifier", "adapter_cls"):
        return None
    try:
        from transformers import pipeline  # optional
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
        run(["test"])  # sanity check the labels
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
        # model failed, do not take the page down
        name = "keyword fallback"
        scores = [_lexicon_score(i["title"]) for i in items]
    return name, scores


def combine(items, scores, now=None):
    # newer counts more (about 4 days), and few headlines pull the number toward 0
    now = now or time.time()
    wsum = 0.0
    ssum = 0.0
    severe_w = 0.0
    for it, s in zip(items, scores):
        age_days = max(0.0, (now - it["time"]) / 86400.0)
        w = math.exp(-age_days / 4.0)
        wsum += w
        ssum += w * s
        # a scandal should not get cancelled by ten "stock rises" headlines
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


# forecast

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
    # (trend, swing) per step from recent log returns
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
    # cap the trend so it cannot run away
    return max(-1.5 * sigma, min(1.5 * sigma, mu)), sigma


def forecast(points, sentiment, steps, end_log=None):
    """future points after the last real one
    not a straight line: most of the move is early, a stretched price gets pulled back,
    and there is a little wiggle from the stock's own past moves
    end_log is the AI's target (log return), the line ends there if given"""
    import random
    v = _vol(points)
    if not v:
        return []
    mu, sigma = v
    closes = [p["c"] for p in points]
    n = len(closes)
    start = closes[-1]

    # fade, about 85% of the move is done by the 2/3 point
    tau = max(1.0, steps / 2.5)
    weights = [math.exp(-k / tau) for k in range(1, steps + 1)]
    wtot = sum(weights)
    cum, run = [], 0.0
    for w in weights:
        run += w
        cum.append(run / wtot)  # 0..1, bends over

    if end_log is None:
        a = max(0.0, min(1.0, (abs(sentiment) - 0.10) / 0.50))
        news_drift = sentiment * 0.45 * sigma
        drift = (1.0 - a) * mu + a * news_drift
        total = drift * wtot  # sum of the fading per-step drift
        # pull back toward the average if it ran too far
        ma = sum(closes[-50:]) / len(closes[-50:])
        dev = math.log(start / ma) if ma > 0 else 0.0
        dev = max(-3 * sigma * math.sqrt(steps), min(3 * sigma * math.sqrt(steps), dev))
        total -= 0.25 * dev
    else:
        total = end_log

    # wiggle from the stock's own moves, same every time
    look = min(120, n - 1)
    hist = [math.log(closes[i] / closes[i - 1]) for i in range(n - look, n) if closes[i - 1] > 0 and closes[i] > 0]
    hm = sum(hist) / len(hist)
    hist = [r - hm for r in hist]
    rng = random.Random(int(points[-1]["t"]) ^ (n * 7919))
    wig, run = [], 0.0
    for _ in range(steps):
        run += rng.choice(hist) * 0.6
        wig.append(run)
    # wiggle starts and ends at zero so we still land on the target
    bridge = [w - (k + 1) / steps * wig[-1] for k, w in enumerate(wig)]

    step_ms = _median([points[i]["t"] - points[i - 1]["t"] for i in range(max(1, n - 20), n)])
    t = points[-1]["t"]
    out = []
    for k in range(1, steps + 1):
        price = start * math.exp(total * cum[k - 1] + bridge[k - 1])
        t = _next_time(t, step_ms)
        spread = 1.28 * sigma * math.sqrt(k)  # roughly an 80% range
        out.append({
            "t": int(t),
            "c": round(price, 2),
            "lo": round(start * math.exp(math.log(price / start) - spread), 2),
            "hi": round(start * math.exp(math.log(price / start) + spread), 2),
        })
    return out


def _median(xs):
    xs = sorted(x for x in xs if x > 0)
    if not xs:
        return 86400000
    return xs[len(xs) // 2]


def _build(items, scores, rel, notes):
    rows = [{"title": it["title"], "publisher": it["publisher"], "link": it["link"], "time": it["time"],
             "score": round(sc, 2), "relevant": r, "note": nt,
             "severe": r and sc < 0 and is_severe(it["title"])}
            for it, sc, r, nt in zip(items, scores, rel, notes)]
    pos = [r for r in rows if r["score"] >= 0.15]
    neg = [r for r in rows if r["score"] <= -0.15]
    mid = len(rows) - len(pos) - len(neg)
    severe = [r for r in neg if r["severe"]]
    s = combine(items, [r["score"] for r in rows])
    return rows, pos, neg, mid, severe, s, label_for(s)


def _ai_verify(gen, name, items, scores, rel, notes):
    """AI rechecks the top headlines and changes scores in place
    returns what it changed, or None if the answer was unreadable"""
    now = time.time()

    def weight(i):
        age = max(0.0, (now - items[i]["time"]) / 86400.0)
        return (abs(scores[i]) + (0.6 if is_severe(items[i]["title"]) else 0.0) + 0.1) * math.exp(-age / 6.0)

    idx = sorted(range(len(items)), key=weight, reverse=True)[:16]
    lines = "\n".join("%d. %s" % (n + 1, items[i]["title"]) for n, i in enumerate(idx))
    prompt = (
        "You check news headlines about %s for a stock app. For each headline decide what it means for the company's stock:\n"
        '- "good": real good news for the business (earnings, growth, deals, upgrades)\n'
        '- "bad": real bad news for the business (lawsuits, investigations, executive scandals, weak results, regulators)\n'
        '- "neutral": routine or mixed\n'
        '- "irrelevant": not about the company\'s business, e.g. a movie, show or trailer title, a review, or an unrelated person\n'
        "Titles in quotes are names of shows, films or products, they are not events.\n\n%s\n\n"
        'Reply with ONLY a JSON object mapping each number to a verdict, like {"1": "bad", "2": "irrelevant"}.' % (name, lines)
    )
    with _gen_lock:
        raw = gen(prompt)
    verdicts = {}
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            for k, v in json.loads(m.group(0)).items():
                verdicts[int(k)] = str(v).lower().strip()
        except (ValueError, AttributeError):
            verdicts = {}
    if not verdicts:
        for k, v in re.findall(r"(\d+)\W{1,4}(good|bad|neutral|irrelevant)", raw.lower()):
            verdicts[int(k)] = v
    if not verdicts:
        return None

    changes = []
    for n, i in enumerate(idx):
        v = verdicts.get(n + 1)
        if v not in ("good", "bad", "neutral", "irrelevant"):
            continue
        old_s, old_r = scores[i], rel[i]
        if v == "good":
            scores[i], rel[i] = (old_s if old_s >= 0.5 else 0.5), True
        elif v == "bad":
            scores[i], rel[i] = (old_s if old_s <= -0.5 else -0.5), True
        elif v == "neutral":
            scores[i], rel[i] = 0.0, True
        else:
            scores[i], rel[i] = 0.0, False
            notes[i] = "AI: not about the company's business"
        if (old_s >= 0.15) != (scores[i] >= 0.15) or (old_s <= -0.15) != (scores[i] <= -0.15) or old_r != rel[i]:
            changes.append('"%s" -> %s' % (items[i]["title"][:55], v))
    return changes


HORIZON_TEXT = {"1D": "the next 45 minutes", "1W": "the next few trading hours", "1M": "the next 7 trading days",
                "3M": "the next 12 trading days", "6M": "the next 21 trading days", "1Y": "the next 30 trading days",
                "5Y": "the next 90 trading days", "MAX": "the next 26 weeks"}


def _parse_ai(text):
    # asked for json but small models ramble, so be forgiving
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
    top = sorted([r for r in rows if r.get("relevant", True)], key=lambda n: abs(n["score"]) + (0.5 if n["severe"] else 0), reverse=True)[:15]
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
    """progress(step_id, status, detail) is called as it goes so the page can show it
    ai=True lets the model help if it loads"""
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
    # context check
    rel, notes = [True] * len(items), [""] * len(items)
    for i, it in enumerate(items):
        scores[i], rel[i], notes[i] = judge(it["title"], scores[i])
    off = sum(1 for r in rel if not r)
    cb("score", "done", "Scored %d headlines with %s. %d ignored as not about the business (shows, films, trailers)." % (len(items), engine, off))

    gen = None
    if ai:
        cb("model", "running", "Loading the AI model. The first time it has to download the base model, which can take a few minutes...")
        gen = _get_generator()
        if gen:
            cb("model", "done", "AI model ready")
        else:
            cb("model", "warn", "Not available: " + (model_note() or "no text-writing AI model found"))

    # AI second opinion on the top headlines
    if gen and items:
        cb("verify", "running", "The AI is double-checking the most important headlines...")
        try:
            changes = _ai_verify(gen, name, items, scores, rel, notes)
            if changes is None:
                cb("verify", "warn", "The AI answer could not be read, so the rule-based check was kept.")
            else:
                msg = "AI re-read the key headlines and changed %d verdict%s" % (len(changes), "" if len(changes) == 1 else "s")
                msg += (": " + "; ".join(changes[:2])[:160]) if changes else ". Everything checked out."
                cb("verify", "done", msg)
        except Exception as e:
            cb("verify", "warn", "The AI check failed (%s), so the rule-based check was kept." % e)
    elif ai:
        cb("verify", "skipped", "No AI model, so only the rule-based context check was used")
    else:
        cb("verify", "skipped", "Not used for this request")

    rows, pos, neg, mid, severe, s, lab = _build(items, scores, rel, notes)

    cb("flags", "running", "Looking for big trouble like lawsuits, investigations or executive scandals...")
    if severe:
        cb("flags", "warn", "%d serious headline%s, like: \"%s\"" % (len(severe), "" if len(severe) == 1 else "s", severe[0]["title"][:90]))
    else:
        cb("flags", "done", "Nothing scary found")
    ignored = sum(1 for r in rows if not r["relevant"])
    cb("score", "done", "%d good, %d bad, %d neutral (%d ignored as not about the business). Overall mood %+.2f (%s), scored by %s"
       % (len(pos), len(neg), mid, ignored, s, lab, engine))

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

    ai_info = {"used": False, "outlook": None, "change_pct": None, "confidence": None,
               "stat_change_pct": round(stat_pct, 2), "note": ""}
    ai_summary = None
    future = stat
    if ai:
        if not gen:
            ai_info["note"] = model_note() or "No text-writing AI model is available."
            cb("ai", "skipped", "Using the trend + news forecast instead")
        else:
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
                    # direction and number have to agree
                    if res["outlook"] == "up":
                        chg = abs(chg)
                    elif res["outlook"] == "down":
                        chg = -abs(chg)
                    elif res["outlook"] == "flat":
                        chg = chg * 0.25
                    chg = max(-99.0, chg)
                    ai_end = math.log(1 + chg / 100.0)
                    # cap wild guesses
                    cap = 2.5 * sigma * math.sqrt(steps)
                    ai_end = max(-cap, min(cap, ai_end))
                    # mostly the AI, some trend
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


# background jobs, so the page can show progress

STEPS = [
    ("history", "Grabbing the price history"),
    ("trend", "Working out the price trend"),
    ("news", "Searching the news"),
    ("score", "Reading every headline"),
    ("model", "Loading the AI model"),
    ("verify", "AI double-checks the main headlines"),
    ("flags", "Looking for big trouble"),
    ("ai", "AI writes its guess and summary"),
    ("forecast", "Drawing the forecast line"),
]
_jobs = {}
_jobs_lock = threading.Lock()
JOB_KEEP = 1800


def _clean_jobs():
    now = time.time()
    for k in [k for k, j in _jobs.items() if now - j["created"] > JOB_KEEP]:
        del _jobs[k]


# one job at a time, the AI is heavy
_queue = []
_running = None
_worker_on = False


def _run_job(job):
    def progress(step, status, detail=None):
        with job["lock"]:
            for st in job["steps"]:
                if st["id"] == step:
                    st["status"] = status
                    if detail is not None:
                        st["detail"] = detail

    try:
        job["result"] = predict(job["ticker"], job["range"], progress=progress, ai=True)
    except market.MarketUnavailable as e:
        job["error"] = str(e) or "Market data is not available right now."
    except Exception as e:
        print("[MoneySprout predict] %s: %s" % (type(e).__name__, e), flush=True)
        job["error"] = "Something went wrong while predicting. Try again."
    job["done"] = True


def _worker():
    # next job until the line is empty
    global _running, _worker_on
    while True:
        with _jobs_lock:
            job = None
            while _queue and job is None:
                jid = _queue.pop(0)
                j = _jobs.get(jid)
                if j and not j["cancelled"] and not j["done"]:
                    job = j
                    j["started_at"] = time.time()
                    _running = jid
            if job is None:
                _running = None
                _worker_on = False
                return
        _run_job(job)
        with _jobs_lock:
            _running = None


def start_job(user_id, ticker, range_name):
    import uuid
    global _worker_on
    with _jobs_lock:
        _clean_jobs()
        # one per person, give back the running one
        for k, j in _jobs.items():
            if j["user"] == user_id and not j["done"] and j["ticker"] == ticker and j["range"] == range_name:
                return k
        if sum(1 for j in _jobs.values() if j["user"] == user_id and not j["done"]) >= 2:
            return None
        jid = uuid.uuid4().hex
        job = {"user": user_id, "ticker": ticker, "range": range_name, "created": time.time(), "done": False,
               "error": None, "result": None, "lock": threading.Lock(), "started_at": None, "cancelled": False,
               "steps": [{"id": i, "title": t, "status": "pending", "detail": ""} for i, t in STEPS]}
        _jobs[jid] = job
        _queue.append(jid)
        if not _worker_on:
            _worker_on = True
            threading.Thread(target=_worker, daemon=True).start()
    return jid


def cancel_job(user_id, jid):
    # only works while still in line
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job or job["user"] != user_id:
            return False
        if job["started_at"] is None and not job["done"]:
            job["cancelled"] = True
            job["done"] = True
            job["error"] = "Cancelled."
            if jid in _queue:
                _queue.remove(jid)
            return True
    return False


def job_state(user_id, jid):
    job = _jobs.get(jid)
    if not job or job["user"] != user_id:
        return None
    with job["lock"]:
        steps = [dict(st) for st in job["steps"]]
    # place in line, 1 = next or running
    position = None
    if job["started_at"] is None and not job["done"]:
        with _jobs_lock:
            if jid in _queue:
                position = _queue.index(jid) + 1 + (1 if _running else 0)
    started = job["started_at"] or time.time()
    return {"done": job["done"], "error": job["error"], "steps": steps,
            "queued": position is not None, "position": position,
            "elapsed": int(time.time() - started) if job["started_at"] else 0,
            "result": job["result"] if job["done"] else None}


# the summary on the side

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
    # cut off a half finished sentence
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
