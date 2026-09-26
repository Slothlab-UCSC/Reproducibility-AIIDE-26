#include "doctest.h"
#include "test_helpers.h"

#include <algorithm>
#include <random>
#include <set>

using namespace paindemic;
using namespace pt;

namespace {
int epidemicsInDeck(const GameState& s) {
    int n = 0;
    for (const Card& c : s.playerDraw) if (c.kind == CardKind::Epidemic) ++n;
    return n;
}
int sumBytes(const std::vector<uint8_t>& v) {
    int t = 0; for (uint8_t b : v) t += b; return t;
}
} // namespace

TEST_CASE("deck-structure metadata stays consistent through a full game") {
    GameState s = newGame({RoleType::Medic, RoleType::Scientist, RoleType::Researcher}, 2025, 5);
    std::mt19937 chooser(99);

    int guard = 0;
    while (!isTerminal(s)) {
        // Invariants hold at every step.
        REQUIRE(sumBytes(s.infectionBlockSizes) == static_cast<int>(s.infectionDraw.size()));
        REQUIRE(sumBytes(s.playerPileSizes) == static_cast<int>(s.playerDraw.size()));
        REQUIRE(s.playerPileSizes.size() == s.playerPileHasEpidemic.size());
        REQUIRE(sumBytes(s.playerPileHasEpidemic) == epidemicsInDeck(s));

        auto legal = legalActions(s);
        REQUIRE_FALSE(legal.empty());
        std::uniform_int_distribution<size_t> pick(0, legal.size() - 1);
        s = applyAction(s, legal[pick(chooser)]);
        REQUIRE(++guard < 100000);
    }
}

TEST_CASE("epidemic splits the infection deck into blocks") {
    // A controlled state: 3-card infection deck as one block; force an epidemic.
    GameState s = newGame({RoleType::Medic, RoleType::Scientist}, 4, 5);
    size_t before = s.infectionBlockSizes.size();
    // Drive an epidemic by stacking one on top of the player deck and passing.
    s.playerDraw.push_back(Card::cityCard(city::Lima));
    s.playerPileSizes.back() = static_cast<uint8_t>(s.playerPileSizes.back() + 1);
    s.playerDraw.push_back(Card::epidemic());
    s.playerPileSizes.back() = static_cast<uint8_t>(s.playerPileSizes.back() + 1);
    s.playerPileHasEpidemic.back() = 1;

    s = applyAction(s, Action::pass());
    // After intensify there is at least one more block than before, and the
    // size/structure invariant still holds.
    CHECK(s.infectionBlockSizes.size() >= before + 1);
    CHECK(sumBytes(s.infectionBlockSizes) == static_cast<int>(s.infectionDraw.size()));
}

TEST_CASE("determinizeHiddenDecks preserves public information") {
    GameState s = newGame({RoleType::Scientist, RoleType::Researcher}, 17, 5);
    std::mt19937 rng(123);
    GameState d = determinizeHiddenDecks(s, rng);

    // Infection draw: same multiset of cities overall...
    auto sortedInf = [](GameState g) {
        std::sort(g.infectionDraw.begin(), g.infectionDraw.end()); return g.infectionDraw;
    };
    CHECK(sortedInf(s) == sortedInf(d));

    // ...and each block's member set is unchanged (no card crosses a boundary).
    size_t i = 0;
    for (uint8_t b : s.infectionBlockSizes) {
        std::vector<CityId> a(s.infectionDraw.begin() + i, s.infectionDraw.begin() + i + b);
        std::vector<CityId> c(d.infectionDraw.begin() + i, d.infectionDraw.begin() + i + b);
        std::sort(a.begin(), a.end()); std::sort(c.begin(), c.end());
        CHECK(a == c);
        i += b;
    }

    // Player draw: same multiset of city cards and same epidemic count.
    CHECK(d.playerDraw.size() == s.playerDraw.size());
    CHECK(epidemicsInDeck(d) == epidemicsInDeck(s));
    auto sortedCities = [](const GameState& g) {
        std::vector<CityId> v;
        for (const Card& c : g.playerDraw) if (c.kind == CardKind::City) v.push_back(c.city);
        std::sort(v.begin(), v.end()); return v;
    };
    CHECK(sortedCities(d) == sortedCities(s));
    // Board / hands / discards untouched.
    CHECK(serialize(d) == serialize(s));  // serialize ignores deck order
}

TEST_CASE("determinizeHiddenDecks actually varies the draw order") {
    GameState s = newGame({RoleType::Scientist, RoleType::Researcher}, 31, 5);
    std::mt19937 r1(1), r2(2);
    GameState a = determinizeHiddenDecks(s, r1);
    GameState b = determinizeHiddenDecks(s, r2);
    // Two different seeds almost surely produce different infection orders.
    CHECK(a.infectionDraw != b.infectionDraw);

    // The realized top infection card ranges over the whole top block across seeds.
    uint8_t topBlock = s.infectionBlockSizes.back();
    std::set<CityId> tops;
    for (unsigned seed = 0; seed < 500; ++seed) {
        std::mt19937 r(seed);
        GameState d = determinizeHiddenDecks(s, r);
        tops.insert(d.infectionDraw.back());
    }
    // The realized top card ranges over essentially the entire top block (allowing
    // one uncovered card to the coupon-collector tail).
    CHECK(tops.size() >= topBlock - 1);
}
