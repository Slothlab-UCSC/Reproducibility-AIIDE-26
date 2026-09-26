"""
Assassin-directionality analysis (paper Move #1).

Question: when an LLM Guesser loses to the assassin, is it just guessing badly,
or is it actively DRAWN to the assassin above what random guessing would produce?

Method (uses only the per-game timeline logs already on disk — no API calls):
  For every guess in every game, while the assassin is still unrevealed, a
  uniform-random guesser would hit it with probability 1 / (#unrevealed words).
  Summing that over all guesses gives the EXPECTED number of assassin hits under
  random play. We compare that to the ACTUAL number of assassin hits, per Guesser
  strategy. A ratio >> 1 means the strategy is systematically steering toward the
  assassin (a directional failure), not merely losing accuracy.

Caveat: per-game logs do not record the provider, so OpenAI and Gemini games are
pooled here. Treat as a first-pass internal result.

Usage:
    python analyze_assassin_directionality.py
"""

import os
import json
import glob
from collections import defaultdict

LOG_ROOT = os.path.join("results", "NoMockMode")

# reverse of event_log.STRATEGY_DIR
DIR_TO_LABEL = {
    "Default": "Default",
    "Cautious": "Cautious",
    "Risky": "Risky",
    "COT": "COT",
    "SelfRefine": "Self Refine",
    "SoloPerformance": "Solo Performance",
    "ThreeStep": "Three Step",
}


def parse_combo(dirname):
    """'CM-COT__G-SelfRefine' -> ('COT', 'Self Refine')."""
    try:
        cm_part, g_part = dirname.split("__G-")
        cm_dir = cm_part[len("CM-"):]
        g_dir = g_part
        return DIR_TO_LABEL.get(cm_dir, cm_dir), DIR_TO_LABEL.get(g_dir, g_dir)
    except ValueError:
        return None, None


def analyze_game(log):
    """Return per-game tallies or None.

    Returns dict with:
      actual_assassin       : assassin hits (0 or 1)
      expected_random_all   : expected hits under uniform-random over ALL words (Metric A)
      expected_random_err   : expected hits under uniform over unrevealed NON-RED words,
                              counted only on guesses that were actually errors (Metric B)
      n_errors              : number of error guesses (non-red picks)
      hit_assassin          : bool
    """
    timeline = log.get("timeline", [])
    key_grid = log.get("key_grid", [])
    if not timeline or not key_grid:
        return None

    # canonical original word order = first 'start' snapshot (aligns with key_grid)
    first_start = next((e for e in timeline if e.get("type") == "start"), None)
    if not first_start:
        return None
    words = first_start.get("board_snapshot", [])
    if len(words) != len(key_grid):
        return None

    norm = lambda w: str(w).replace("*", "").strip().upper()
    role_of = {norm(w): str(r).upper() for w, r in zip(words, key_grid)}
    try:
        assassin_idx = key_grid.index("Assassin")
    except ValueError:
        return None
    assassin_word = norm(words[assassin_idx])
    total_words = len(words)
    total_nonred = sum(1 for r in key_grid if str(r).upper() != "RED")

    revealed = set()
    revealed_nonred = 0
    expected_random_all = 0.0
    expected_random_err = 0.0
    actual_assassin = 0
    n_errors = 0
    hit_assassin = False

    for e in timeline:
        if e.get("type") != "guess":
            continue
        guess_word = norm(e.get("guess", ""))
        role = str(e.get("role", "")).upper()
        candidates_before = total_words - len(revealed)
        if candidates_before <= 0:
            break
        assassin_up = assassin_word not in revealed

        # Metric A: uniform over all remaining words
        if assassin_up:
            expected_random_all += 1.0 / candidates_before

        is_error = (role != "RED")  # any non-red pick ends the turn = a mistake
        if is_error:
            n_errors += 1
            # Metric B: among mistakes, expected chance of the assassin specifically
            if assassin_up:
                nonred_unrevealed = total_nonred - revealed_nonred
                if nonred_unrevealed > 0:
                    expected_random_err += 1.0 / nonred_unrevealed

        if role == "ASSASSIN" or guess_word == assassin_word:
            actual_assassin += 1
            hit_assassin = True

        revealed.add(guess_word)
        if role_of.get(guess_word, "") != "RED":
            revealed_nonred += 1

    return {
        "actual_assassin": actual_assassin,
        "expected_random_all": expected_random_all,
        "expected_random_err": expected_random_err,
        "n_errors": n_errors,
        "hit_assassin": hit_assassin,
    }


def main():
    by_guesser = defaultdict(lambda: {
        "games": 0, "actual": 0, "exp_all": 0.0, "exp_err": 0.0,
        "n_errors": 0, "assassin_games": 0,
    })

    pattern = os.path.join(LOG_ROOT, "*", "*.json")
    files = glob.glob(pattern)

    for path in files:
        combo_dir = os.path.basename(os.path.dirname(path))
        _, g_label = parse_combo(combo_dir)
        if g_label is None:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                log = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        res = analyze_game(log)
        if res is None:
            continue
        d = by_guesser[g_label]
        d["games"] += 1
        d["actual"] += res["actual_assassin"]
        d["exp_all"] += res["expected_random_all"]
        d["exp_err"] += res["expected_random_err"]
        d["n_errors"] += res["n_errors"]
        d["assassin_games"] += 1 if res["hit_assassin"] else 0

    order = ["Default", "Cautious", "Risky", "COT", "Self Refine", "Solo Performance", "Three Step"]

    print("=" * 96)
    print("ASSASSIN DIRECTIONALITY BY GUESSER STRATEGY  (pooled OpenAI+Gemini per-game logs)")
    print("=" * 96)

    # Metric A
    print("\n[Metric A] Assassin hits vs uniform-random over ALL remaining words")
    header = f"{'Guesser':<18}{'Games':>7}{'AssnRate':>10}{'Actual':>9}{'ExpRand':>10}{'Ratio':>9}"
    print(header); print("-" * len(header))
    for g in order:
        if g not in by_guesser:
            continue
        d = by_guesser[g]
        rate = 100 * d["assassin_games"] / d["games"] if d["games"] else 0
        ratio = d["actual"] / d["exp_all"] if d["exp_all"] > 0 else float("nan")
        print(f"{g:<18}{d['games']:>7}{rate:>9.1f}%{d['actual']:>9}{d['exp_all']:>10.1f}{ratio:>8.2f}x")

    # Metric B  (the cleaner, confound-controlled test)
    print("\n[Metric B] CONDITIONAL ON MAKING A MISTAKE: did the error land on the assassin")
    print("           more than if mistakes were spread uniformly over non-red words?")
    header = f"{'Guesser':<18}{'Errors':>8}{'AssnErr':>9}{'Actual%':>9}{'ExpUnif%':>10}{'Ratio':>9}"
    print(header); print("-" * len(header))
    for g in order:
        if g not in by_guesser:
            continue
        d = by_guesser[g]
        actual_share = 100 * d["actual"] / d["n_errors"] if d["n_errors"] else 0
        exp_share = 100 * d["exp_err"] / d["n_errors"] if d["n_errors"] else 0
        ratio = d["actual"] / d["exp_err"] if d["exp_err"] > 0 else float("nan")
        print(f"{g:<18}{d['n_errors']:>8}{d['actual']:>9}{actual_share:>8.1f}%{exp_share:>9.1f}%{ratio:>8.2f}x")

    print("\nMetric B reading: of all wrong guesses, what fraction hit the assassin (Actual%)")
    print("vs. what you'd expect if wrong guesses were uniform over non-red words (ExpUnif%).")
    print("Ratio >1 = when this strategy errs, it errs onto the assassin MORE than chance")
    print("-- i.e. a directional pull toward the assassin specifically, not generic bad play.")


if __name__ == "__main__":
    main()
