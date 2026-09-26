#pragma once
#include "paindemic/types.h"
#include "paindemic/cards.h"
#include "paindemic/player.h"

#include <array>
#include <cstdint>
#include <random>
#include <vector>

namespace paindemic {

inline constexpr std::array<int, 7> INFECTION_RATE_TRACK = {2, 2, 2, 3, 3, 4, 4};

// Complete game state. Designed as a value type: every member has value semantics
// (no pointers, no references into shared data), so a plain copy yields a fully
// independent state — exactly what tree search / rollouts need. The embedded
// std::mt19937 is the single source of randomness, so a (state, action) sequence
// from a given seed is perfectly reproducible.
struct GameState {
    // --- Board ---
    std::array<std::array<uint8_t, NUM_COLORS>, NUM_CITIES> cubes{};  // [city][color]
    std::array<uint8_t, NUM_COLORS> cubesSupply{};                    // remaining in supply
    std::array<bool, NUM_CITIES> stations{};
    uint8_t stationCount = 0;
    std::array<CureStatus, NUM_COLORS> cures{};

    // --- Players ---
    std::vector<Player> players;
    uint8_t currentPlayer = 0;
    uint8_t actionsRemaining = ACTIONS_PER_TURN;

    // --- Decks (top of deck == back of vector; drawn via pop_back) ---
    std::vector<Card> playerDraw;
    std::vector<Card> playerDiscard;
    std::vector<CityId> infectionDraw;
    std::vector<CityId> infectionDiscard;

    // Public deck structure for hidden-info re-determinization in agent rollouts.
    // All ordered bottom->top, matching the deck vectors (front = bottom, back = top).
    // infectionDraw is a stack of blocks (each block = an epidemic reshuffle, with
    // public membership but hidden internal order). playerDraw is a sequence of setup
    // piles, each originally holding one epidemic. Maintained only for newGame-derived
    // states; updates are guarded so hand-built states are unaffected.
    std::vector<uint8_t> infectionBlockSizes;
    std::vector<uint8_t> playerPileSizes;
    std::vector<uint8_t> playerPileHasEpidemic;

    // --- Tracks ---
    uint8_t infectionRateIndex = 0;
    uint8_t outbreakCount = 0;
    uint16_t initialPlayerDeckSize = 0;  // turnsMax reference for the heuristic

    // --- Flow control ---
    Phase phase = Phase::PlayerActions;
    GameStatus status = GameStatus::InProgress;
    int8_t discardingPlayer = -1;  // who must discard during Phase::Discard
    bool opsFlightUsedThisTurn = false;  // Operations Expert's once-per-turn flight

    std::mt19937 rng;

    // --- Helpers ---
    int infectionRate() const {
        return INFECTION_RATE_TRACK[infectionRateIndex];
    }
    Player& cur() { return players[currentPlayer]; }
    const Player& cur() const { return players[currentPlayer]; }

    int colorIndex(Color c) const { return static_cast<int>(c); }
    uint8_t cubeCount(CityId city, Color color) const {
        return cubes[static_cast<size_t>(city)][static_cast<size_t>(color)];
    }
    bool hasStation(CityId city) const { return stations[static_cast<size_t>(city)]; }
};

} // namespace paindemic
