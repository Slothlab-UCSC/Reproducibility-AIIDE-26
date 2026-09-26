#pragma once
#include <cstdint>

namespace paindemic {

// A city is referenced everywhere by its integer index into the static map table
// (0..47). Using indices (not pointers) keeps GameState a trivially copyable value
// type, which is what makes cheap clone-for-search possible.
using CityId = int8_t;
inline constexpr CityId NO_CITY = -1;

inline constexpr int NUM_CITIES = 48;
inline constexpr int NUM_COLORS = 4;
inline constexpr int CUBES_PER_COLOR = 24;
inline constexpr int MAX_RESEARCH_STATIONS = 6;
inline constexpr int HAND_LIMIT = 7;
inline constexpr int MAX_OUTBREAKS = 8;       // reaching this = loss
inline constexpr int ACTIONS_PER_TURN = 4;
inline constexpr int MAX_PLAYERS = 4;

// City / disease colors. Index 0..3 also indexes the cube arrays and cure track.
enum class Color : int8_t { Blue = 0, Yellow = 1, Black = 2, Red = 3, None = -1 };

// Per-disease cure progress.
enum class CureStatus : int8_t { Uncured = 0, Cured = 1, Eradicated = 2 };

// The 7 base-game roles.
enum class RoleType : int8_t {
    ContingencyPlanner = 0,
    Dispatcher,
    Medic,
    OperationsExpert,
    QuarantineSpecialist,
    Researcher,
    Scientist,
    COUNT
};

// Turn phases driven by the engine's internal state machine.
enum class Phase : int8_t {
    PlayerActions,  // current player has actionsRemaining to spend
    Draw,           // draw 2 player cards (resolved internally)
    Discard,        // a player is over the hand limit and must discard
    Infect,         // flip infection cards (resolved internally)
    GameOver
};

enum class GameStatus : int8_t { InProgress = 0, Won = 1, Lost = 2 };

// All action kinds an agent can choose from. Each maps to a small set of integer
// args carried in the Action struct (see action.h).
enum class ActionType : int8_t {
    DriveFerry,        // move to an adjacent city
    DirectFlight,      // discard a city card, move to that city
    CharterFlight,     // discard card of current city, move anywhere
    ShuttleFlight,     // move between two research stations
    BuildStation,      // build a research station in current city
    TreatDisease,      // remove cube(s) of a color from current city
    ShareGive,         // give the current-city card to another player
    ShareTake,         // take the current-city card from another player
    DiscoverCure,      // discard matching cards at a station to cure a disease
    Pass,              // forfeit remaining actions

    // Role-specific
    DispatcherMovePawn,    // move any pawn as if it were yours (drive/charter/etc.)
    DispatcherSummon,      // move any pawn to a city containing another pawn
    OperationsFlight,      // Operations Expert: from a station, discard any card -> anywhere
    ResearcherGive,        // Researcher gives any card from hand (handled via ShareGive)

    // Forced/utility
    Discard                // discard a named card (hand-limit resolution)
};

} // namespace paindemic
