# Connections Puzzle Generator

A fully dynamic NYT Connections puzzle generator powered by LLMs, featuring multiple generation methods, player simulation, and a modern web interface.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)
![React](https://img.shields.io/badge/React-18-61dafb.svg)

## Overview

This project implements and extends the puzzle generation system described in "Making New Connections" by Merino et al. It generates valid, challenging Connections puzzles using Large Language Models with multiple generation strategies.

**Key Features:**
- 5 generation methods including novel TriCO (Tri-View Counterfactual Optimization)
- Fully dynamic word generation (no hardcoded word lists)
- Real phonetic rhyme detection using CMU Pronouncing Dictionary
- Automated player simulation for difficulty evaluation
- Modern minimalist web interface
- REST API for integration

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Generation Methods](#generation-methods)
- [Usage](#usage)
  - [Command Line](#command-line)
  - [Web Interface](#web-interface)
  - [API](#api)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Examples](#examples)
- [References](#references)

## Installation

### Prerequisites

- Python 3.8+
- OpenAI API key (for GPT-4 generation)

### Install Dependencies

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install sentence-transformers scikit-learn numpy pronouncing phonetics openai flask flask-cors
```

### Set API Key

```bash
export OPENAI_API_KEY="your-api-key-here"
```

## Quick Start

### Option 1: Command Line

```bash
python main.py
```

Follow the interactive prompts to:
1. Select generation method (1-5)
2. Choose model backend
3. Enter optional theme
4. Set number of simulations

### Option 2: Web Interface

```bash
# Start the API server
python server.py

# Open connections-ui.html in your browser
# (Use port-forwarding if running on remote server)
```

## Generation Methods

| Method | Description | Difficulty |
|--------|-------------|------------|
| **One-Step** | Single prompt generation | Easy |
| **Intentional Overlap** | Words with multiple meanings create traps | Hard |
| **False Group** | Red herring connections between groups | Medium |
| **Tree of Thoughts** | Iterative exploration of category types | Medium |
| **TriCO** | Tri-view optimization (semantic + phonetic + orthographic) | Variable |

### TriCO (Novel Contribution)

TriCO generates puzzles with three types of word relationships:

- **Semantic**: Words sharing meaning/category (e.g., SALMON, TROUT, BASS, PERCH → "Types of Fish")
- **Phonetic**: Words that rhyme (e.g., CHAIN, BRAIN, TRAIN, DRAIN → "Rhymes with -AIN")
- **Orthographic**: Visual patterns (e.g., BLUE, TREE, FISH, BIRD → "4-letter words")

TriCO is **fully dynamic**:
- Uses CMU Pronouncing Dictionary for real phonetic rhymes
- Discovers categories via embedding clustering + LLM validation
- No hardcoded word lists

## Usage

### Command Line

```bash
python main.py
```

**Output:**
```
============================================================
GENERATED PUZZLE
============================================================
YELLOW   | Types of Fish             | SALMON, TROUT, BASS, PERCH
GREEN    | Kitchen Utensils          | SPATULA, WHISK, LADLE, PEELER
BLUE     | Emotions                  | HAPPY, SAD, ANGRY, FEAR
PURPLE   | Rhymes with '-AIN'        | CHAIN, BRAIN, TRAIN, DRAIN

============================================================
SIMULATION RESULTS
============================================================
Solve Rate:            70.0%
Mean Mistakes:         1.30 ± 1.79
```

### Web Interface

1. Start the server:
   ```bash
   python server.py
   ```

2. If running remotely, port-forward:
   ```bash
   kubectl port-forward pod/YOUR_POD 5001:5001
   ```

3. Open `connections-ui.html` in your browser

4. Configure and generate!

### API

#### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/methods` | GET | List available methods |
| `/api/generate` | POST | Generate a puzzle |
| `/api/simulate` | POST | Run player simulations |
| `/api/evaluate` | POST | Evaluate puzzle quality |

#### Example: Generate Puzzle

```bash
curl -X POST http://localhost:5001/api/generate \
  -H "Content-Type: application/json" \
  -d '{"method": "trico", "theme": "music"}'
```

#### Example: Run Simulations

```bash
curl -X POST http://localhost:5001/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"puzzle": {...}, "simulations": 10}'
```

## Project Structure

```
├── core.py                 # Data structures, enums, utilities
├── generator.py            # All 5 generation methods
├── player.py               # Player simulation & evaluation
├── main.py                 # Command-line interface
├── server.py               # Flask API server
├── connections-ui.html     # React web frontend
├── connections-frontend.jsx # React component (for integration)
├── requirements.txt        # Python dependencies
├── paper.tex              # LaTeX paper
└── README.md              # This file
```

### Module Details

| Module | Lines | Purpose |
|--------|-------|---------|
| `core.py` | ~1,226 | `ConnectionsPuzzle`, `WordGroup`, `PuzzleMode`, similarity calculators |
| `generator.py` | ~2,700 | `PuzzleGenerator` with all methods, TriCO implementation |
| `player.py` | ~1,166 | `PuzzleSimulator`, `HumanEvaluator`, solving strategies |
| `main.py` | ~420 | Interactive CLI, display formatting |
| `server.py` | ~284 | REST API wrapping Python modules |

## How It Works

### TriCO Generation Flow

```
1. Generate Word Pool (LLM)
   ↓
2. Find Semantic Groups
   - Cluster words via embeddings
   - LLM names each cluster
   - Validate each word individually
   ↓
3. Find Phonetic Groups
   - CMU Pronouncing Dictionary
   - Group by rhyme part
   ↓
4. Find Orthographic Groups
   - Analyze length, prefix, suffix
   ↓
5. Select 4 Diverse Groups
   - Min 2 semantic
   - Max 1 phonetic
   - Max 1 orthographic
   ↓
6. Final Quality Validation
   ↓
7. Return Puzzle
```

### Player Simulation Strategies

| Strategy | Description |
|----------|-------------|
| **Hybrid** | LLM reasoning + embedding clustering |
| **Human-like** | Target obvious groups first |
| **Greedy Embedding** | Pure K-means clustering |
| **Random** | Baseline random guessing |

### Evaluation Metrics

- **Semantic Clarity**: How tightly clustered each group is
- **Deceptiveness**: Cross-group similarity (trap potential)
- **Creativity**: Category originality
- **Near-miss Count**: Plausible wrong groupings
- **Estimated Solve Rate**: Predicted human success rate

## Examples

### TriCO Puzzle

```
YELLOW | Professions           | TEACHER, SCIENTIST, ENGINEER, ARCHITECT  [Semantic]
GREEN  | Musical Terms         | TROMBONE, SONATA, ARPEGGIO, CELLO        [Semantic]
BLUE   | 4-letter words        | KING, THAT, WITH, TEAM                   [Orthographic]
PURPLE | Rhymes with '-HAIN'   | CHAIN, STAIN, DRAIN, BRAIN               [Phonetic]
```

### Intentional Overlap Puzzle

```
YELLOW | Birds                 | CRANE, ROBIN, SWIFT, CARDINAL
GREEN  | Construction          | CRANE, BEAM, FOUNDATION, SCAFFOLDING
BLUE   | Batman Characters     | ROBIN, JOKER, PENGUIN, RIDDLER
PURPLE | Banks                 | SWIFT, CHASE, CAPITAL, WELLS
```
*(CRANE and ROBIN appear in multiple conceptual categories)*

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | Model to use | `gpt-4` |

### Generation Parameters

```python
generator.generate_puzzle(
    mode=PuzzleMode.TRICO,      # Generation method
    theme="music",              # Optional theme
    difficulty_target=0.35     # Target difficulty (0-1)
)
```

## Performance

| Method | Solve Rate | Avg Mistakes | Generation Time |
|--------|------------|--------------|-----------------|
| One-Step | 70% | 2.1 | ~5s |
| Intentional Overlap | 40% | 2.5 | ~15s |
| False Group | 100% | 0.9 | ~10s |
| Tree of Thoughts | 100% | 0.3 | ~20s |
| TriCO | 70% | 1.3 | ~30s |

## Troubleshooting

### "phonetics library not available"

```bash
pip install phonetics --break-system-packages
```

### "Object of type float32 is not JSON serializable"

Update to latest `server.py` which includes numpy type conversion.

### API Disconnected (Web UI)

1. Ensure server is running: `python server.py`
2. If remote, use port-forwarding: `kubectl port-forward pod/NAME 5001:5001`
3. Check CORS is enabled in server

### Generation Fails

- Check OpenAI API key is set
- Ensure sufficient API quota
- Try reducing simulation count

## References

- Merino et al., "Making New Connections: LLMs as Puzzle Generators for The New York Times' Connections Word Game" (2024)
- CMU Pronouncing Dictionary
- Sentence-Transformers (all-MiniLM-L6-v2)

## Authors

Russell Elliott, Ehsan Mirafzali, Victoria Duan  
University of California, Santa Cruz

## License

MIT License
