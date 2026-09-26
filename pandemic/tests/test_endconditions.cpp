#include "doctest.h"
#include "test_helpers.h"

using namespace paindemic;
using namespace pt;

namespace {
GameState bare(RoleType r0 = RoleType::Scientist) {
    GameState s;
    s.cubesSupply.fill(CUBES_PER_COLOR);
    s.cures.fill(CureStatus::Uncured);
    s.players = {Player{r0, STARTING_CITY, {}}, Player{RoleType::Researcher, STARTING_CITY, {}}};
    s.stations[STARTING_CITY] = true;
    s.stationCount = 1;
    s.currentPlayer = 0;
    s.actionsRemaining = 4;
    s.phase = Phase::PlayerActions;
    return s;
}
} // namespace

TEST_CASE("WIN: curing the fourth disease wins the game") {
    GameState s = bare(RoleType::Medic);  // needs 5
    s.cures[static_cast<int>(Color::Blue)] = CureStatus::Cured;
    s.cures[static_cast<int>(Color::Yellow)] = CureStatus::Cured;
    s.cures[static_cast<int>(Color::Black)] = CureStatus::Cured;
    // 5 red cards at a station.
    s.players[0].hand = {city::Beijing, city::Seoul, city::Shanghai, city::Tokyo, city::Osaka};

    Action a; a.type = ActionType::DiscoverCure; a.color = Color::Red;
    s = applyAction(s, a);
    CHECK(s.status == GameStatus::Won);
}

TEST_CASE("LOSS: the eighth outbreak loses the game") {
    GameState s = bare();
    s.outbreakCount = 7;
    s.playerDraw = {Card::cityCard(city::Lima), Card::cityCard(city::Santiago)};
    s.infectionRateIndex = 0;
    s.infectionDraw = {city::Atlanta};
    s.cubes[city::Atlanta][static_cast<int>(Color::Blue)] = 3;  // next cube bursts
    s.cubesSupply[static_cast<int>(Color::Blue)] = CUBES_PER_COLOR - 3;

    s = applyAction(s, Action::pass());
    CHECK(s.outbreakCount == MAX_OUTBREAKS);
    CHECK(s.status == GameStatus::Lost);
}

TEST_CASE("LOSS: running out of cubes of a color loses the game") {
    GameState s = bare();
    s.playerDraw = {Card::cityCard(city::Lima), Card::cityCard(city::Santiago)};
    s.infectionRateIndex = 0;
    s.infectionDraw = {city::Paris};
    s.cubesSupply[static_cast<int>(Color::Blue)] = 0;  // none left to place

    s = applyAction(s, Action::pass());
    CHECK(s.status == GameStatus::Lost);
}

TEST_CASE("LOSS: exhausting the player deck loses the game") {
    GameState s = bare();
    s.playerDraw.clear();  // cannot draw 2 at end of turn
    s.infectionDraw = {city::Lima, city::Santiago};

    s = applyAction(s, Action::pass());
    CHECK(s.status == GameStatus::Lost);
}
