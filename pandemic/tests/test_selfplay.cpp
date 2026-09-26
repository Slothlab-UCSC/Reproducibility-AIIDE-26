#include "doctest.h"
#include "test_helpers.h"

#include <random>

using namespace paindemic;
using namespace pt;

// Exercises the full agent contract: from newGame, repeatedly enumerate
// legalActions and apply a random one until the game terminates. Across many seeds
// this asserts the engine never crashes, never offers an empty action set while in
// progress, and always reaches a valid terminal state in bounded time.
TEST_CASE("random self-play terminates cleanly across many seeds") {
    const std::vector<RoleType> roles = {
        RoleType::Medic, RoleType::Scientist, RoleType::Dispatcher, RoleType::Researcher};

    int wins = 0, losses = 0;
    for (unsigned seed = 0; seed < 300; ++seed) {
        GameState s = newGame(roles, seed, 5);
        std::mt19937 chooser(seed * 2654435761u + 1u);

        int guard = 0;
        while (!isTerminal(s)) {
            auto acts = legalActions(s);
            REQUIRE_FALSE(acts.empty());  // must always have a move while in progress

            std::uniform_int_distribution<size_t> pick(0, acts.size() - 1);
            s = applyAction(s, acts[pick(chooser)]);

            // Cube + supply conservation must hold at every step.
            for (int col = 0; col < NUM_COLORS; ++col)
                REQUIRE(cubesOfColorOnBoard(s, static_cast<Color>(col)) + s.cubesSupply[col]
                        == CUBES_PER_COLOR);

            REQUIRE(++guard < 100000);  // must terminate in bounded time
        }
        if (s.status == GameStatus::Won) ++wins;
        else ++losses;
    }

    // Every game must have ended decisively.
    CHECK(wins + losses == 300);
    // Sanity: random play almost always loses Pandemic, but it must run.
    CHECK(losses > 0);
    MESSAGE("random self-play: wins=" << wins << " losses=" << losses);
}
