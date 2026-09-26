#pragma once
#include "paindemic/game_state.h"
#include "paindemic/action.h"
#include "paindemic/log.h"

#include <string>
#include <vector>

namespace paindemic {

// ---------------------------------------------------------------------------
// The engine: the entire contract an AI agent needs.
//
//   newGame      -> a fresh, fully set-up state (reproducible from `seed`)
//   legalActions -> every legal move from a state (never empty while InProgress)
//   applyAction  -> pure transition: returns a new, independent state
//   serialize    -> human / LLM-readable dump of a state
//
// applyAction resolves all non-decision flow internally (drawing player cards,
// epidemics, infections, turn advancement). It only ever hands control back to
// the agent at genuine decision points: spending actions, and discarding down to
// the hand limit (Phase::Discard).
// ---------------------------------------------------------------------------

// roles.size() determines the player count (2..4). `epidemics` is the number of
// Epidemic cards shuffled into the player deck (4=intro, 5=standard, 6=heroic).
GameState newGame(const std::vector<RoleType>& roles, unsigned seed, int epidemics = 5);

std::vector<Action> legalActions(const GameState& s);

GameState applyAction(const GameState& s, const Action& a);

// Logging overload: appends structured reveal events (cards drawn, infections,
// epidemics, outbreaks, cures, win/loss) to `log` as it resolves. Pass nullptr for
// the pure behaviour. The plain applyAction(s, a) above forwards here with nullptr.
GameState applyAction(const GameState& s, const Action& a, EventLog* log);

// --- Planning support (used by the heuristic / planner agents) ---------------
// Apply a single action WITHOUT resolving the end-of-turn draw/infect. A
// turn-ending action (4th action or Pass) lands the state at Phase::Draw with the
// decks and infections untouched, so search can explore action sequences over only
// the known information.
GameState stepAction(const GameState& s, const Action& a);

// From a Phase::Draw state, resolve the stochastic draw + epidemic + infect phases
// (and any forced discards) using the state's seeded RNG, advancing to the next
// turn. Used for Monte Carlo rollouts at goal states.
GameState resolveTurnEnd(const GameState& s, EventLog* log = nullptr);

// From a Phase::Draw state, hand the SAME player a fresh action phase WITHOUT
// drawing cards, infecting, or advancing through the other players. This is the
// "jump to my next turn" transition a 2-turn-horizon planner uses to look ahead
// past its own turn boundary while skipping all stochastic/other-player effects
// (which are accounted for only in the rollout evaluation).
GameState advanceTurnSkippingDraws(const GameState& s);

// Like advanceTurnSkippingDraws, but hands the fresh action phase to the NEXT player
// (still no draws/infections/teammate turns). A multi-turn cooperative planner uses
// this to look ahead into the next player's turn — justified in a cooperative game with
// known hands — accounting for stochastic effects only in the rollout evaluation.
GameState advanceToNextPlayerSkippingDraws(const GameState& s);

// Re-determinize the hidden decks from public information: reshuffle the cards known
// to be in the infection deck (within each epidemic block) and the player deck
// (within each setup pile, one epidemic per pile that still holds it), leaving hands,
// discards, and the board untouched. Agents call this before each Monte Carlo rollout
// so rollouts neither peek at the true draw order nor collapse to a single outcome.
GameState determinizeHiddenDecks(GameState s, std::mt19937& rng);

std::string serialize(const GameState& s);

// Convenience for agents/tests: true when no further moves should be requested.
inline bool isTerminal(const GameState& s) { return s.status != GameStatus::InProgress; }

} // namespace paindemic
