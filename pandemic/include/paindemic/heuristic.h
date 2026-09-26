#pragma once
#include "paindemic/game_state.h"

namespace paindemic {

// State-evaluation heuristic from Sauma-Chacón & Eger, "PAIndemic: A Planning Agent
// for Pandemic" (AIIDE-20), equations 1-8. Lower is better (the agents minimize it);
// a won state (all diseases cured) drives the dominant h_cures term to 0.
//
// Distances are research-station aware: any two stations are one shuttle step apart,
// so building stations shortens the relevant distance terms — as the paper intends.
double evaluateState(const GameState& s);

// Goal-dependent variant. The paper's Heuristic.heuristic(find_diseases, find_rs) toggles
// the two distance terms by the agent's current goal: the *survive* goal uses only h_dsurv
// (findDiseases) and the *discover-cure* goal uses only h_dcure (findRs). The greedy
// baseline uses both — which is exactly evaluateState(s) above (both flags true).
double evaluateState(const GameState& s, bool findDiseases, bool findRs);

// The individual weighted terms, exposed for tests / tuning.
struct HeuristicTerms {
    double dsurv;  // eq.1  proximity to infected cities (survive goal)
    double dcure;  // eq.2  proximity to research stations (cure goal)
    double cards;  // eq.3  cards still missing toward each cure
    double disc;   // eq.4  useful cards lost to the discard pile
    double inf;    // eq.5  total cubes on the board
    double dist;   // eq.6  board "spread" cost, scaled by turns remaining
    double cures;  // eq.7  diseases still lacking a cure
    double total() const;                          // both distance terms (greedy baseline)
    double total(bool findDiseases, bool findRs) const;  // goal-toggled distances
};
HeuristicTerms heuristicTerms(const GameState& s);

} // namespace paindemic
