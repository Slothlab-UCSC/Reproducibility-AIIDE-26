"""
Role x Critique 2x2 (paper Move #1): does self-critique help the INFORMED agent and
hurt the UNINFORMED one -- same technique, opposite sign?

Both roles use the Self-Refine strategy; we toggle each role's critique step on/off:
  Codemaster critique : CM_CRITIQUE = on | off   (off ablates feedback+refine)
  Guesser    critique : SELF_REFINE_CRITIQUE = fixed (on) | none (off)

Four cells x seeds. Prediction:
  - Guesser critique OFF helps (G-off > G-on), regardless of CM  -> hurts the uninformed.
  - Codemaster critique ON helps (CM-on > CM-off), regardless of G -> helps the informed.

Output under results/2x2/ ; never touches the main dataset. Needs API keys.

Usage:
    python run_2x2_critique.py --provider openai --seeds 30
"""

import os
import json
import time
import argparse

from codenames.game import Game
from codenames.players.codemaster_gpt import AICodemaster
from codenames.players.guesser_gpt import AIGuesser
from codenames.event_log import StreamObserver
from run_experiments import FIXED_BOARD_SEEDS

OUT_DIR = os.path.join("results", "2x2")
SUMMARY_FILE = os.path.join(OUT_DIR, "summary.json")

# (cell-name, CM_CRITIQUE, SELF_REFINE_CRITIQUE)
CELLS = [
    ("cmON_gON",  "on",  "fixed"),
    ("cmON_gOFF", "on",  "none"),
    ("cmOFF_gON", "off", "fixed"),
    ("cmOFF_gOFF","off", "none"),
]


def load():
    try:
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(summary):
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = SUMMARY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUMMARY_FILE)


def run_one(provider, cm_crit, g_crit, seed):
    os.environ["LLM_PROVIDER"] = provider
    os.environ["CM_CRITIQUE"] = cm_crit
    os.environ["SELF_REFINE_CRITIQUE"] = g_crit
    os.environ.pop("MOCK_GPT", None)

    obs = StreamObserver()
    game = Game(
        AICodemaster, AIGuesser, seed=seed, do_print=False, do_log=False,
        game_name=f"2x2_{provider}",
        cm_kwargs={"strategy": "Self Refine"}, g_kwargs={"strategy": "Self Refine"},
        observer=obs,
    )
    t = time.time()
    game.run()
    red = game.words_on_board.count("*Red*")
    assassin = game.words_on_board.count("*Assassin*")
    return {"did_win": red == 8, "red": red, "assassin": assassin,
            "time_s": round(time.time() - t, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["openai", "gemini", "anthropic"], default="openai")
    ap.add_argument("--seeds", type=int, default=30)
    args = ap.parse_args()

    seeds = FIXED_BOARD_SEEDS[: args.seeds]
    summary = load()
    planned = len(CELLS) * len(seeds)
    print(f"2x2 critique study | planned {planned} games | done {len(summary)}")

    for cell, cm_crit, g_crit in CELLS:
        for seed in seeds:
            key = f"{args.provider}|{cell}|{seed}"
            if key in summary:
                continue
            try:
                res = run_one(args.provider, cm_crit, g_crit, seed)
                res.update({"provider": args.provider, "cell": cell,
                            "cm_critique": cm_crit, "g_critique": g_crit, "seed": seed})
                summary[key] = res
                save(summary)
                print(f"[{cell}] seed {int(seed)}: {'WIN' if res['did_win'] else 'LOSS'} "
                      f"assassin={res['assassin']} {res['time_s']}s")
            except Exception as e:
                summary[key] = {"error": str(e), "provider": args.provider, "cell": cell, "seed": seed}
                save(summary)
                print(f"[{cell}] seed {int(seed)} ERROR: {e}")

    # 2x2 table
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "wins": 0, "assn": 0})
    for v in summary.values():
        if isinstance(v, dict) and "did_win" in v:
            a = agg[v["cell"]]; a["n"] += 1; a["wins"] += v["did_win"]; a["assn"] += 1 if v["assassin"] else 0
    print("\n=== 2x2 RESULTS (win%) ===")
    print(f"{'':<14}{'G critique ON':>16}{'G critique OFF':>16}")
    for cm in ("ON", "OFF"):
        row = f"CM critique {cm:<3}"
        for g in ("ON", "OFF"):
            cell = f"cm{cm}_g{g}".replace("ON", "ON").replace("OFF", "OFF")
            cell = {"ONON": "cmON_gON", "ONOFF": "cmON_gOFF",
                    "OFFON": "cmOFF_gON", "OFFOFF": "cmOFF_gOFF"}[cm + g]
            a = agg.get(cell)
            row += f"{(100*a['wins']/a['n'] if a and a['n'] else 0):>14.0f}% " if a else f"{'--':>16}"
        print(row)


if __name__ == "__main__":
    main()
