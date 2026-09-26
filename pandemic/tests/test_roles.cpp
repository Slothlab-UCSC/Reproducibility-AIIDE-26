#include "doctest.h"
#include "test_helpers.h"

using namespace paindemic;
using namespace pt;

namespace {
GameState controlled(RoleType r0, RoleType r1 = RoleType::Scientist) {
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

TEST_CASE("Medic auto-removes cured-disease cubes upon entering a city") {
    GameState s = controlled(RoleType::Medic);
    s.cures[static_cast<int>(Color::Blue)] = CureStatus::Cured;
    s.cubes[city::Chicago][static_cast<int>(Color::Blue)] = 3;
    s.cubesSupply[static_cast<int>(Color::Blue)] = CUBES_PER_COLOR - 3;

    s = applyAction(s, Action::drive(city::Chicago));
    CHECK(s.cur().location == city::Chicago);
    CHECK(s.cubeCount(city::Chicago, Color::Blue) == 0);  // swept on arrival
    CHECK(s.cubesSupply[static_cast<int>(Color::Blue)] == CUBES_PER_COLOR);
}

TEST_CASE("Scientist cures with only 4 cards") {
    GameState s = controlled(RoleType::Scientist);
    // A stray blue cube on the board so the cure isn't instantly eradicated.
    s.cubes[city::London][static_cast<int>(Color::Blue)] = 1;
    s.cubesSupply[static_cast<int>(Color::Blue)] = CUBES_PER_COLOR - 1;
    s.players[0].hand = {city::Atlanta, city::Chicago, city::Montreal, city::NewYork};
    REQUIRE(hasActionType(legalActions(s), ActionType::DiscoverCure));
    Action a; a.type = ActionType::DiscoverCure; a.color = Color::Blue;
    s = applyAction(s, a);
    CHECK(s.cures[static_cast<int>(Color::Blue)] == CureStatus::Cured);
}

TEST_CASE("Researcher may give any card from hand") {
    GameState s = controlled(RoleType::Researcher, RoleType::Medic);
    // Researcher in Atlanta holding a non-Atlanta card.
    s.players[0].hand = {city::Tokyo};
    auto acts = legalActions(s);
    const Action* give = findAction(acts, ActionType::ShareGive);
    REQUIRE(give != nullptr);
    CHECK(give->card == city::Tokyo);  // can give Tokyo despite being in Atlanta

    s = applyAction(s, *give);
    CHECK(s.players[1].hasCityCard(city::Tokyo));
}

TEST_CASE("Operations Expert builds without discarding a card") {
    GameState s = controlled(RoleType::OperationsExpert);
    s.players[0].location = city::Paris;  // no Paris card in hand
    REQUIRE(hasActionType(legalActions(s), ActionType::BuildStation));
    s = applyAction(s, Action::build());
    CHECK(s.hasStation(city::Paris));
    CHECK(s.stationCount == 2);
}

TEST_CASE("Operations Expert special flight from a station, once per turn") {
    GameState s = controlled(RoleType::OperationsExpert);
    s.players[0].hand = {city::Tokyo};  // any card works as the discard
    auto acts = legalActions(s);
    const Action* fly = findAction(acts, ActionType::OperationsFlight);
    REQUIRE(fly != nullptr);

    s = applyAction(s, *fly);
    CHECK(s.opsFlightUsedThisTurn);
    // No longer offered this turn.
    CHECK_FALSE(hasActionType(legalActions(s), ActionType::OperationsFlight));
}

TEST_CASE("Dispatcher can summon one pawn to another and drive any pawn") {
    GameState s = controlled(RoleType::Dispatcher);
    s.players[1].location = city::Tokyo;

    auto acts = legalActions(s);
    REQUIRE(hasActionType(acts, ActionType::DispatcherSummon));
    REQUIRE(hasActionType(acts, ActionType::DispatcherMovePawn));

    // Summon player 1 (Tokyo) to player 0's city (Atlanta).
    const Action* summon = findAction(acts, ActionType::DispatcherSummon);
    s = applyAction(s, *summon);
    bool someoneMoved = (s.players[1].location == city::Atlanta) ||
                        (s.players[0].location == city::Tokyo);
    CHECK(someoneMoved);
}
