#pragma once
#include "paindemic/game_state.h"

#include <string>
#include <string_view>

namespace paindemic {

// Machine-readable game-state snapshot used by the differential decision harness
// (tools comparing this engine's planner against the paper's Python reference).
//
// Format conventions, chosen so Python and C++ emit/parse the *same* text:
//   - city names are the Python convention (lowercase, underscores: "new_york")
//   - colors are always ordered blue, yellow, black, red (the Color enum order)
//   - only the fields a *deterministic* (sampling-free) planner/heuristic reads are
//     carried; the hidden draw/infection deck order is NOT — playerDraw is rebuilt as
//     a dummy vector of the recorded size (only its length feeds h_dist).
//
// One snapshot looks like:
//   meta players=2 current=0 phase=actions actions=4 infrate=2 outbreaks=0 turn=1 deck=44 initdeck=44
//   player 0 role=scientist loc=atlanta hand=delhi,manila,taipei,tokyo
//   player 1 role=researcher loc=atlanta hand=seoul,khartoum,montreal,hong_kong
//   cubes paris=1,0,0,0 tokyo=0,0,0,2
//   supply 24,23,22,24
//   stations atlanta
//   cures 0,0,0,0
//   discard
std::string writeState(const GameState& s);

// Parse a snapshot block (lines up to, but not including, any non-state line) into a
// GameState suitable for legalActions / evaluateState / the planner. Throws
// std::runtime_error on a malformed block.
GameState parseState(std::string_view block);

// City-name helpers in the Python convention.
std::string pyCityName(CityId c);
CityId cityFromPyName(std::string_view name);  // NO_CITY if unknown

} // namespace paindemic
