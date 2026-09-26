# PAIndemic

A headless C++20 game engine for the board game **Pandemic** (base game), built to
be driven by AI agents (tree search, RL, or LLM).

## Design goals

1. **Agent-drivable.** `GameState` is a pure value type (cities/players referenced
   by integer index, no pointers), so cloning a state for search is a plain copy.
   Randomness comes from a single seeded `std::mt19937` carried *in* the state, so a
   `(state, action)` sequence is perfectly reproducible.
2. **Rules-correct core.** Board, cubes, decks, infect/epidemic/outbreak chains, the
   standard actions, the 7 base roles, and all win/loss conditions.

## The agent contract (`include/paindemic/engine.h`)

```cpp
GameState           newGame(const std::vector<RoleType>& roles, unsigned seed, int epidemics = 5);
std::vector<Action> legalActions(const GameState& s);   // never empty while in progress
GameState           applyAction(const GameState& s, const Action& a);  // pure transition
std::string         serialize(const GameState& s);      // human / LLM readable
bool                isTerminal(const GameState& s);
```

`applyAction` resolves all non-decision flow internally (drawing player cards,
epidemics, infections, turn advancement). It only returns control to the agent at
real decision points: spending the 4 actions, and discarding to the hand limit
(`Phase::Discard`).

## Layout

```
include/paindemic/   types, map_data, cards, player, action, game_state, engine
src/                 map_data.cpp (48-city board), engine.cpp (rules)
tests/               doctest suites + random self-play smoke test
third_party/         vendored doctest.h
```

## Build & test

```sh
cmake -S . -B build
cmake --build build -j
ctest --test-dir build --output-on-failure   # or: ./build/paindemic_tests
```

Requires CMake ≥ 3.20 and a C++20 compiler. Builds clean under `-Wall -Wextra`.

## Running games (`paindemic_driver`)

A console driver runs games with agents and prints the starting configuration plus
a full turn-by-turn trace (actions, cards drawn, infections, epidemics, outbreaks,
cures, win/loss).

```sh
./build/paindemic_driver                                   # 1 game, random agents
./build/paindemic_driver -n 10 --seed 7                     # 10 reproducible games
./build/paindemic_driver --agent greedy                     # greedy baseline
./build/paindemic_driver --agent planner -n 50 --players 2 --epidemics 4
```

| option           | meaning                                                  | default |
|------------------|----------------------------------------------------------|---------|
| `-n, --games N`  | number of games to run                                   | 1       |
| `--seed S`       | base RNG seed; game *i* uses `S+i`                        | 1       |
| `--agent NAME`   | `random` / `greedy` / `heuristic` / `planner` / `planner2` / `planner3` / `planner4` | random  |
| `--turns N`      | `planner4` look-ahead horizon, in players' turns          | 2       |
| `--players P`    | 2..4 players                                             | 4       |
| `--epidemics E`  | epidemics in the deck (4..6)                             | 5       |
| `--rollouts N`   | planner Monte Carlo samples per goal state               | 30      |
| `--max-turns T`  | safety cap per game                                      | 2000    |

The summary reports **win rate** and **average cures discovered per game** (how close
the team got to winning). Same seed + same agent ⇒ byte-identical output.

### Agents

> **Note on the win-rate figures below.** The parenthetical numbers in the `planner2` /
> `planner3` / `planner4` descriptions describe the *relative* design story and were measured
> under two non-paper crutches (a fixed Scientist+Researcher 2-player pairing and a loss
> penalty on lost rollouts), both since removed for fidelity. With the paper's actual setup —
> randomized role combinations and no loss penalty — every planner drops to 0–5% win at
> 2p/4-epi. See the "Paper-faithful re-measurement" section of `literal.md` for the current,
> honest numbers; the descriptions here are kept for the design rationale.

- `random` — uniform over legal moves.
- `greedy` — a simple hand-rolled action-preference heuristic.
- `heuristic` — the **AIIDE-20 paper's greedy baseline**: picks the action minimizing
  the paper's state-evaluation heuristic (`include/paindemic/heuristic.h`, eq. 1–8) on
  the immediate next state.
- `planner` — the **AIIDE-20 planning agent** (Sauma-Chacón & Eger): A\* over the
  current player's turn with the draw/infect phases skipped, choosing a *discover-cure*
  or *survive* goal, and evaluating goal states with Monte Carlo rollouts of the hidden
  draws. **Single-turn** search horizon.
- `planner2` — the same agent with the paper's **literal 2-turn horizon**: the search
  crosses its own turn boundary (`advanceTurnSkippingDraws`) into a second turn of
  lookahead before judging the *survive* goal, and rolls a full round of infections
  forward when evaluating. Only the first turn's actions are executed; the second turn
  guides that choice. Deeper, but ~10× slower, and on this engine it actually
  **under-performs** `planner` (≈9% vs 27% win at 2p/4-epi) because infections between
  the two turns aren't modeled inside the search — see `literal.md` for the full
  analysis, the head-to-head numbers, and why.
- `planner3` — the **structural fix** for `planner2`'s flaw: the outer A\* searches only
  turn 1, and the second turn is *re-planned inside every rollout* on a freshly
  re-determinized, re-infected board, with the other players modeled by the greedy eq.8
  heuristic (`greedyHeuristicChoice`) rather than skipped or passing. This couples the
  second-turn search with the sampling, so the second turn's action choices and their
  evaluation are both made on realistic boards. It **recovers most of `planner2`'s lost
  ground** (≈15% vs 9% win, 1.87 vs 1.74 cures at 2p/4-epi), confirming the asymmetry
  diagnosis — but it still trails the cheap `planner` and costs ~170× as much wall-clock
  (≈1h20m / 100 games). See `literal.md` for the analysis and why.
- `planner4` — the paper's **faithful "n turns ahead" horizon**: the A\* crosses each turn
  boundary into the **next player's** turn (`advanceToNextPlayerSkippingDraws`) and plans
  *that player's* actions too — valid in a cooperative game with known hands — for
  `--turns` turns (default 2). Only the first turn is executed; the rest is cooperative
  look-ahead. Evaluation is identical to `planner2`, so the only difference is *whose*
  turn fills the second slot. That single change **more than doubles `planner2`'s win rate
  (9% → 21%) and brings cures level with `planner` (2.23 vs 2.29)** at the same ~5-min
  cost — the best multi-turn variant, though still shy of single-turn `planner`'s 27%.
  See `literal.md`.

Rollouts for both planners **re-determinize the hidden decks from public information**
before each sample (`determinizeHiddenDecks`): the infection deck is reshuffled within
each epidemic block and the player deck within each setup pile, so rollouts neither
peek at the true draw order nor collapse to a single outcome.

`heuristic`, `planner`, `planner2`, `planner3`, and `planner4` play the paper's
**Restricted Pandemic**: only the Scientist, Researcher, Quarantine Specialist, and Medic
roles are used, and the driver assigns a **random distinct subset of them each game**
(seeded by `--seed`), matching the paper's averaging over role combinations. Because the
old fixed Scientist+Researcher pairing was a strong, cure-focused one, the randomized
two-player win rates are markedly lower (and more honest) than the fixed-pair figures.
See `literal.md` for the current head-to-head numbers and `paper-differences.md` for the
remaining deltas from the paper.



### Trace & agents under the hood

- **Event log** (`include/paindemic/log.h`): `applyAction(s, a, EventLog*)` appends
  structured `Event`s for every reveal; `describe(Event)` renders one line. The pure
  `applyAction(s, a)` is unchanged, so search/agents pay nothing.
- **Agents** (`include/paindemic/agent.h`): implement the `Agent` interface and
  register a name in `makeAgent` (`src/agents.cpp`) — the single edit point for new
  agent types (heuristic, MCTS, LLM-backed, …).
- **Planning API** (`include/paindemic/engine.h`): `stepAction` applies one action
  *without* resolving the stochastic end-of-turn (lands at `Phase::Draw`), and
  `resolveTurnEnd` performs the draw/infect for rollouts — so a planner can search
  over known information only. The pure `applyAction` is unchanged.

## v1 scope & known simplifications

- **No event cards** yet — the player deck is city + epidemic only. The Contingency
  Planner role slot exists but has no special moves until events land.
- **Dispatcher** supports summon (move a pawn onto another pawn) and driving any
  pawn to an adjacent city; card-based moving of *other* pawns is deferred.
- **Build station** requires `stationCount < 6` (relocating an existing station when
  all 6 are placed is not modeled).

## Roadmap

- Event cards + the event hook (activates the Contingency Planner).
- A thin CLI/text front-end.
- AI agents: random baseline (already in the self-play test), then MCTS / heuristic.
