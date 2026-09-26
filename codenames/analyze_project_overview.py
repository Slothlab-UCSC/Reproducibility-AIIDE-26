"""
Whole-project analysis of the 36-combo Codenames dataset (beyond the Self-Refine deep-dive).

Surfaces the project's main findings with statistics:
  1. Role dominance        - Guesser vs Codemaster marginal spread (with 95% CIs).
  2. Interaction / synergy  - actual cell win rate vs the additive prediction from the
                              two marginals (two-way decomposition). Finds CMxG pairings
                              that beat or underperform what the marginals alone predict.
  3. Loss-mode breakdown    - of all losses, how many are assassin vs blue-out/timeout.
  4. Cost-effectiveness     - win rate vs average game time per strategy.

Stats: Wilson 95% confidence intervals on win rates; a chi-square test of independence
on the best-vs-worst guesser strategies. Pure stdlib + the existing JSON. No API.

Usage:
    python analyze_project_overview.py
"""

import json
import os
import math
from collections import defaultdict

RESULTS_FILE = os.path.join("results", "experiment_results.json")
STRATEGIES = ["Default", "Cautious", "Risky", "COT", "Self Refine", "Solo Performance"]


def load():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        d = json.load(f)
    return [v for v in d.values() if isinstance(v, dict) and "did_win" in v]


def wilson(wins, n, z=1.96):
    """Wilson score 95% CI for a proportion; returns (low%, high%)."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (100 * (center - half), 100 * (center + half))


def chi_square_2x2(a, b, c, d):
    """2x2 chi-square (with totals), returns (chi2, dof=1). a,b / c,d are counts."""
    n = a + b + c + d
    if n == 0:
        return 0.0
    row1, row2 = a + b, c + d
    col1, col2 = a + c, b + d
    exp = [row1 * col1 / n, row1 * col2 / n, row2 * col1 / n, row2 * col2 / n]
    obs = [a, b, c, d]
    chi2 = sum((o - e) ** 2 / e for o, e in zip(obs, exp) if e > 0)
    return chi2


def marginals(games, role_key):
    out = {}
    for s in STRATEGIES:
        sub = [g for g in games if g.get(role_key) == s]
        if not sub:
            continue
        wins = sum(1 for g in sub if g["did_win"])
        lo, hi = wilson(wins, len(sub))
        out[s] = {"n": len(sub), "wins": wins, "wr": 100 * wins / len(sub), "lo": lo, "hi": hi}
    return out


def section_role_dominance(games):
    print("\n" + "=" * 78)
    print("1. ROLE DOMINANCE  (which role's strategy choice controls the outcome?)")
    print("=" * 78)
    for role_key, label in (("cm_strategy", "CODEMASTER"), ("g_strategy", "GUESSER")):
        m = marginals(games, role_key)
        if not m:
            continue
        wrs = {s: v["wr"] for s, v in m.items()}
        best, worst = max(wrs, key=wrs.get), min(wrs, key=wrs.get)
        spread = wrs[best] - wrs[worst]
        print(f"\n  {label} marginals (win% [95% CI], n):")
        for s in STRATEGIES:
            if s in m:
                v = m[s]
                print(f"    {s:<18} {v['wr']:>5.1f}%  [{v['lo']:>4.1f}, {v['hi']:>4.1f}]   n={v['n']}")
        print(f"    -> spread (best-worst): {spread:.1f} pts  ({best} vs {worst})")
        # chi-square best vs worst
        bw, bn = m[best]["wins"], m[best]["n"]
        ww, wn = m[worst]["wins"], m[worst]["n"]
        chi2 = chi_square_2x2(bw, bn - bw, ww, wn - ww)
        sig = "p<0.001" if chi2 > 10.83 else "p<0.01" if chi2 > 6.63 else "p<0.05" if chi2 > 3.84 else "n.s."
        print(f"    -> chi-square(best vs worst): {chi2:.1f}  ({sig})")


def section_interaction(games, provider):
    sub = [g for g in games if g.get("provider") == provider]
    if not sub:
        return
    grand = 100 * sum(g["did_win"] for g in sub) / len(sub)
    cm = marginals(sub, "cm_strategy")
    gm = marginals(sub, "g_strategy")
    cells = defaultdict(list)
    for g in sub:
        cells[(g["cm_strategy"], g["g_strategy"])].append(g["did_win"])
    rows = []
    for (c, gg), outs in cells.items():
        if c not in cm or gg not in gm or len(outs) < 5:
            continue
        actual = 100 * sum(outs) / len(outs)
        predicted = grand + (cm[c]["wr"] - grand) + (gm[gg]["wr"] - grand)
        rows.append((actual - predicted, c, gg, actual, predicted, len(outs)))
    rows.sort(reverse=True)
    print(f"\n  [{provider.upper()}] grand mean win rate = {grand:.1f}%")
    print(f"  Biggest POSITIVE interactions (pairing beats marginal prediction = synergy):")
    for d, c, gg, a, p, n in rows[:3]:
        print(f"    CM:{c:<16} G:{gg:<16} actual {a:>5.1f}% vs predicted {p:>5.1f}%  (+{d:>4.1f}) n={n}")
    print(f"  Biggest NEGATIVE interactions (pairing underperforms marginals = antagonism):")
    for d, c, gg, a, p, n in rows[-3:]:
        print(f"    CM:{c:<16} G:{gg:<16} actual {a:>5.1f}% vs predicted {p:>5.1f}%  ({d:>5.1f}) n={n}")


def section_loss_modes(games):
    print("\n" + "=" * 78)
    print("3. HOW TEAMS LOSE  (loss-mode breakdown)")
    print("=" * 78)
    by_provider = defaultdict(lambda: {"games": 0, "wins": 0, "assassin": 0, "other": 0})
    for g in games:
        d = by_provider[g.get("provider")]
        d["games"] += 1
        if g["did_win"]:
            d["wins"] += 1
        elif g.get("assassin", 0) > 0:
            d["assassin"] += 1
        else:
            d["other"] += 1
    for prov, d in by_provider.items():
        losses = d["games"] - d["wins"]
        if losses == 0:
            continue
        print(f"\n  {prov.upper()}: {losses} losses of {d['games']} games")
        print(f"    assassin deaths : {d['assassin']:>4}  ({100*d['assassin']/losses:.0f}% of losses)")
        print(f"    other (blue-out/timeout): {d['other']:>4}  ({100*d['other']/losses:.0f}% of losses)")


def section_cost(games, provider):
    sub = [g for g in games if g.get("provider") == provider]
    if not sub:
        return
    print(f"\n  [{provider.upper()}] cost-effectiveness by GUESSER strategy:")
    print(f"    {'strategy':<18}{'win%':>7}{'avg_time_s':>12}{'win per min':>13}")
    for s in STRATEGIES:
        gs = [g for g in sub if g.get("g_strategy") == s]
        if not gs:
            continue
        wr = 100 * sum(g["did_win"] for g in gs) / len(gs)
        t = sum(g.get("time_s", 0) for g in gs) / len(gs)
        wpm = (wr / t * 60) if t > 0 else 0
        print(f"    {s:<18}{wr:>6.1f}%{t:>11.1f}s{wpm:>12.1f}")


def main():
    games = load()
    print(f"WHOLE-PROJECT OVERVIEW  ({len(games)} valid games)")
    section_role_dominance(games)
    print("\n" + "=" * 78)
    print("2. INTERACTION / SYNERGY  (does a pairing beat its two marginals?)")
    print("=" * 78)
    for p in ("openai", "gemini"):
        section_interaction(games, p)
    section_loss_modes(games)
    print("\n" + "=" * 78)
    print("4. COST-EFFECTIVENESS")
    print("=" * 78)
    for p in ("openai", "gemini"):
        section_cost(games, p)


if __name__ == "__main__":
    main()
