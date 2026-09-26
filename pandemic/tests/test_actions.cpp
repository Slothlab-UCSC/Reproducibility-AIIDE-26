#include "doctest.h"
#include "test_helpers.h"

using namespace paindemic;
using namespace pt;

namespace {
// A controlled state with two players in Atlanta and 4 actions to spend. Decks are
// left empty on purpose; tests must not end the turn (which would draw).
GameState controlled(RoleType r0 = RoleType::Scientist, RoleType r1 = RoleType::Researcher) {
    GameState s;
    s.cubesSupply.fill(CUBES_PER_COLOR);
    s.cures.fill(CureStatus::Uncured);
    s.players = {Player{r0, STARTING_CITY, {}}, Player{r1, STARTING_CITY, {}}};
    s.stations[STARTING_CITY] = true;
    s.stationCount = 1;
    s.currentPlayer = 0;
    s.actionsRemaining = 4;
    s.phase = Phase::PlayerActions;
    return s;
}
} // namespace

TEST_CASE("DriveFerry moves to adjacent cities only") {
    GameState s = controlled();
    auto acts = legalActions(s);
    // Atlanta neighbors: Chicago, Washington, Miami.
    CHECK(countActionType(acts, ActionType::DriveFerry) == 3);

    s = applyAction(s, Action::drive(city::Miami));
    CHECK(s.cur().location == city::Miami);
    CHECK(s.actionsRemaining == 3);
}

TEST_CASE("DirectFlight discards the destination card") {
    GameState s = controlled();
    s.players[0].hand = {city::Tokyo, city::Paris};
    auto acts = legalActions(s);
    const Action* a = findAction(acts, ActionType::DirectFlight);
    REQUIRE(a != nullptr);

    Action fly; fly.type = ActionType::DirectFlight; fly.target = city::Tokyo; fly.card = city::Tokyo;
    s = applyAction(s, fly);
    CHECK(s.cur().location == city::Tokyo);
    CHECK_FALSE(s.cur().hasCityCard(city::Tokyo));
    CHECK(s.cur().hasCityCard(city::Paris));
}

TEST_CASE("CharterFlight discards current-city card and flies anywhere") {
    GameState s = controlled();
    s.players[0].hand = {city::Atlanta};
    auto acts = legalActions(s);
    // 47 possible destinations.
    CHECK(countActionType(acts, ActionType::CharterFlight) == NUM_CITIES - 1);

    Action a; a.type = ActionType::CharterFlight; a.target = city::Sydney; a.card = city::Atlanta;
    s = applyAction(s, a);
    CHECK(s.cur().location == city::Sydney);
    CHECK(s.cur().hand.empty());
}

TEST_CASE("ShuttleFlight requires stations at both ends") {
    GameState s = controlled();
    CHECK(countActionType(legalActions(s), ActionType::ShuttleFlight) == 0);  // only Atlanta

    s.stations[city::Tokyo] = true;
    s.stationCount = 2;
    auto acts = legalActions(s);
    CHECK(countActionType(acts, ActionType::ShuttleFlight) == 1);
    Action a; a.type = ActionType::ShuttleFlight; a.target = city::Tokyo;
    s = applyAction(s, a);
    CHECK(s.cur().location == city::Tokyo);
}

TEST_CASE("BuildStation costs the current-city card (non-Ops)") {
    GameState s = controlled();
    s.players[0].location = city::Paris;
    s.players[0].hand = {city::Paris};
    REQUIRE(hasActionType(legalActions(s), ActionType::BuildStation));
    s = applyAction(s, Action::build());
    CHECK(s.hasStation(city::Paris));
    CHECK(s.stationCount == 2);
    CHECK(s.cur().hand.empty());
}

TEST_CASE("BuildStation without card is illegal for non-Ops") {
    GameState s = controlled();
    s.players[0].location = city::Paris;  // no Paris card
    CHECK_FALSE(hasActionType(legalActions(s), ActionType::BuildStation));
}

TEST_CASE("TreatDisease removes one cube (uncured)") {
    GameState s = controlled();
    s.cubes[city::Atlanta][static_cast<int>(Color::Blue)] = 2;
    s.cubesSupply[static_cast<int>(Color::Blue)] = 22;

    s = applyAction(s, Action::treat(Color::Blue));
    CHECK(s.cubeCount(city::Atlanta, Color::Blue) == 1);
    CHECK(s.cubesSupply[static_cast<int>(Color::Blue)] == 23);
}

TEST_CASE("TreatDisease removes all cubes when cured") {
    GameState s = controlled();
    s.cures[static_cast<int>(Color::Blue)] = CureStatus::Cured;
    s.cubes[city::Atlanta][static_cast<int>(Color::Blue)] = 3;
    s.cubesSupply[static_cast<int>(Color::Blue)] = 21;

    s = applyAction(s, Action::treat(Color::Blue));
    CHECK(s.cubeCount(city::Atlanta, Color::Blue) == 0);
    CHECK(s.cubesSupply[static_cast<int>(Color::Blue)] == CUBES_PER_COLOR);
    // Cured + zero cubes on board -> eradicated.
    CHECK(s.cures[static_cast<int>(Color::Blue)] == CureStatus::Eradicated);
}

TEST_CASE("ShareKnowledge give/take the current-city card") {
    GameState s = controlled(RoleType::Scientist, RoleType::Medic);
    s.players[0].hand = {city::Atlanta};

    auto acts = legalActions(s);
    const Action* give = findAction(acts, ActionType::ShareGive);
    REQUIRE(give != nullptr);
    CHECK(give->card == city::Atlanta);

    s = applyAction(s, *give);
    CHECK_FALSE(s.players[0].hasCityCard(city::Atlanta));
    CHECK(s.players[1].hasCityCard(city::Atlanta));
}

TEST_CASE("DiscoverCure needs 5 same-color cards at a station") {
    GameState s = controlled(RoleType::Medic);  // not Scientist -> needs 5
    // A stray blue cube on the board so the cure isn't instantly eradicated.
    s.cubes[city::London][static_cast<int>(Color::Blue)] = 1;
    s.cubesSupply[static_cast<int>(Color::Blue)] = CUBES_PER_COLOR - 1;
    // 5 blue city cards (all blue cities).
    s.players[0].hand = {city::Atlanta, city::Chicago, city::Montreal,
                         city::NewYork, city::Washington};
    REQUIRE(hasActionType(legalActions(s), ActionType::DiscoverCure));

    Action a; a.type = ActionType::DiscoverCure; a.color = Color::Blue;
    s = applyAction(s, a);
    CHECK(s.cures[static_cast<int>(Color::Blue)] == CureStatus::Cured);
    CHECK(s.cur().hand.empty());
}

TEST_CASE("legalActions is never empty while in progress") {
    GameState s = controlled();
    CHECK_FALSE(legalActions(s).empty());  // at minimum, Pass + drives
}
