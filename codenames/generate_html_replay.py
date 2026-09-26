"""
Generate standalone HTML replay files from game JSON logs.

Usage:
    python generate_html_replay.py path/to/game.json          # single file
    python generate_html_replay.py results/NoMockMode/         # all JSONs in dir (recursive)
    python generate_html_replay.py --all                       # all game JSONs under results/
"""

import os
import sys
import json
import argparse
from pathlib import Path

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Codenames Replay — Seed {{SEED}}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f0f2f5; color: #222; padding: 20px; }
  .header { text-align: center; margin-bottom: 20px; }
  .header h1 { font-size: 1.4em; color: #333; }
  .header .meta { color: #666; font-size: 0.9em; margin-top: 4px; }
  .result { font-size: 1.1em; font-weight: 700; margin: 8px 0; }
  .result.win { color: #2e7d32; }
  .result.loss { color: #c62828; }
  .board { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; max-width: 700px; margin: 0 auto 20px; }
  .tile {
    border: 2px solid #ddd; background: #fafafa; border-radius: 10px;
    padding: 14px 6px; text-align: center; font-weight: 600;
    font-size: 0.85em; letter-spacing: 0.3px; transition: all 0.3s;
    min-height: 52px; display: flex; align-items: center; justify-content: center;
  }
  .tile.RED { background: #ffebee; border-color: #e53935; }
  .tile.BLUE { background: #e8f0ff; border-color: #1e88e5; }
  .tile.CIVILIAN { background: #f5f5f5; border-color: #9e9e9e; }
  .tile.ASSASSIN { background: #fff3e0; border-color: #fb8c00; }
  .tile.revealed { opacity: 0.7; }
  .tile.just-guessed { box-shadow: 0 0 0 3px #333; }
  .controls { text-align: center; margin: 16px 0; }
  .controls button {
    background: #1976d2; color: #fff; border: none; border-radius: 6px;
    padding: 8px 20px; margin: 0 6px; cursor: pointer; font-size: 0.95em;
  }
  .controls button:hover { background: #1565c0; }
  .controls button:disabled { background: #bbb; cursor: default; }
  .controls label { margin-left: 16px; font-size: 0.9em; cursor: pointer; }
  .event-log { max-width: 700px; margin: 0 auto; }
  .event { padding: 8px 12px; margin: 4px 0; border-radius: 6px; font-size: 0.9em; }
  .event.clue { background: #e3f2fd; border-left: 4px solid #1976d2; }
  .event.guess-correct { background: #e8f5e9; border-left: 4px solid #43a047; }
  .event.guess-wrong { background: #fce4ec; border-left: 4px solid #e53935; }
  .event.active { box-shadow: 0 0 0 2px #333; }
  .step-counter { font-size: 0.85em; color: #666; text-align: center; margin: 6px 0; }
</style>
</head>
<body>
<div class="header">
  <h1>Codenames AI Replay</h1>
  <div class="meta">Seed: {{SEED}} | Strategy: {{STRATEGY}}</div>
  <div class="result {{RESULT_CLASS}}">{{RESULT_TEXT}}</div>
</div>

<div class="board" id="board"></div>

<div class="controls">
  <button id="prevBtn" onclick="prev()">Prev</button>
  <button id="nextBtn" onclick="next()">Next</button>
  <button onclick="goTo(0)">Reset</button>
  <button onclick="goTo(events.length)">End</button>
  <label><input type="checkbox" id="revealToggle" onchange="render()"> Reveal roles</label>
</div>
<div class="step-counter" id="stepCounter"></div>

<div class="event-log" id="eventLog"></div>

<script>
const gameData = {{GAME_JSON}};
const board = gameData.board || [];
const keyGrid = gameData.key_grid || [];
const timeline = gameData.timeline || [];

// Build event list (skip the "start" event for stepping)
const events = timeline.filter(e => e.type !== "start");
let currentStep = 0;

function getSnapshot(stepIndex) {
  // Build board state by replaying events up to stepIndex
  let state = board.map(w => w.replace(/\*/g, ''));
  let revealed = new Array(25).fill(false);
  let justGuessed = -1;

  let count = 0;
  for (const evt of timeline) {
    if (evt.type === "start") continue;
    if (count > stepIndex) break;
    if (evt.type === "guess" && evt.board_snapshot) {
      for (let i = 0; i < 25; i++) {
        if (evt.board_snapshot[i] && evt.board_snapshot[i].startsWith("*")) {
          revealed[i] = true;
        }
      }
      // Find the guessed tile
      justGuessed = -1;
      const g = (evt.guess || "").toUpperCase();
      for (let i = 0; i < 25; i++) {
        if (state[i].toUpperCase() === g) { justGuessed = i; break; }
      }
    }
    if (count === stepIndex && evt.type !== "guess") {
      justGuessed = -1;
    }
    count++;
  }
  return { state, revealed, justGuessed };
}

function render() {
  const reveal = document.getElementById("revealToggle").checked;
  const { state, revealed, justGuessed } = getSnapshot(currentStep - 1);
  const boardEl = document.getElementById("board");
  boardEl.innerHTML = "";

  for (let i = 0; i < 25; i++) {
    const div = document.createElement("div");
    div.className = "tile";
    const role = (keyGrid[i] || "").toUpperCase();

    if (revealed[i]) {
      div.classList.add(role, "revealed");
      div.textContent = reveal ? `${role}` : "?";
    } else {
      if (reveal) div.classList.add(role);
      div.textContent = state[i];
    }
    if (i === justGuessed) div.classList.add("just-guessed");
    boardEl.appendChild(div);
  }

  // Step counter
  document.getElementById("stepCounter").textContent =
    `Step ${currentStep} / ${events.length}`;

  // Event log
  const logEl = document.getElementById("eventLog");
  logEl.innerHTML = "";
  let evtIdx = 0;
  for (const evt of events) {
    const div = document.createElement("div");
    div.className = "event";
    if (evt.type === "clue") {
      div.classList.add("clue");
      div.textContent = `Turn ${evt.turn} — Clue: "${evt.clue}" for ${evt.num}`;
    } else if (evt.type === "guess") {
      div.classList.add(evt.correct ? "guess-correct" : "guess-wrong");
      const icon = evt.correct ? "\u2705" : "\u274c";
      div.textContent = `${icon} Guess: ${evt.guess} (${evt.role})`;
    }
    if (evtIdx === currentStep - 1) div.classList.add("active");
    evtIdx++;
    logEl.appendChild(div);
  }

  document.getElementById("prevBtn").disabled = currentStep <= 0;
  document.getElementById("nextBtn").disabled = currentStep >= events.length;
}

function next() {
  if (currentStep < events.length) { currentStep++; render(); }
}
function prev() {
  if (currentStep > 0) { currentStep--; render(); }
}
function goTo(step) {
  currentStep = Math.max(0, Math.min(events.length, step));
  render();
}

// Keyboard navigation
document.addEventListener("keydown", e => {
  if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); next(); }
  if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
});

render();
</script>
</body>
</html>"""


def generate_replay(json_path: str, output_dir: str = None):
    """Generate an HTML replay from a game JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    seed = data.get("seed", "?")
    strategy = data.get("strategy", "")
    did_win = data.get("did_win", False)

    result_class = "win" if did_win else "loss"
    result_text = "WIN" if did_win else "LOSS"

    html = HTML_TEMPLATE
    html = html.replace("{{SEED}}", str(seed))
    html = html.replace("{{STRATEGY}}", strategy or "N/A")
    html = html.replace("{{RESULT_CLASS}}", result_class)
    html = html.replace("{{RESULT_TEXT}}", result_text)
    html = html.replace("{{GAME_JSON}}", json.dumps(data, ensure_ascii=False))

    if output_dir is None:
        # Mirror the source structure under results/replays/
        rel = os.path.relpath(os.path.dirname(json_path), "results")
        output_dir = os.path.join("results", "replays", rel)

    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(json_path))[0] + ".html"
    out_path = os.path.join(output_dir, base)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def find_game_jsons(root: str):
    """Find all game JSON files under root."""
    jsons = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".json") and not fn.startswith("tech_stats") and fn != "experiment_results.json":
                jsons.append(os.path.join(dirpath, fn))
    return sorted(jsons)


def main():
    parser = argparse.ArgumentParser(description="Generate HTML replay from game JSONs")
    parser.add_argument("path", nargs="?", default=None, help="Game JSON file or directory")
    parser.add_argument("--all", action="store_true", help="Process all game JSONs under results/")
    args = parser.parse_args()

    if args.all:
        target = "results"
    elif args.path:
        target = args.path
    else:
        parser.print_help()
        return

    if os.path.isfile(target):
        out = generate_replay(target)
        print(f"Generated: {out}")
    elif os.path.isdir(target):
        jsons = find_game_jsons(target)
        if not jsons:
            print(f"No game JSON files found in {target}")
            return
        print(f"Found {len(jsons)} game JSON files")
        for jp in jsons:
            try:
                out = generate_replay(jp)
                print(f"  {out}")
            except Exception as e:
                print(f"  ERROR: {jp}: {e}")
    else:
        print(f"Path not found: {target}")
        sys.exit(1)


if __name__ == "__main__":
    main()
