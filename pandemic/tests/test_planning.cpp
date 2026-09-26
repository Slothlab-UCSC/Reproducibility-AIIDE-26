#include "doctest.h"
#include "test_helpers.h"

#include "paindemic/agent.h"
#include "paindemic/heuristic.h"
#include "paindemic/map_data.h"

#include <algorithm>

using namespace paindemic;
using namespace pt;

TEST_CASE("baseDistance is a valid metric on the board") {
    CHECK(baseDistance(city::Atlanta, city::Atlanta) == 0);
    CHECK(baseDistance(city::Atlanta, city::Chicago) == 1);     // adjacent
    CHECK(baseDistance(city::Atlanta, city::Miami) == 1);
    // Symmetry + triangle-ish sanity on a known longer hop.
    CHECK(baseDistance(city::Atlanta, city::Sydney) == baseDistance(city::Sydney, city::Atlanta));
    CHECK(baseDistance(city::Atlanta, city::Sydney) > 1);
}

TEST_CASE("stepAction does not draw or infect; resolveTurnEnd does") {
    GameState s = newGame({RoleType::Medic, RoleType::Scientist}, 2024, 5);
    size_t deck0 = s.playerDraw.size();
    size_t inf0 = s.infectionDraw.size();
    int cubes0 = totalCubesOnBoard(s);

    // A non-turn-ending action: decks and cubes untouched, still in the action phase.
    s = stepAction(s, Action::drive(city::Miami));
    CHECK(s.cur().location == city::Miami);
    CHECK(s.actionsRemaining == ACTIONS_PER_TURN - 1);
    CHECK(s.playerDraw.size() == deck0);
    CHECK(s.infectionDraw.size() == inf0);
    CHECK(totalCubesOnBoard(s) == cubes0);
    CHECK(s.phase == Phase::PlayerActions);

    // Ending the turn via stepAction stops at the pre-draw boundary (no draws yet).
    GameState atDraw = stepAction(s, Action::pass());
    CHECK(atDraw.phase == Phase::Draw);
    CHECK(atDraw.playerDraw.size() == deck0);
    CHECK(atDraw.infectionDraw.size() == inf0);

    // resolveTurnEnd performs the stochastic phases and passes the turn.
    GameState next = resolveTurnEnd(atDraw);
    if (next.status == GameStatus::InProgress) {
        CHECK(next.currentPlayer == 1);
        CHECK(next.playerDraw.size() == deck0 - 2);  // drew two player cards
    }
    // Cube conservation holds regardless.
    for (int k = 0; k < NUM_COLORS; ++k)
        CHECK(cubesOfColorOnBoard(next, static_cast<Color>(k)) + next.cubesSupply[k]
              == CUBES_PER_COLOR);
}

TEST_CASE("heuristic rewards progress toward winning") {
    GameState base = newGame({RoleType::Scientist, RoleType::Researcher}, 5, 5);

    // Discovering a cure must lower the heuristic (h_cures dominates with weight 24).
    GameState cured = base;
    cured.cures[static_cast<int>(Color::Blue)] = CureStatus::Cured;
    CHECK(evaluateState(cured) < evaluateState(base));
    CHECK(heuristicTerms(cured).cures == heuristicTerms(base).cures - 1);

    // Fewer cubes on the board is better, all else equal.
    GameState fewerCubes = base;
    for (CityId c = 0; c < NUM_CITIES; ++c)
        for (int k = 0; k < NUM_COLORS; ++k)
            fewerCubes.cubes[static_cast<size_t>(c)][k] = 0;
    fewerCubes.cubesSupply.fill(CUBES_PER_COLOR);
    CHECK(heuristicTerms(fewerCubes).inf < heuristicTerms(base).inf);
}

TEST_CASE("advanceTurnSkippingDraws gives the same player a fresh turn, untouched board") {
    GameState s = newGame({RoleType::Scientist, RoleType::Medic}, 77, 5);
    GameState atDraw = stepAction(s, Action::pass());
    REQUIRE(atDraw.phase == Phase::Draw);

    GameState next = advanceTurnSkippingDraws(atDraw);
    CHECK(next.phase == Phase::PlayerActions);
    CHECK(next.actionsRemaining == ACTIONS_PER_TURN);
    CHECK(next.currentPlayer == atDraw.currentPlayer);     // same player, not the next
    CHECK(next.playerDraw.size() == s.playerDraw.size());  // no cards drawn
    CHECK(totalCubesOnBoard(next) == totalCubesOnBoard(s)); // no infections
}

TEST_CASE("advanceToNextPlayerSkippingDraws rotates to the next player, untouched board") {
    GameState s = newGame({RoleType::Scientist, RoleType::Medic, RoleType::Researcher}, 51, 5);
    GameState atDraw = stepAction(s, Action::pass());
    REQUIRE(atDraw.phase == Phase::Draw);

    GameState next = advanceToNextPlayerSkippingDraws(atDraw);
    CHECK(next.phase == Phase::PlayerActions);
    CHECK(next.actionsRemaining == ACTIONS_PER_TURN);
    CHECK(next.currentPlayer ==
          (atDraw.currentPlayer + 1) % atDraw.players.size());   // next player, not the same
    CHECK(next.playerDraw.size() == s.playerDraw.size());        // no cards drawn
    CHECK(totalCubesOnBoard(next) == totalCubesOnBoard(s));      // no infections
}

TEST_CASE("heuristic and planner agents return legal actions and terminate") {
    for (const std::string& name : {std::string("heuristic"), std::string("planner"),
                                    std::string("planner2"), std::string("planner3"),
                                    std::string("planner4")}) {
        auto agent = makeAgent(name, 11, /*rollouts=*/4);
        CHECK(agent->name() == name);

        GameState s = newGame({RoleType::Scientist, RoleType::Medic}, 1, 5);
        int guard = 0;
        while (!isTerminal(s)) {
            auto legal = legalActions(s);
            REQUIRE_FALSE(legal.empty());
            Action a = agent->chooseAction(s, legal);
            CHECK(std::find(legal.begin(), legal.end(), a) != legal.end());
            s = applyAction(s, a);
            REQUIRE(++guard < 100000);
        }
        CHECK((s.status == GameStatus::Won || s.status == GameStatus::Lost));
    }
}

TEST_CASE("planner3 is deterministic for a fixed seed") {
    auto playOut = [](unsigned seed) {
        auto agent = makeAgent("planner3", seed, /*rollouts=*/6);
        GameState s = newGame({RoleType::Scientist, RoleType::Medic}, 3, 4);
        std::vector<Action> trace;
        int guard = 0;
        while (!isTerminal(s)) {
            auto legal = legalActions(s);
            Action a = agent->chooseAction(s, legal);
            trace.push_back(a);
            s = applyAction(s, a);
            REQUIRE(++guard < 100000);
        }
        return trace;
    };
    // Same seed twice -> identical move sequence (coupled rollouts reseed per rollout).
    CHECK(playOut(42) == playOut(42));
}

TEST_CASE("planner4 is deterministic for a fixed seed") {
    auto playOut = [](unsigned seed) {
        auto agent = makeAgent("planner4", seed, /*rollouts=*/6, /*planTurns=*/2);
        GameState s = newGame({RoleType::Scientist, RoleType::Medic}, 3, 4);
        std::vector<Action> trace;
        int guard = 0;
        while (!isTerminal(s)) {
            auto legal = legalActions(s);
            Action a = agent->chooseAction(s, legal);
            trace.push_back(a);
            s = applyAction(s, a);
            REQUIRE(++guard < 100000);
        }
        return trace;
    };
    CHECK(playOut(42) == playOut(42));
}
