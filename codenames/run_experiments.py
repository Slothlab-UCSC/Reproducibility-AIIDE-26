"""
Run all 36 strategy combinations (6 CM x 6 Guesser) across 10 fixed boards
for both OpenAI (GPT-4o-mini) and Gemini (Flash Lite).

Usage:
    python run_experiments.py                  # run all (both providers)
    python run_experiments.py --provider openai # only OpenAI
    python run_experiments.py --provider gemini # only Gemini
"""

import os
import sys
import json
import time
import argparse
import traceback

from codenames.game import Game
from codenames.players.codemaster_gpt import AICodemaster
from codenames.players.guesser_gpt import AIGuesser
from codenames.event_log import StreamObserver, save_run

FIXED_BOARD_SEEDS = [
    # original 10
    1763425169.8379521,
    1763425590.8460038,
    1763425770.556834,
    1763425814.4200814,
    1763425859.4435585,
    1763425948.30537,
    1763426101.5985343,
    1763426133.7536027,
    1763426173.3689868,
    1763426236.519082,
    # additional 20 (total = 30)
    1763426637.7420592,
    1763426498.6548400,
    1763426748.5631933,
    1763426862.6448321,
    1763427231.0120463,
    1763427341.5147693,
    1763427575.8808055,
    1763427350.9224746,
    1763427639.0648189,
    1763427600.0087488,
    1763427822.3870888,
    1763428088.8098798,
    1763428010.7411864,
    1763428225.6769428,
    1763428566.0479970,
    1763428656.2236662,
    1763428647.5982800,
    1763428950.9695578,
    1763429187.4437056,
    1763428963.5244417,
]

STRATEGIES = ["Default", "Cautious", "Risky", "COT", "Self Refine", "Solo Performance"]

RESULTS_FILE = os.path.join("results", "experiment_results.json")
LOCK_FILE = RESULTS_FILE + ".lock"


def load_results():
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_results(results):
    os.makedirs("results", exist_ok=True)
    # Spinlock: exclusive .lock file prevents concurrent read-merge-write collisions.
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            break
        except FileExistsError:
            time.sleep(0.1)
    try:
        tmp = RESULTS_FILE + ".tmp"
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            on_disk = {}
        on_disk.update(results)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(on_disk, f, ensure_ascii=False, indent=2)
        for _ in range(10):
            try:
                os.replace(tmp, RESULTS_FILE)
                break
            except PermissionError:
                time.sleep(0.2)
    finally:
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass


def run_single_game(provider, cm_strategy, g_strategy, seed):
    """Run a single game and return result dict."""
    os.environ["LLM_PROVIDER"] = provider
    os.environ.pop("MOCK_GPT", None)

    observer = StreamObserver()
    mock_mode = os.getenv("MOCK_GPT") == "1"

    game = Game(
        AICodemaster,
        AIGuesser,
        seed=seed,
        do_print=False,
        do_log=True,
        game_name=f"{provider}_{cm_strategy}_{g_strategy}",
        cm_kwargs={"strategy": cm_strategy},
        g_kwargs={"strategy": g_strategy},
        observer=observer,
    )

    start = time.time()
    game.run()
    elapsed = time.time() - start

    # save rich game JSON via observer
    save_run(observer.log, mock_mode, cm_strategy, g_strategy)

    # count results from board state
    red = game.words_on_board.count("*Red*")
    blue = game.words_on_board.count("*Blue*")
    civ = game.words_on_board.count("*Civilian*")
    assassin = game.words_on_board.count("*Assassin*")

    did_win = (red == 8)

    return {
        "seed": seed,
        "provider": provider,
        "cm_strategy": cm_strategy,
        "g_strategy": g_strategy,
        "did_win": did_win,
        "red": red,
        "blue": blue,
        "civilian": civ,
        "assassin": assassin,
        "time_s": round(elapsed, 1),
    }


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except (ValueError, OSError, BrokenPipeError):
        pass


def make_key(provider, cm, g, seed):
    return f"{provider}|{cm}|{g}|{seed}"


def run_experiments(providers):
    results = load_results()
    total_combos = len(providers) * len(STRATEGIES) * len(STRATEGIES) * len(FIXED_BOARD_SEEDS)
    done = len(results)
    skipped = 0

    safe_print(f"Total experiments: {total_combos}")
    safe_print(f"Already completed: {done}")
    safe_print(f"Remaining: {total_combos - done}")
    safe_print("=" * 60)

    counter = 0
    for provider in providers:
        for cm_strategy in STRATEGIES:
            for g_strategy in STRATEGIES:
                for seed in FIXED_BOARD_SEEDS:
                    key = make_key(provider, cm_strategy, g_strategy, seed)
                    if key in results:
                        skipped += 1
                        continue

                    counter += 1
                    label = f"[{provider}] CM:{cm_strategy} / G:{g_strategy} / seed:{int(seed)}"
                    safe_print(f"\n--- Game {counter} | {label} ---")

                    try:
                        result = run_single_game(provider, cm_strategy, g_strategy, seed)
                        win_str = "WIN" if result["did_win"] else "LOSS"
                        safe_print(f"  Result: {win_str} | R:{result['red']} B:{result['blue']} C:{result['civilian']} A:{result['assassin']} | {result['time_s']}s")
                        results[key] = result
                        save_results(results)
                    except Exception as e:
                        safe_print(f"  ERROR: {e}")
                        try:
                            traceback.print_exc()
                        except (ValueError, OSError, BrokenPipeError):
                            pass
                        results[key] = {"error": str(e), "seed": seed, "provider": provider,
                                        "cm_strategy": cm_strategy, "g_strategy": g_strategy}
                        save_results(results)

    safe_print("\n" + "=" * 60)
    safe_print("EXPERIMENT COMPLETE")
    safe_print("=" * 60)

    for provider in providers:
        provider_results = [v for v in results.values() if isinstance(v, dict) and v.get("provider") == provider and "did_win" in v]
        if not provider_results:
            continue
        wins = sum(1 for r in provider_results if r["did_win"])
        total = len(provider_results)
        assassins = sum(r.get("assassin", 0) for r in provider_results)
        print(f"\n{provider.upper()}: {wins}/{total} wins ({100*wins/total:.1f}%) | {assassins} assassin hits")

        # per strategy combo
        combos = {}
        for r in provider_results:
            combo_key = f"CM:{r['cm_strategy']} / G:{r['g_strategy']}"
            combos.setdefault(combo_key, []).append(r)

        print(f"  {'Strategy Combo':<45} {'Wins':>5} {'Games':>6} {'Win%':>6} {'Assassins':>10}")
        for combo_key in sorted(combos.keys()):
            games = combos[combo_key]
            w = sum(1 for g in games if g["did_win"])
            a = sum(g.get("assassin", 0) for g in games)
            print(f"  {combo_key:<45} {w:>5} {len(games):>6} {100*w/len(games):>5.1f}% {a:>10}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Codenames experiments")
    parser.add_argument("--provider", choices=["openai", "gemini", "anthropic", "both"], default="both")
    args = parser.parse_args()

    if args.provider == "both":
        providers = ["openai", "gemini", "anthropic"]
    else:
        providers = [args.provider]

    run_experiments(providers)
