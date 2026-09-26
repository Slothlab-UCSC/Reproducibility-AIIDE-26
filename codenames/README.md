# Codenames AI — Prompt Strategy Research Framework

A framework for systematically evaluating prompt-engineering strategies for LLM agents playing the cooperative word game [Codenames](https://czechgames.com/en/codenames/). Built on top of the [Codenames AI Competition](https://github.com/alanabibi/codenames) framework, extended for multi-provider batch experimentation and research.

This project reproduces and extends *Prompt Engineering ChatGPT for Codenames* (Sidji & Stephenson, 2024), testing all **36 cross-strategy combinations** (6 Codemaster × 6 Guesser) across **30 fixed board seeds** on GPT-4o-mini (1,101 games), plus a 24-combination subset on Gemini 2.5 Flash Lite (664 games) — 1,765 valid games in total. This work is part of a co-authored submission to AIIDE 2026.

---

## Key Findings

| Finding | Detail |
|---|---|
| Best combo (OpenAI) | COT Codemaster + Cautious Guesser — **96% win rate** |
| Guesser strategy dominates | Swapping guesser strategy has far more impact on win rate than swapping codemaster strategy |
| Cautious Guesser lifts any CM | Paired with any codemaster, Cautious Guesser achieves 67–96% win rate |
| Self-Refine failure mode | The uninformed guesser's self-critique overrode its own answers 93–99% of the time, converting correct picks to wrong ones in 60% of changes (buggy variant: 87% assassin rate). Rewording the critique didn't help — removing it took win rate from 22% to 73% |
| Reflection asymmetry | The same critique step *helped* the informed Codemaster (+10 pts in a controlled 2×2) — self-reflection only helps an agent with information to reflect on |
| Overall OpenAI win rate | 60.2% across 1,101 games |
| Contradicts original paper | Cross-strategy pairings (not tested in the original) show 70–96% WR, contradicting "no significant improvement over Default" |

Full results: [`results/analysis_report.md`](results/analysis_report.md)

---

## Strategies

Six prompt strategies are implemented for both the Codemaster and Guesser:

| Strategy | Description |
|---|---|
| **Default** | Single-step prompt — pick the best clue/word |
| **Cautious** | Prioritizes safety; guesser stops after 1 guess per turn |
| **Risky** | Aggressive; guesser uses all available guesses |
| **COT** | Chain-of-thought reasoning before final answer |
| **Self Refine** | Initial answer followed by a critique and refinement step |
| **Solo Performance** | Instructs the model to internally reason before responding |

---

## Project Structure

```
codenames/
  game.py                   # Core game engine
  players/
    codemaster_gpt.py       # LLM Codemaster (all 6 strategies)
    guesser_gpt.py          # LLM Guesser (all 6 strategies)
    gpt_manager.py          # Multi-provider LLM wrapper (OpenAI, Gemini, Anthropic)
    event_log.py            # Per-game event logging

run_experiments.py          # Batch runner: all 36 combos × 30 seeds
analyze_results.py          # Generates results/analysis_report.md
build_dataset.py            # Exports labeled CM/Guesser datasets
generate_html_replay.py     # HTML game replay viewer
ui_app.py                   # Streamlit dashboard for single games

results/
  experiment_results.json   # All game results (primary data)
  analysis_report.md        # Win rates, assassin hits, per-combo breakdown
  analysis_gemini.png       # Win rate heatmap

docs/
  Prompt Engineering ChatGPT for Codenames.pdf  # Reference paper
  aiide2026_section.md      # Draft paper section for AIIDE 2026
```

---

## Installation

```bash
conda create --name codenames python=3.10
conda activate codenames
pip install streamlit openai google-genai anthropic
```

## API Keys

Set environment variables before running:

```bash
export OPENAI_API_KEY="your-openai-key"
export GEMINI_API_KEY="your-gemini-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
export LLM_PROVIDER="openai"   # or "gemini" / "anthropic"
```

---

## Running Experiments

**Batch experiment runner** (all 36 combos, 30 seeds, resumable):
```bash
python run_experiments.py --provider openai   # OpenAI only
python run_experiments.py --provider gemini   # Gemini only
python run_experiments.py                     # Both
```

Results are saved incrementally to `results/experiment_results.json`. Already-completed games are skipped on resume.

**Regenerate analysis report:**
```bash
python analyze_results.py
```

**Streamlit dashboard** (single games, interactive):
```bash
streamlit run ui_app.py
```

The sidebar lets you choose provider, codemaster strategy, guesser strategy, and whether to run a single game or a batch of 10 fixed boards.

---

## Game Class

```python
from codenames.game import Game
from codenames.players.codemaster_gpt import AICodemaster
from codenames.players.guesser_gpt import AIGuesser

game = Game(
    AICodemaster,
    AIGuesser,
    seed=12345,               # fixed seed for reproducibility, or "time"
    do_print=True,
    do_log=True,
    cm_kwargs={"strategy": "COT"},
    g_kwargs={"strategy": "Cautious"},
)
game.run()
```

---

## Codemaster Interface

Any Codemaster is a Python class deriving from `Codemaster` in `codemaster.py`:

```python
def __init__(self)
def set_game_state(words_on_board: List[str], key_grid: List[str]) -> None
def get_clue() -> Tuple[str, int]
```

`words_on_board` contains either plain uppercase words or revealed tokens (`*Red*`, `*Blue*`, `*Civilian*`, `*Assassin*`). `key_grid` contains the full identity map only visible to the Codemaster.

---

## Guesser Interface

Any Guesser is a Python class deriving from `Guesser` in `guesser.py`:

```python
def __init__(self)
def set_board(words: List[str]) -> None
def set_clue(clue: str, num_guesses: int) -> None
def keep_guessing() -> bool
def get_answer() -> str
```

`keep_guessing` is called after each correct guess to decide whether to continue. `get_answer` returns one word from the remaining board words.

---

## Rules Summary

- 25 words on the board; 8 are Red (your team), 7 Blue, 8 Civilian, 1 Assassin
- Codemaster gives a one-word clue + count each turn
- Guesser picks words; turn ends on a wrong pick or by choice
- Win: find all 8 Red words. Lose: reveal all Blue words or hit the Assassin
