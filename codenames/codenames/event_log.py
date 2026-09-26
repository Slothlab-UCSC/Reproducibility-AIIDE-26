"""
EventLog, StreamObserver, and persistence helpers.

Extracted from ui_app.py so that non-Streamlit scripts (run_experiments.py,
build_dataset.py, etc.) can use them without importing streamlit.
"""

import os
import json
import time
from dataclasses import dataclass, asdict, field


# ---- constants ----

ROLE_COLORS = {
    "RED":      ("#ffebee", "#e53935"),
    "BLUE":     ("#e8f0ff", "#1e88e5"),
    "CIVILIAN": ("#f5f5f5", "#9e9e9e"),
    "NEUTRAL":  ("#f5f5f5", "#9e9e9e"),
    "ASSASSIN": ("#fff3e0", "#fb8c00"),
}
MARKER_WORDS = {"RED", "BLUE", "CIVILIAN", "NEUTRAL", "ASSASSIN"}

STRATEGY_LABELS = ["Default", "Cautious", "Risky", "COT", "Self Refine", "Solo Performance", "Three Step"]
STRATEGY_DIR = {
    "Default": "Default",
    "Cautious": "Cautious",
    "Risky": "Risky",
    "COT": "COT",
    "Self Refine": "SelfRefine",
    "Solo Performance": "SoloPerformance",
    "Three Step": "ThreeStep",
}


# ---- small helpers ----

def clean_token(t: str) -> str:
    return str(t).replace("*", "").strip()


def is_marker(t: str) -> bool:
    return clean_token(t).upper() in MARKER_WORDS


def get_save_dir(mock_mode: bool, cm_strategy_label: str, g_strategy_label: str) -> str:
    mode_dir = "MockMode" if mock_mode else "NoMockMode"
    cm_dir = STRATEGY_DIR.get(cm_strategy_label, "Default")
    g_dir = STRATEGY_DIR.get(g_strategy_label, "Default")
    combo = f"CM-{cm_dir}__G-{g_dir}"
    return os.path.join("results", mode_dir, combo)


def ensure_save_dir(mock_mode: bool, cm_strategy_label: str, g_strategy_label: str):
    os.makedirs(get_save_dir(mock_mode, cm_strategy_label, g_strategy_label), exist_ok=True)


# ---- EventLog dataclass ----

@dataclass
class EventLog:
    seed: float = 0.0
    board: list = field(default_factory=list)
    key_grid: list = field(default_factory=list)
    timeline: list = field(default_factory=list)
    final_score: int = 0
    did_win: bool = False
    started_at: float = 0.0
    run_id: str = ""
    strategy: str = ""
    cm_interactions: list = field(default_factory=list)
    g_interactions: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(s: str):
        d = json.loads(s)
        return EventLog(**{k: v for k, v in d.items() if k in EventLog.__dataclass_fields__})


# ---- StreamObserver ----

class StreamObserver:
    def __init__(self):
        self.log = EventLog()

    def on_start(self, seed, words_in_play, key_grid):
        self.log.seed = seed
        self.log.started_at = time.time()
        self.log.board = [clean_token(w).upper() for w in words_in_play]
        self.log.key_grid = list(key_grid)
        self.log.timeline.append(
            {
                "type": "start",
                "board_snapshot": list(self.log.board),
            }
        )

    def on_clue(self, turn_num, clue, clue_num):
        self.log.timeline.append(
            {
                "type": "clue",
                "turn": int(turn_num),
                "clue": str(clue),
                "num": int(clue_num),
            }
        )

    def on_guess(self, guess_word, role, was_correct):
        snapshot = list(self.log.board)

        guess_clean = clean_token(guess_word).upper()
        role_up = str(role).upper()

        idx = None
        for i, lbl in enumerate(snapshot):
            if clean_token(lbl).upper() == guess_clean:
                idx = i
                break

        if idx is not None and role_up in MARKER_WORDS:
            self.log.board[idx] = f"*{role_up}*"
            snapshot[idx] = f"*{role_up}*"

        self.log.timeline.append(
            {
                "type": "guess",
                "guess": guess_clean,
                "role": role_up,
                "correct": bool(was_correct),
                "board_snapshot": snapshot,
            }
        )

    def on_end(self, final_score, did_win, cm_interactions=None, g_interactions=None):
        self.log.final_score = int(final_score)
        self.log.did_win = bool(did_win)
        if cm_interactions is not None:
            self.log.cm_interactions = list(cm_interactions)
        if g_interactions is not None:
            self.log.g_interactions = list(g_interactions)


# ---- persistence helpers ----

def list_saved_runs(mock_mode: bool, cm_strategy_label: str, g_strategy_label: str):
    ensure_save_dir(mock_mode, cm_strategy_label, g_strategy_label)
    base = get_save_dir(mock_mode, cm_strategy_label, g_strategy_label)
    files = [f for f in os.listdir(base) if f.endswith(".json")]
    files.sort(reverse=True)
    return files


def save_run(log: EventLog, mock_mode: bool, cm_strategy_label: str, g_strategy_label: str):
    ensure_save_dir(mock_mode, cm_strategy_label, g_strategy_label)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(log.started_at or time.time()))
    run_id = f"{ts}_{int(log.seed)}.json" if isinstance(log.seed, (int, float)) else f"{ts}.json"
    log.run_id = run_id
    path = os.path.join(get_save_dir(mock_mode, cm_strategy_label, g_strategy_label), run_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(log.to_json())
    return run_id


def load_run(mock_mode: bool, cm_strategy_label: str, g_strategy_label: str, run_id: str) -> EventLog:
    path = os.path.join(get_save_dir(mock_mode, cm_strategy_label, g_strategy_label), run_id)
    with open(path, "r", encoding="utf-8") as f:
        return EventLog.from_json(f.read())
