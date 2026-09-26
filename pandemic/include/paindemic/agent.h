#pragma once
#include "paindemic/game_state.h"
#include "paindemic/action.h"

#include <memory>
#include <string>
#include <vector>

namespace paindemic {

// Strategy that chooses a move from the legal set. New agent types (heuristic,
// MCTS, LLM-backed, ...) implement this interface and register a name in
// makeAgent() — that factory is the single edit point for adding agents.
struct Agent {
    virtual ~Agent() = default;
    virtual std::string name() const = 0;
    // `legal` is guaranteed non-empty (the engine never offers an empty set while
    // the game is in progress).
    virtual Action chooseAction(const GameState& s, const std::vector<Action>& legal) = 0;
};

// Construct an agent by name (e.g. "random", "greedy", "heuristic", "planner").
// Unknown names fall back to the random agent. `seed` makes the agent's own choices
// reproducible. `rollouts` is the Monte Carlo sample count used by the planner
// (ignored by the other agents). `planTurns` is the look-ahead horizon in turns used
// by `planner4` (number of consecutive players' turns it plans; ignored otherwise).
// `deterministic` (planner agents only) ranks goals by g+h alone, skipping the Monte-Carlo
// predictor — used by the differential decision harness. `nodeCap` (>0) overrides the A*
// node budget (e.g. to align with the paper's 3500 for that comparison).
std::unique_ptr<Agent> makeAgent(const std::string& name, unsigned seed, int rollouts = 30,
                                 int planTurns = 2, bool deterministic = false, int nodeCap = 0);

// The goal the planning agents would pursue from this state: true = discover-cure,
// false = survive (the paper's goal_heuristic_chooser). Exposed for the differential harness.
bool plannerPursuesCure(const GameState& s);

// Names of all registered agent types (for --help / discovery).
std::vector<std::string> agentNames();

} // namespace paindemic
