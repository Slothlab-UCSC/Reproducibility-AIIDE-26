"""
Extract structured datasets from game JSON logs for Codemaster and Guesser roles.

Produces:
    results/dataset_codemaster.csv   — one row per clue given
    results/dataset_guesser.csv      — one row per guess made
    results/dataset_codemaster.jsonl  — same data, richer format
    results/dataset_guesser.jsonl     — same data, richer format

Usage:
    python build_dataset.py                          # all game JSONs under results/
    python build_dataset.py results/NoMockMode/      # specific directory
    python build_dataset.py --skip-mock              # skip MockMode games
"""

import os
import csv
import json
import argparse
from pathlib import Path


def find_game_jsons(root: str, skip_mock: bool = False):
    jsons = []
    for dirpath, _, filenames in os.walk(root):
        if skip_mock and "MockMode" in dirpath and "NoMockMode" not in dirpath:
            continue
        for fn in filenames:
            if fn.endswith(".json") and fn != "experiment_results.json" and not fn.startswith("tech_stats"):
                jsons.append(os.path.join(dirpath, fn))
    return sorted(jsons)


def infer_strategy_from_path(json_path: str):
    """Try to extract CM and G strategy from the directory path."""
    parts = json_path.replace("\\", "/")
    cm_strategy = ""
    g_strategy = ""
    # Look for CM-Xxx__G-Yyy pattern
    for segment in parts.split("/"):
        if segment.startswith("CM-") and "__G-" in segment:
            cm_part, g_part = segment.split("__G-")
            cm_strategy = cm_part.replace("CM-", "")
            g_strategy = g_part
            break
    return cm_strategy, g_strategy


def compute_remaining(board_snapshot, key_grid):
    """Count remaining words per role from a board snapshot."""
    red = blue = civ = assn = 0
    for i, cell in enumerate(board_snapshot):
        if cell.startswith("*"):
            continue
        role = key_grid[i] if i < len(key_grid) else ""
        if role == "Red":
            red += 1
        elif role == "Blue":
            blue += 1
        elif role == "Civilian":
            civ += 1
        elif role == "Assassin":
            assn += 1
    return red, blue, civ, assn


def extract_from_game(json_path: str):
    """Extract codemaster and guesser rows from a single game JSON."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    timeline = data.get("timeline", [])
    key_grid = data.get("key_grid", [])
    seed = data.get("seed", "")
    did_win = data.get("did_win", False)
    cm_interactions = data.get("cm_interactions", [])
    g_interactions = data.get("g_interactions", [])
    cm_strategy, g_strategy = infer_strategy_from_path(json_path)

    cm_rows = []
    g_rows = []

    # Walk timeline to build per-clue and per-guess rows
    current_clue = None
    current_clue_num = 0
    current_turn = 0
    guess_position = 0
    current_board_snapshot = data.get("board", [])
    clue_guesses = []

    cm_interaction_idx = 0
    g_interaction_idx = 0

    for event in timeline:
        if event["type"] == "start":
            current_board_snapshot = event.get("board_snapshot", current_board_snapshot)
            continue

        if event["type"] == "clue":
            # If there was a previous clue, finalize the CM row
            if current_clue is not None:
                correct_guesses = sum(1 for g in clue_guesses if g.get("correct"))
                hit_assassin = any(g.get("role", "").upper() in ("ASSASSIN", "*ASSASSIN*") for g in clue_guesses)
                red_rem, blue_rem, civ_rem, assn_rem = compute_remaining(current_board_snapshot, key_grid)

                if correct_guesses >= current_clue_num:
                    label_coverage = "full"
                elif correct_guesses > 0:
                    label_coverage = "partial"
                else:
                    label_coverage = "none"

                if hit_assassin:
                    label_risk = "assassin"
                elif len(clue_guesses) > correct_guesses:
                    label_risk = "risky"
                else:
                    label_risk = "safe"

                cm_row = {
                    "seed": seed,
                    "turn": current_turn,
                    "cm_strategy": cm_strategy,
                    "g_strategy": g_strategy,
                    "clue_word": current_clue,
                    "clue_num": current_clue_num,
                    "total_guesses": len(clue_guesses),
                    "correct_guesses": correct_guesses,
                    "hit_assassin": hit_assassin,
                    "red_remaining": red_rem,
                    "blue_remaining": blue_rem,
                    "civilian_remaining": civ_rem,
                    "did_win": did_win,
                    "label_coverage": label_coverage,
                    "label_risk": label_risk,
                }
                cm_rows.append(cm_row)

            current_clue = event["clue"]
            current_clue_num = event["num"]
            current_turn = event["turn"]
            guess_position = 0
            clue_guesses = []

        elif event["type"] == "guess":
            guess_position += 1
            guess_data = {
                "guess": event.get("guess", ""),
                "role": event.get("role", ""),
                "correct": event.get("correct", False),
            }
            clue_guesses.append(guess_data)

            # Update board snapshot if available
            if event.get("board_snapshot"):
                current_board_snapshot = event["board_snapshot"]

            # Find corresponding interaction log entry
            g_prompt = ""
            g_response = ""
            if g_interaction_idx < len(g_interactions):
                g_prompt = g_interactions[g_interaction_idx].get("prompt", "")
                g_response = g_interactions[g_interaction_idx].get("response", "")
                g_interaction_idx += 1

            guess_role_raw = event.get("role", "").upper().replace("*", "")
            was_correct = event.get("correct", False)
            if was_correct:
                label_quality = "correct"
            elif guess_role_raw == "ASSASSIN":
                label_quality = "assassin"
            elif guess_role_raw == "BLUE":
                label_quality = "wrong_team"
            elif guess_role_raw == "CIVILIAN":
                label_quality = "civilian"
            else:
                label_quality = "unknown"

            g_row = {
                "seed": seed,
                "turn": current_turn,
                "cm_strategy": cm_strategy,
                "g_strategy": g_strategy,
                "clue_word": current_clue or "",
                "clue_num": current_clue_num,
                "guess_position": guess_position,
                "guess_word": event.get("guess", ""),
                "guess_role": event.get("role", ""),
                "was_correct": was_correct,
                "did_win": did_win,
                "prompt_text": g_prompt,
                "response_text": g_response,
                "label_quality": label_quality,
            }
            g_rows.append(g_row)

    # Finalize last clue's CM row
    if current_clue is not None:
        correct_guesses = sum(1 for g in clue_guesses if g.get("correct"))
        hit_assassin = any(g.get("role", "").upper() in ("ASSASSIN", "*ASSASSIN*") for g in clue_guesses)
        red_rem, blue_rem, civ_rem, assn_rem = compute_remaining(current_board_snapshot, key_grid)

        if correct_guesses >= current_clue_num:
            label_coverage = "full"
        elif correct_guesses > 0:
            label_coverage = "partial"
        else:
            label_coverage = "none"

        if hit_assassin:
            label_risk = "assassin"
        elif len(clue_guesses) > correct_guesses:
            label_risk = "risky"
        else:
            label_risk = "safe"

        cm_row = {
            "seed": seed,
            "turn": current_turn,
            "cm_strategy": cm_strategy,
            "g_strategy": g_strategy,
            "clue_word": current_clue,
            "clue_num": current_clue_num,
            "total_guesses": len(clue_guesses),
            "correct_guesses": correct_guesses,
            "hit_assassin": hit_assassin,
            "red_remaining": red_rem,
            "blue_remaining": blue_rem,
            "civilian_remaining": civ_rem,
            "did_win": did_win,
            "label_coverage": label_coverage,
            "label_risk": label_risk,
        }
        cm_rows.append(cm_row)

    return cm_rows, g_rows


def write_csv(rows, path, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


CM_FIELDS = [
    "seed", "turn", "cm_strategy", "g_strategy",
    "clue_word", "clue_num", "total_guesses", "correct_guesses",
    "hit_assassin", "red_remaining", "blue_remaining", "civilian_remaining",
    "did_win", "label_coverage", "label_risk",
]

G_FIELDS = [
    "seed", "turn", "cm_strategy", "g_strategy",
    "clue_word", "clue_num", "guess_position",
    "guess_word", "guess_role", "was_correct",
    "did_win", "prompt_text", "response_text", "label_quality",
]


def main():
    parser = argparse.ArgumentParser(description="Build datasets from game JSONs")
    parser.add_argument("path", nargs="?", default="results", help="Root directory to scan")
    parser.add_argument("--skip-mock", action="store_true", help="Skip MockMode games")
    args = parser.parse_args()

    jsons = find_game_jsons(args.path, skip_mock=args.skip_mock)
    print(f"Found {len(jsons)} game JSON files")

    all_cm_rows = []
    all_g_rows = []

    for jp in jsons:
        try:
            cm_rows, g_rows = extract_from_game(jp)
            all_cm_rows.extend(cm_rows)
            all_g_rows.extend(g_rows)
        except Exception as e:
            print(f"  ERROR processing {jp}: {e}")

    print(f"Codemaster rows: {len(all_cm_rows)}")
    print(f"Guesser rows: {len(all_g_rows)}")

    write_csv(all_cm_rows, os.path.join("results", "dataset_codemaster.csv"), CM_FIELDS)
    write_jsonl(all_cm_rows, os.path.join("results", "dataset_codemaster.jsonl"))
    write_csv(all_g_rows, os.path.join("results", "dataset_guesser.csv"), G_FIELDS)
    write_jsonl(all_g_rows, os.path.join("results", "dataset_guesser.jsonl"))

    print(f"\nSaved:")
    print(f"  results/dataset_codemaster.csv  ({len(all_cm_rows)} rows)")
    print(f"  results/dataset_guesser.csv     ({len(all_g_rows)} rows)")
    print(f"  results/dataset_codemaster.jsonl")
    print(f"  results/dataset_guesser.jsonl")


if __name__ == "__main__":
    main()
