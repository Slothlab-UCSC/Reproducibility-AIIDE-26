#pragma once
#include "paindemic/types.h"
#include "paindemic/cards.h"
#include "paindemic/action.h"

#include <string>
#include <vector>

namespace paindemic {

// Structured trace of everything that happens during applyAction, including the
// hidden reveals (player cards drawn, infection cards flipped, epidemics,
// outbreaks) that the engine otherwise resolves internally. Events are
// self-describing: `describe` needs nothing but the Event itself.
enum class EventType {
    TurnStart,
    ActionPerformed,
    PlayerCardDrawn,    // card (city or epidemic) entering a hand
    EpidemicIncrease,   // amount = new infection rate
    EpidemicInfect,     // city = bottom card infected with 3 cubes
    EpidemicIntensify,
    InfectionDrawn,     // city flipped during the infect phase
    Outbreak,           // city/color; amount = running outbreak count
    HandDiscard,        // player discards card (hand limit or as a cost)
    CureDiscovered,     // color
    Eradicated,         // color
    GameWon,
    GameLost            // amount = LossReason
};

enum class LossReason { None = 0, EighthOutbreak, CubesOut, PlayerDeckOut };

struct Event {
    EventType type;
    int8_t   player = -1;
    RoleType role   = RoleType::Scientist;
    Action   action{};
    Card     card{};
    CityId   city  = NO_CITY;
    Color    color = Color::None;
    int      amount = 0;
};

using EventLog = std::vector<Event>;

// Small text helpers (also handy for the driver / future LLM agents).
std::string roleName(RoleType r);
std::string colorName(Color c);

// One-line human-readable rendering.
std::string describeAction(int player, RoleType role, const Action& a);
std::string describe(const Event& e);

} // namespace paindemic
