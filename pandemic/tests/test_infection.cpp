#include "doctest.h"
#include "test_helpers.h"

using namespace paindemic;
using namespace pt;

namespace {
// Minimal state with one player (engine supports 2+, but infection mechanics are
// independent of player count; we still give 2 for validity).
GameState bare() {
    GameState s;
    s.cubesSupply.fill(CUBES_PER_COLOR);
    s.cures.fill(CureStatus::Uncured);
    s.players = {Player{RoleType::Scientist, STARTING_CITY, {}},
                 Player{RoleType::Researcher, STARTING_CITY, {}}};
    s.currentPlayer = 0;
    s.phase = Phase::PlayerActions;
    return s;
}

// Drives the internal infect phase by giving the player a Pass with empty hand and
// a known infection deck. We instead test infection by a tiny custom harness:
// place an infection card on top and call applyAction(Pass) with a player deck of
// two harmless city cards so the turn completes (draw 2 cities, then infect).
} // namespace

TEST_CASE("single infection adds one cube") {
    GameState s = bare();
    // Player deck: two harmless city cards so the draw step doesn't lose/epidemic.
    s.playerDraw = {Card::cityCard(city::Lima), Card::cityCard(city::Santiago)};
    s.infectionRateIndex = 0;  // rate 2
    // Top two infection cards (drawn from back): Sydney then Paris.
    s.infectionDraw = {city::Paris, city::Sydney};

    s = applyAction(s, Action::pass());

    CHECK(s.status == GameStatus::InProgress);
    CHECK(s.cubeCount(city::Sydney, Color::Red) == 1);
    CHECK(s.cubeCount(city::Paris, Color::Blue) == 1);
}

TEST_CASE("fourth cube triggers an outbreak, not a 4th cube") {
    GameState s = bare();
    s.playerDraw = {Card::cityCard(city::Lima), Card::cityCard(city::Santiago)};
    s.infectionRateIndex = 0;  // rate 2, but only one infection card present
    s.infectionDraw = {city::Atlanta};      // drawn this infect phase
    // Atlanta already saturated with blue.
    s.cubes[city::Atlanta][static_cast<int>(Color::Blue)] = 3;
    s.cubesSupply[static_cast<int>(Color::Blue)] = 21;

    s = applyAction(s, Action::pass());

    CHECK(s.outbreakCount == 1);
    CHECK(s.cubeCount(city::Atlanta, Color::Blue) == 3);  // still 3, not 4
    // Atlanta's neighbors each gained a blue cube.
    for (CityId n : cityInfo(city::Atlanta).neighbors)
        CHECK(s.cubeCount(n, Color::Blue) == 1);
}

TEST_CASE("eradicated disease places no cubes") {
    GameState s = bare();
    s.playerDraw = {Card::cityCard(city::Lima), Card::cityCard(city::Santiago)};
    s.infectionRateIndex = 0;
    s.infectionDraw = {city::Paris};
    s.cures[static_cast<int>(Color::Blue)] = CureStatus::Eradicated;

    s = applyAction(s, Action::pass());
    CHECK(s.cubeCount(city::Paris, Color::Blue) == 0);
}

TEST_CASE("Quarantine Specialist blocks infection in and around her city") {
    GameState s = bare();
    s.players[0].role = RoleType::QuarantineSpecialist;
    s.players[0].location = city::Paris;
    s.playerDraw = {Card::cityCard(city::Lima), Card::cityCard(city::Santiago)};
    s.infectionRateIndex = 0;
    // London is adjacent to Paris -> protected. Sydney is far -> infected.
    s.infectionDraw = {city::Sydney, city::London};

    s = applyAction(s, Action::pass());
    CHECK(s.cubeCount(city::London, Color::Blue) == 0);  // blocked
    CHECK(s.cubeCount(city::Sydney, Color::Red) == 1);   // normal
}
