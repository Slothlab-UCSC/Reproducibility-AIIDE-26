"""
Buggy-vs-fixed critique A/B for the Self-Refine Guesser (paper Move #2 + causal test).

Why: aggregate logs show Self-Refine's high assassin rate is driven by error VOLUME
at chance directionality (see analyze_assassin_directionality.py), NOT by active
attraction to the assassin. The original "it picks the assassin on purpose" claim was
about the OLD negative-framing critique. This script runs both critique variants on the
SAME boards, with full prompt/response TRACES captured, so we can test directly:

  Does the buggy negative-framing critique cause (a) more assassin deaths, and
  (b) assassin-specific directional attraction (Metric B > 1), relative to the fix?

Traces are saved per game so the critique step can be mined later (run_id JSON includes
g_interactions). Output is written under results/ab_selfrefine/ and never touches the
main experiment dataset.

Usage (needs API keys; not run automatically):
    python run_selfrefine_ab.py --condition both --provider openai --codemasters Default COT --seeds 30
    python run_selfrefine_ab.py --condition buggy --provider openai --seeds 10
"""

import os
import sys
import json
import time
import argparse

from codenames.game import Game
from codenames.players.codemaster_gpt import AICodemaster
from codenames.players.guesser_gpt import AIGuesser
from codenames.event_log import StreamObserver
from run_experiments import FIXED_BOARD_SEEDS

OUT_DIR = os.path.join("results", "ab_selfrefine")
SUMMARY_FILE = os.path.join(OUT_DIR, "summary.json")


def load_summary():
    try:
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_summary(summary):
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = SUMMARY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUMMARY_FILE)


def save_game_log(log, condition, cm_strategy, seed):
    cond_dir = os.path.join(OUT_DIR, condition, f"CM-{cm_strategy}")
    os.makedirs(cond_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(log.started_at or time.time()))
    path = os.path.join(cond_dir, f"{ts}_{int(seed)}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(log.to_json())
    return path


def run_one(provider, condition, cm_strategy, seed):
    os.environ["LLM_PROVIDER"] = provider
    os.environ["SELF_REFINE_CRITIQUE"] = condition  # buggy | fixed | verifiable | none
    os.environ.pop("MOCK_GPT", None)

    observer = StreamObserver()
    game = Game(
        AICodemaster,
        AIGuesser,
        seed=seed,
        do_print=False,
        do_log=False,
        game_name=f"{provider}_{condition}_{cm_strategy}_SelfRefine",
        cm_kwargs={"strategy": cm_strategy},
        g_kwargs={"strategy": "Self Refine"},
        observer=observer,
    )
    start = time.time()
    game.run()
    elapsed = time.time() - start

    log_path = save_game_log(observer.log, condition, cm_strategy, seed)

    red = game.words_on_board.count("*Red*")
    assassin = game.words_on_board.count("*Assassin*")
    n_traces = len(getattr(observer.log, "g_interactions", []) or [])
    return {
        "provider": provider, "condition": condition, "cm_strategy": cm_strategy,
        "seed": seed, "did_win": red == 8, "red": red, "assassin": assassin,
        "time_s": round(elapsed, 1), "log_path": log_path, "g_traces": n_traces,
    }


def main():
    ap = argparse.ArgumentParser(description="Self-Refine buggy-vs-fixed critique A/B")
    ap.add_argument("--condition", choices=["buggy", "fixed", "verifiable", "none", "both", "all"],
                    default="both")
    ap.add_argument("--provider", choices=["openai", "gemini", "anthropic"], default="openai")
    ap.add_argument("--codemasters", nargs="+", default=["Default"])
    ap.add_argument("--seeds", type=int, default=30, help="number of fixed seeds to use")
    args = ap.parse_args()

    if args.condition == "both":
        conditions = ["buggy", "fixed"]
    elif args.condition == "all":
        conditions = ["buggy", "fixed", "verifiable", "none"]
    else:
        conditions = [args.condition]
    seeds = FIXED_BOARD_SEEDS[: args.seeds]
    summary = load_summary()

    planned = len(conditions) * len(args.codemasters) * len(seeds)
    print(f"Planned games: {planned} | already done: {len(summary)}")
    print("=" * 60)

    for condition in conditions:
        for cm in args.codemasters:
            for seed in seeds:
                key = f"{args.provider}|{condition}|{cm}|{seed}"
                if key in summary:
                    continue
                print(f"[{condition}] CM:{cm} seed:{int(seed)} ...", flush=True)
                try:
                    res = run_one(args.provider, condition, cm, seed)
                    summary[key] = res
                    save_summary(summary)
                    print(f"   {'WIN' if res['did_win'] else 'LOSS'} "
                          f"| assassin={res['assassin']} | traces={res['g_traces']} | {res['time_s']}s")
                except Exception as e:
                    print(f"   ERROR: {e}")
                    summary[key] = {"error": str(e), "provider": args.provider,
                                    "condition": condition, "cm_strategy": cm, "seed": seed}
                    save_summary(summary)

    # quick tally
    print("\n" + "=" * 60)
    for condition in conditions:
        games = [v for v in summary.values()
                 if isinstance(v, dict) and v.get("condition") == condition and "did_win" in v]
        if not games:
            continue
        n = len(games)
        wins = sum(1 for g in games if g["did_win"])
        assn = sum(1 for g in games if g.get("assassin", 0) > 0)
        print(f"{condition:>6}: {wins}/{n} wins ({100*wins/n:.0f}%) | "
              f"assassin deaths {assn}/{n} ({100*assn/n:.0f}%)")


if __name__ == "__main__":
    main()
