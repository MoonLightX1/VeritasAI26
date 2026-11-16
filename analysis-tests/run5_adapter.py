# run5: does the adapter beat plain Qwen on the 63 headlines?
# runs them 3 ways: keywords only, plain Qwen2.5-3B-Instruct, Qwen + our adapter
# needs: pip install torch transformers peft
# run: python run5_adapter.py --adapter ../backend/model/moneysprout-26-out
# no model needed to check the script: python run5_adapter.py --dry

import os, sys, re, json, math, time, random, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
from services import predict as P
from headlines import H

BASE = "Qwen/Qwen2.5-3B-Instruct"
NAMES = {"positive": "good", "negative": "bad", "neutral": "neutral", "irrelevant": "irrelevant"}
CLASSES = ["good", "bad", "neutral", "irrelevant"]


def wilson(k, n, z=1.96):
    # confidence range
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def start_state(t):
    # keywords then context rules, like the app
    s, rel, note = P.judge(t, P._lexicon_score(t))
    return s, rel, note


def label_of(s, rel):
    return NAMES[P.label_for(s)] if rel else "irrelevant"


def run_keyword_only():
    return [label_of(*start_state(t)[:2]) for t, _ in H]


def run_with_ai(gen, chunk=16):
    # 16 per AI call like the app
    # shuffled (fixed seed) because H is sorted by answer
    order = list(range(len(H)))
    random.Random(5).shuffle(order)
    labels = [None] * len(H)
    unreadable = 0
    for a in range(0, len(order), chunk):
        ids = order[a:a + chunk]
        items = [{"title": H[i][0], "time": time.time()} for i in ids]
        scores, rels, notes = [], [], []
        for i in ids:
            s, r, n = start_state(H[i][0])
            scores.append(s); rels.append(r); notes.append(n)
        changes = P._ai_verify(gen, "the companies below", items, scores, rels, notes)
        if changes is None:
            unreadable += 1  # model answer could not be read, keyword result stays
        for j, i in enumerate(ids):
            labels[i] = label_of(scores[j], rels[j])
    return labels, unreadable


def report(title, labels, unreadable=None):
    n = len(H)
    right = sum(1 for (t, truth), lab in zip(H, labels) if truth == lab)
    lo, hi = wilson(right, n)
    cm = {a: {b: 0 for b in CLASSES} for a in CLASSES}
    for (t, truth), lab in zip(H, labels):
        cm[truth][lab] += 1
    flips = cm["good"]["bad"] + cm["bad"]["good"]
    print("")
    print(title)
    print("  right: %d of %d (%.1f percent, could be %.1f to %.1f)" % (right, n, right / n * 100, lo * 100, hi * 100))
    print("  good headlines called bad or the other way round:", flips)
    if unreadable is not None:
        print("  AI answers we could not read:", unreadable)
    print("  rows are the truth, columns are what it said:")
    print("  %-12s %s" % ("", " ".join("%10s" % c for c in CLASSES)))
    for a in CLASSES:
        print("  %-12s %s" % (a, " ".join("%10d" % cm[a][b] for b in CLASSES)))
    return right


def make_gen(model, tok):
    # same as the generator in predict.py
    def gen(prompt):
        text = tok.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt").to(model.device)
        out = model.generate(**ids, max_new_tokens=260, do_sample=False)
        return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    return gen


def dry_gen(prompt):
    # fake AI that says neutral to everything
    nums = re.findall(r"^(\d+)\. ", prompt, re.M)
    return json.dumps({n: "neutral" for n in nums})


def find_adapter(path):
    # files can be a folder or two down, like predict.py
    for root, dirs, files in os.walk(path):
        if "adapter_config.json" in files:
            return root
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=os.path.join(HERE, "..", "backend", "model", "moneysprout-26-out"))
    ap.add_argument("--dry", action="store_true", help="no model, just test the script")
    args = ap.parse_args()

    base_right = report("1. keyword scorer + context rules (no AI)", run_keyword_only())

    if args.dry:
        labels, bad = run_with_ai(dry_gen)
        report("2. dry run, pretend AI says neutral to everything", labels, bad)
        print("\ndry run done. the script works, the numbers above mean nothing")
        return

    adapter = find_adapter(args.adapter)
    if not adapter:
        print("\ncould not find adapter_config.json under", args.adapter)
        return

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import PeftModel
    except ImportError as e:
        print("\nmissing a package (%s). run: pip install torch transformers peft" % e)
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    print("\nloading", BASE, "on", device, "(first time downloads it, takes a while)")
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=dtype).to(device)
    model.eval()

    t0 = time.time()
    labels, bad = run_with_ai(make_gen(model, tok))
    plain_right = report("2. plain Qwen + keyword scorer (no adapter), %.0fs" % (time.time() - t0), labels, bad)

    print("\nputting the adapter on top:", adapter)
    model = PeftModel.from_pretrained(model, adapter)
    model.eval()

    t0 = time.time()
    labels, bad = run_with_ai(make_gen(model, tok))
    adapter_right = report("3. Qwen + adapter + keyword scorer, %.0fs" % (time.time() - t0), labels, bad)

    print("\nsummary (right out of %d)" % len(H))
    print("  keyword only :", base_right)
    print("  plain Qwen   :", plain_right)
    print("  with adapter :", adapter_right)
    if adapter_right <= plain_right:
        print("  the adapter did not beat plain Qwen on this test")


if __name__ == "__main__":
    main()
