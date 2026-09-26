#include "doctest.h"
#include "test_helpers.h"

using namespace paindemic;
using namespace pt;

TEST_CASE("map: 12 cities of each color and symmetric adjacency") {
    int counts[NUM_COLORS] = {0, 0, 0, 0};
    for (CityId c = 0; c < NUM_CITIES; ++c)
        counts[static_cast<int>(cityColor(c))]++;
    for (int col = 0; col < NUM_COLORS; ++col)
        CHECK(counts[col] == 12);

    // Adjacency is symmetric and irreflexive.
    for (CityId a = 0; a < NUM_CITIES; ++a) {
        CHECK_FALSE(areAdjacent(a, a));
        for (CityId b : cityInfo(a).neighbors)
            CHECK(areAdjacent(b, a));
    }
}

TEST_CASE("map: a few known connections") {
    CHECK(areAdjacent(city::Atlanta, city::Chicago));
    CHECK(areAdjacent(city::Atlanta, city::Miami));
    CHECK(areAdjacent(city::SanFrancisco, city::Tokyo));   // trans-Pacific
    CHECK(areAdjacent(city::Sydney, city::LosAngeles));
    CHECK_FALSE(areAdjacent(city::Atlanta, city::Paris));
}

TEST_CASE("setup: cube conservation and initial infections") {
    GameState s = newGame({RoleType::Medic, RoleType::Scientist}, 1234, 5);

    // 9 initial infection cards placed 3+3+3 cubes at 3/2/1 each = 18 cubes.
    CHECK(totalCubesOnBoard(s) == 18);

    // Supply + board cubes == 24 per color (conservation).
    for (int col = 0; col < NUM_COLORS; ++col) {
        int onBoard = cubesOfColorOnBoard(s, static_cast<Color>(col));
        CHECK(onBoard + s.cubesSupply[col] == CUBES_PER_COLOR);
    }
    CHECK(s.infectionDiscard.size() == 9);
}

TEST_CASE("setup: stations, hands, decks") {
    GameState s = newGame({RoleType::Medic, RoleType::Scientist, RoleType::Researcher}, 7, 5);

    CHECK(s.stationCount == 1);
    CHECK(s.hasStation(STARTING_CITY));

    // 3 players -> 3 cards each.
    for (const Player& p : s.players) {
        CHECK(p.hand.size() == 3);
        CHECK(p.location == STARTING_CITY);
    }

    // Player deck = 48 cities - dealt (9) + 5 epidemics = 44.
    int epidemics = 0;
    for (const Card& c : s.playerDraw)
        if (c.kind == CardKind::Epidemic) ++epidemics;
    CHECK(epidemics == 5);
    CHECK(s.playerDraw.size() == static_cast<size_t>(48 - 9 + 5));

    // Infection deck started at 48, 9 drawn -> 39 remain.
    CHECK(s.infectionDraw.size() == 39);
}

TEST_CASE("setup: reproducible from seed, independent from clones") {
    GameState a = newGame({RoleType::Medic, RoleType::Scientist}, 99, 5);
    GameState b = newGame({RoleType::Medic, RoleType::Scientist}, 99, 5);
    CHECK(serialize(a) == serialize(b));

    GameState c = a;                 // copy
    auto acts = legalActions(a);
    a = applyAction(a, acts.front());
    CHECK(serialize(c) != serialize(a));  // original clone untouched
}
