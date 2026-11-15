# does our model beat a simple baseline?
# a baseline is the dumbest guess that still makes sense, like always saying the most common answer
# we print the baseline score right next to the model score so you can see what the model really adds
#
# run it:  python baseline.py
# faster:  python baseline.py --quick

import os, sys, math, random
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
from services import predict as P
from headlines import H

NAMES = {"positive": "good", "negative": "bad", "neutral": "neutral"}


def wilson(k, n, z=1.96):
    # a range for what the real score could be
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def show(name, right, n):
    lo, hi = wilson(right, n)
    print("  %-44s %2d of %d  %5.1f%%  (range %.0f to %.0f%%)" % (name, right, n, right / n * 100, lo * 100, hi * 100))


# part 1: reading headlines
# baseline 1: always say the biggest group
# baseline 2: the plain keyword scorer, no context rules
# model: keyword scorer plus the context rules (what the app uses without the AI)
def part_headlines():
    print("headline test (%d headlines we wrote and labeled)" % len(H))
    counts = Counter(truth for _, truth in H)
    # two groups tie at 20, so we pick "good"
    biggest = "good"
    print("  group sizes:", dict(counts))

    base1 = sum(1 for _, truth in H if truth == biggest)

    base2 = 0
    for t, truth in H:
        if NAMES[P.label_for(P._lexicon_score(t))] == truth:
            base2 += 1

    model = 0
    for t, truth in H:
        s, ok, _ = P.judge(t, P._lexicon_score(t))
        guess = NAMES[P.label_for(s)] if ok else "irrelevant"
        if guess == truth:
            model += 1

    show("baseline 1: always say '%s'" % biggest, base1, len(H))
    show("baseline 2: keywords only, no rules", base2, len(H))
    show("model: keywords + context rules", model, len(H))
    print("  model beats the dumbest guess by %.1f points" % ((model - base1) / len(H) * 100))
    print("  rules add %.1f points on top of keywords alone" % ((model - base2) / len(H) * 100))
    print("  (the AI adapter is tested separately in run5_adapter.py)")
    return base1, base2, model


# part 2: the forecast line on fake stocks
# baseline: "no change", the price just stays where it is
# model: the real forecast function
# we measure how far off the end price was, smaller is better
def fake_points(rets):
    p, t = 100.0, 1_700_000_000_000
    pts = [{"t": t, "c": p}]
    for r in rets:
        p *= math.exp(r)
        t += 86400_000
        pts.append({"t": t, "c": p})
    return pts


def part_forecast(trials):
    print()
    print("forecast test (%d fake stocks per row, 30 days ahead)" % trials)
    print("  %-34s %12s %12s %10s" % ("scenario", "baseline miss", "model miss", "direction"))
    scenarios = [("normal moves, no news", 0.0, False),
                 ("calm, then 2.5x jumpier", 0.0, True),
                 ("strong good news (just noise)", 0.8, False)]
    for name, sent, shock in scenarios:
        base_err, model_err, dir_right = 0.0, 0.0, 0
        for seed in range(trials):
            rng = random.Random(seed)
            hist = [rng.gauss(0, 0.02) for _ in range(250)]
            fut = [rng.gauss(0, 0.02 * (2.5 if shock else 1.0)) for _ in range(30)]
            pts = fake_points(hist)
            f = P.forecast(pts, sent, 30)
            last = pts[-1]["c"]
            real = last * math.exp(sum(fut))
            base_err += abs(real / last - 1)
            model_err += abs(f[-1]["c"] / last - real / last)
            dir_right += (f[-1]["c"] > last) == (real > last)
        print("  %-34s %11.2f%% %11.2f%% %9.1f%%" % (name, base_err / trials * 100, model_err / trials * 100, dir_right / trials * 100))
    print("  baseline has no direction, so a coin flip (50%) is what to compare against")


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    part_headlines()
    part_forecast(200 if quick else 1000)
