"""
Trace-miner for the Self-Refine critique step (paper Move #2 mechanism evidence).

Consumes the traced games produced by run_selfrefine_ab.py (results/ab_selfrefine/),
where each game JSON carries g_interactions = [{prompt, response, ...}, ...].

For every Self-Refine guess it pairs the INITIAL prompt ("Pick the most likely word")
with the following CRITIQUE prompt, extracts the board word chosen in each, and asks the
question the aggregate logs cannot answer:

  When the critique CHANGES the guess, what does it change it TO?
    - onto the ASSASSIN  (the catastrophic switch the bug story claims)
    - RED -> non-RED     (harmful: abandoned a correct pick)
    - non-RED -> RED     (helpful: the critique's intended purpose)
    - non-RED -> non-RED  (lateral)

Comparing the buggy vs fixed condition on "switched onto the assassin" is the direct
test of the directional-attraction claim.

Usage:
    python analyze_selfrefine_traces.py
"""

import os
import re
import json
import glob
from collections import defaultdict

AB_ROOT = os.path.join("results", "ab_selfrefine")

INITIAL_SIG = "pick the most likely word"
CRITIQUE_SIGS = ("could accidentally be", "most confident", "more strongly associated")  # buggy / fixed / verifiable


def norm(w):
    return str(w).replace("*", "").strip().upper()


def extract_word(response, board_words):
    """Return the board word the response refers to, or None."""
    if not isinstance(response, str):
        return None
    up = response.strip().upper()
    board_set = set(board_words)
    # exact
    if up in board_set:
        return up
    # quoted
    for q in ('"', "'"):
        parts = up.split(q)
        if len(parts) > 2 and parts[1] in board_set:
            return parts[1]
    # any board word appearing as a whole token in the response
    tokens = set(re.findall(r"[A-Z]+", up))
    hits = [w for w in board_words if w in tokens]
    if len(hits) == 1:
        return hits[0]
    # first board word by position in the text
    best, best_pos = None, len(up) + 1
    for w in board_words:
        p = up.find(w)
        if p != -1 and p < best_pos:
            best, best_pos = w, p
    return best


def board_from_log(log):
    timeline = log.get("timeline", [])
    key_grid = log.get("key_grid", [])
    first_start = next((e for e in timeline if e.get("type") == "start"), None)
    if not first_start or not key_grid:
        return None, None, None
    words = [norm(w) for w in first_start.get("board_snapshot", [])]
    if len(words) != len(key_grid):
        return None, None, None
    role_of = {w: str(r).upper() for w, r in zip(words, key_grid)}
    assassin = next((w for w, r in role_of.items() if r == "ASSASSIN"), None)
    return words, role_of, assassin


def mine_game(log, stats):
    words, role_of, assassin = board_from_log(log)
    if words is None:
        return
    interactions = log.get("g_interactions", []) or []

    i = 0
    while i < len(interactions):
        prompt = str(interactions[i].get("prompt", "")).lower()
        if INITIAL_SIG in prompt:
            initial_resp = interactions[i].get("response", "")
            # find the next critique prompt
            j = i + 1
            crit_idx = None
            while j < len(interactions) and j <= i + 2:
                p2 = str(interactions[j].get("prompt", "")).lower()
                if any(sig in p2 for sig in CRITIQUE_SIGS):
                    crit_idx = j
                    break
                j += 1
            if crit_idx is not None:
                final_resp = interactions[crit_idx].get("response", "")
                init_w = extract_word(initial_resp, words)
                final_w = extract_word(final_resp, words)
                stats["pairs"] += 1
                if init_w and final_w:
                    stats["parsed"] += 1
                    if init_w != final_w:
                        stats["changed"] += 1
                        ir = role_of.get(init_w, "?")
                        fr = role_of.get(final_w, "?")
                        if final_w == assassin:
                            stats["switch_to_assassin"] += 1
                        if ir == "RED" and fr != "RED":
                            stats["red_to_nonred"] += 1
                        elif ir != "RED" and fr == "RED":
                            stats["nonred_to_red"] += 1
                        elif ir != "RED" and fr != "RED":
                            stats["nonred_to_nonred"] += 1
                    else:
                        stats["kept"] += 1
                i = crit_idx + 1
                continue
        i += 1


def main():
    if not os.path.isdir(AB_ROOT):
        print(f"No data yet at {AB_ROOT}. Run run_selfrefine_ab.py first.")
        return

    by_cond = defaultdict(lambda: defaultdict(int))
    for cond in ("buggy", "fixed", "verifiable", "none"):
        for path in glob.glob(os.path.join(AB_ROOT, cond, "*", "*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            mine_game(log, by_cond[cond])

    print("=" * 78)
    print("SELF-REFINE CRITIQUE TRACE ANALYSIS  (what the critique changes the guess TO)")
    print("=" * 78)
    for cond in ("buggy", "fixed", "verifiable", "none"):
        s = by_cond.get(cond)
        if not s or s["pairs"] == 0:
            print(f"\n[{cond}] no traced critique pairs found.")
            continue
        changed = s["changed"]
        print(f"\n[{cond}]  critique pairs={s['pairs']}  parsed={s['parsed']}  "
              f"changed={changed} ({100*changed/max(s['parsed'],1):.0f}% of parsed)")
        if changed:
            print(f"    -> switched ONTO ASSASSIN : {s['switch_to_assassin']} "
                  f"({100*s['switch_to_assassin']/changed:.0f}% of changes)")
            print(f"    -> RED  -> non-RED  (harmful): {s['red_to_nonred']} "
                  f"({100*s['red_to_nonred']/changed:.0f}%)")
            print(f"    -> non-RED -> RED   (helpful): {s['nonred_to_red']} "
                  f"({100*s['nonred_to_red']/changed:.0f}%)")
            print(f"    -> non-RED -> non-RED (lateral): {s['nonred_to_nonred']} "
                  f"({100*s['nonred_to_nonred']/changed:.0f}%)")

    print("\nKey comparison: 'switched ONTO ASSASSIN' rate, buggy vs fixed. If the buggy")
    print("critique drives directional attraction, it should switch onto the assassin")
    print("markedly more often than the fixed critique does.")


if __name__ == "__main__":
    main()
