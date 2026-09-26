"""
Conservatism analysis: is the Guesser-strategy effect explained by HOW MANY words a
guesser commits to per turn, rather than how cleverly it reasons?

Motivation: 97-98% of all losses are assassin deaths (see analyze_project_overview.py).
Every extra guess in a turn is another draw against the assassin. So the hypothesis is
that win rate is governed by guesses-per-turn (an action-conservatism knob), not by
reasoning sophistication.

From the per-game timeline logs we compute, per guesser strategy:
  guesses/turn = (# guess events) / (# clue events)
and relate it to assassin-death rate and win rate.

Caveat: per-game logs carry no provider label, so OpenAI+Gemini are pooled.

Usage:
    python analyze_conservatism.py
"""

import os
import json
import glob
from collections import defaultdict

LOG_ROOT = os.path.join("results", "NoMockMode")
DIR_TO_LABEL = {
    "Default": "Default", "Cautious": "Cautious", "Risky": "Risky", "COT": "COT",
    "SelfRefine": "Self Refine", "SoloPerformance": "Solo Performance", "ThreeStep": "Three Step",
}
ORDER = ["Cautious", "Default", "COT", "Solo Performance", "Risky", "Self Refine", "Three Step"]


def guesser_of(dirname):
    try:
        return DIR_TO_LABEL.get(dirname.split("__G-")[1])
    except (IndexError, ValueError):
        return None


def game_stats(log):
    timeline = log.get("timeline", [])
    key_grid = log.get("key_grid", [])
    if not timeline or not key_grid:
        return None
    n_clues = sum(1 for e in timeline if e.get("type") == "clue")
    guesses = [e for e in timeline if e.get("type") == "guess"]
    if n_clues == 0:
        return None
    hit_assassin = any(str(e.get("role", "")).upper() == "ASSASSIN" for e in guesses)
    won = log.get("did_win", False)
    return len(guesses), n_clues, hit_assassin, won


def main():
    agg = defaultdict(lambda: {"games": 0, "guesses": 0, "turns": 0, "assassin": 0, "wins": 0})
    for path in glob.glob(os.path.join(LOG_ROOT, "*", "*.json")):
        g = guesser_of(os.path.basename(os.path.dirname(path)))
        if not g:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        st = game_stats(log)
        if st is None:
            continue
        n_guess, n_clue, hit, won = st
        d = agg[g]
        d["games"] += 1
        d["guesses"] += n_guess
        d["turns"] += n_clue
        d["assassin"] += 1 if hit else 0
        d["wins"] += 1 if won else 0

    print("=" * 82)
    print("CONSERVATISM: guesses-per-turn vs assassin-death and win rate (by Guesser)")
    print("=" * 82)
    print(f"{'Guesser':<18}{'games':>7}{'guesses/turn':>14}{'assassin%':>11}{'win%':>8}")
    print("-" * 58)
    series = []
    for g in ORDER:
        if g not in agg:
            continue
        d = agg[g]
        gpt = d["guesses"] / d["turns"] if d["turns"] else 0
        ar = 100 * d["assassin"] / d["games"] if d["games"] else 0
        wr = 100 * d["wins"] / d["games"] if d["games"] else 0
        series.append((gpt, ar, wr))
        print(f"{g:<18}{d['games']:>7}{gpt:>14.2f}{ar:>10.1f}%{wr:>7.1f}%")

    # simple Pearson correlations across strategies
    def pearson(xs, ys):
        n = len(xs)
        if n < 3:
            return float("nan")
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        vx = sum((x - mx) ** 2 for x in xs) ** 0.5
        vy = sum((y - my) ** 2 for y in ys) ** 0.5
        return cov / (vx * vy) if vx and vy else float("nan")

    gpts = [s[0] for s in series]
    ars = [s[1] for s in series]
    wrs = [s[2] for s in series]
    print("-" * 58)
    print(f"Across strategies:")
    print(f"  corr(guesses/turn, assassin%) = {pearson(gpts, ars):+.2f}")
    print(f"  corr(guesses/turn, win%)      = {pearson(gpts, wrs):+.2f}")
    print(f"  corr(assassin%,   win%)       = {pearson(ars, wrs):+.2f}")
    print("\nHypothesis: more guesses/turn -> more assassin deaths -> lower win rate.")
    print("A strong positive (guesses/turn, assassin%) and strong negative")
    print("(guesses/turn, win%) would show the guesser effect is largely about")
    print("action conservatism, not reasoning quality.")


if __name__ == "__main__":
    main()
