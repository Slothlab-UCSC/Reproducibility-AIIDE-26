"""
Verifiability-flip analysis (paper standout angle).

Claim: a self-reflection / self-critique prompt helps an agent that CAN verify its own
output, and hurts an agent that CANNOT. Codenames gives a clean within-game test because
the SAME six strategies are applied to two roles with opposite information access:
  - Codemaster: sees the full key grid -> CAN verify its clue against ground truth.
  - Guesser:    sees only the clue      -> CANNOT verify (roles are hidden).

For each strategy we compute its marginal win rate as Codemaster vs as Guesser. If
verifiability governs the value of reflection, the reflective strategies (especially
Self-Refine) should sit near the top as Codemaster and near the bottom as Guesser --
a sign flip that a single-role study could never reveal.

Usage:
    python analyze_verifiability_flip.py
"""

import json
import os
from collections import defaultdict

RESULTS_FILE = os.path.join("results", "experiment_results.json")
STRATEGIES = ["Default", "Cautious", "Risky", "COT", "Self Refine", "Solo Performance"]
# strategies whose mechanism is "produce an answer, then reflect/critique/iterate"
REFLECTIVE = {"COT", "Self Refine", "Solo Performance"}


def load():
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        d = json.load(f)
    return [v for v in d.values() if isinstance(v, dict) and "did_win" in v]


def marginal(games, role_key, strat):
    sub = [g for g in games if g.get(role_key) == strat]
    if not sub:
        return None, 0
    wins = sum(1 for g in sub if g["did_win"])
    return 100 * wins / len(sub), len(sub)


def report(games, provider):
    sub = [g for g in games if g.get("provider") == provider]
    if not sub:
        return
    print(f"\n{'='*72}\nPROVIDER: {provider.upper()}   ({len(sub)} games)\n{'='*72}")
    print(f"{'Strategy':<18}{'as CODEMASTER':>16}{'as GUESSER':>14}{'FLIP (CM-G)':>14}")
    print(f"{'(reflective*)':<18}{'(can verify)':>16}{'(cannot)':>14}")
    print("-" * 62)
    rows = []
    for s in STRATEGIES:
        cm_wr, cm_n = marginal(sub, "cm_strategy", s)
        g_wr, g_n = marginal(sub, "g_strategy", s)
        if cm_wr is None or g_wr is None:
            continue
        flip = cm_wr - g_wr
        rows.append((s, cm_wr, g_wr, flip))
        star = "*" if s in REFLECTIVE else " "
        print(f"{s+star:<18}{cm_wr:>14.1f}% {g_wr:>12.1f}% {flip:>+12.1f}")

    # headline
    if rows:
        biggest = max(rows, key=lambda r: r[3])
        print("-" * 62)
        print(f"Largest positive flip: {biggest[0]} "
              f"(+{biggest[3]:.1f} pts better as Codemaster than as Guesser)")
        refl = [r for r in rows if r[0] in REFLECTIVE]
        nonrefl = [r for r in rows if r[0] not in REFLECTIVE]
        if refl and nonrefl:
            avg_refl = sum(r[3] for r in refl) / len(refl)
            avg_non = sum(r[3] for r in nonrefl) / len(nonrefl)
            print(f"Avg flip — reflective strategies: {avg_refl:+.1f} pts | "
                  f"non-reflective: {avg_non:+.1f} pts")


def main():
    games = load()
    print("VERIFIABILITY-FLIP ANALYSIS")
    print("Same strategy, two roles: does reflection help the agent that can verify\n"
          "and hurt the one that can't?  (* = reflective/self-critique strategy)")
    for provider in ("openai", "gemini"):
        report(games, provider)
    print("\nInterpretation: a large POSITIVE flip means the strategy is much better when")
    print("the agent can verify its own output (Codemaster) than when it cannot (Guesser).")
    print("Reflective strategies flipping positive while simple ones stay flat is the")
    print("signature of verifiability — not reflection itself — governing the payoff.")


if __name__ == "__main__":
    main()
