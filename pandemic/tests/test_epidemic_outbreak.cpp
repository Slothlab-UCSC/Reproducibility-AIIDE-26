#include "doctest.h"
#include "test_helpers.h"

using namespace paindemic;
using namespace pt;

namespace {
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
} // namespace

TEST_CASE("epidemic: raises rate, infects the bottom city with 3 cubes, intensifies") {
    GameState s = bare();
    // Draw order (pop_back): Epidemic first, then a harmless city card.
    s.playerDraw = {Card::cityCard(city::Lima), Card::epidemic()};
    s.infectionRateIndex = 0;                       // rate 2
    s.infectionDiscard.clear();
    // Bottom infection card = Lagos (front), top = Paris (back).
    s.infectionDraw = {city::Lagos, city::Paris};

    s = applyAction(s, Action::pass());

    CHECK(s.status == GameStatus::InProgress);
    // Rate stepped up one notch.
    CHECK(s.infectionRateIndex == 1);
    // Epidemic put Lagos to 3 yellow; the intensified deck then drew Lagos again in
    // the infect phase, triggering an outbreak to its neighbors.
    CHECK(s.cubeCount(city::Lagos, Color::Yellow) == 3);
    CHECK(s.outbreakCount == 1);
    for (CityId n : cityInfo(city::Lagos).neighbors)
        CHECK(s.cubeCount(n, Color::Yellow) == 1);
    // Paris (the other infect-phase card) got one blue cube.
    CHECK(s.cubeCount(city::Paris, Color::Blue) == 1);

    // Infection card conservation: all 48 still accounted for.
    CHECK(s.infectionDraw.size() + s.infectionDiscard.size() == 2);
}

TEST_CASE("outbreak chains do not burst a city twice") {
    GameState s = bare();
    s.playerDraw = {Card::cityCard(city::Lima), Card::cityCard(city::Santiago)};
    s.infectionRateIndex = 0;
    s.infectionDraw = {city::Atlanta};  // one infect card this phase

    // Saturate Atlanta and both its blue neighbors so the burst chains.
    s.cubes[city::Atlanta][static_cast<int>(Color::Blue)] = 3;
    s.cubes[city::Chicago][static_cast<int>(Color::Blue)] = 3;
    s.cubes[city::Washington][static_cast<int>(Color::Blue)] = 3;
    s.cubes[city::Miami][static_cast<int>(Color::Blue)] = 3;
    s.cubesSupply[static_cast<int>(Color::Blue)] = CUBES_PER_COLOR - 12;

    s = applyAction(s, Action::pass());

    // Atlanta bursts, chaining to Chicago/Washington/Miami (each already at 3) — but
    // each city bursts at most once in the resolution.
    CHECK(s.outbreakCount == 4);
    CHECK(s.status == GameStatus::InProgress);
}

TEST_CASE("hand-limit forces a discard phase") {
    GameState s = bare();
    // Player 0 already holds 7 distinct cards.
    s.players[0].hand = {city::Tokyo, city::Paris, city::London, city::Cairo,
                         city::Delhi, city::Lima, city::Bogota};
    s.playerDraw = {Card::cityCard(city::Osaka), Card::cityCard(city::Manila)};
    s.infectionDraw = {city::Santiago, city::Lima};  // harmless-ish infect targets

    s = applyAction(s, Action::pass());
    REQUIRE(s.phase == Phase::Discard);
    CHECK(s.discardingPlayer == 0);
    CHECK(s.players[0].hand.size() == 9);

    // Must keep discarding until at the limit.
    auto acts = legalActions(s);
    CHECK_FALSE(acts.empty());
    s = applyAction(s, acts.front());
    CHECK(s.phase == Phase::Discard);
    s = applyAction(s, legalActions(s).front());

    // Down to the limit -> turn resumes and passes to player 1.
    CHECK(s.players[0].hand.size() == HAND_LIMIT);
    CHECK(s.currentPlayer == 1);
    CHECK(s.phase == Phase::PlayerActions);
}
