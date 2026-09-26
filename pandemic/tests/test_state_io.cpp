#include "doctest.h"
#include "test_helpers.h"

#include "paindemic/state_io.h"
#include "paindemic/heuristic.h"

#include <random>

using namespace paindemic;
using namespace pt;

namespace {

// Advance a fresh game by a handful of random legal actions so the snapshot has cubes,
// a non-trivial hand, maybe a station, and a populated discard pile to round-trip.
GameState evolved(unsigned seed, int steps) {
    GameState s = newGame({RoleType::Scientist, RoleType::Researcher}, seed, 4);
    std::mt19937 rng(seed);
    for (int i = 0; i < steps && s.status == GameStatus::InProgress; ++i) {
        auto legal = legalActions(s);
        if (legal.empty()) break;
        std::uniform_int_distribution<size_t> pick(0, legal.size() - 1);
        s = applyAction(s, legal[pick(rng)]);
    }
    return s;
}

} // namespace

TEST_CASE("writeState/parseState round-trips the carried fields") {
    for (unsigned seed = 1; seed <= 20; ++seed) {
        GameState s = evolved(seed, static_cast<int>(seed) % 12);
        if (s.phase != Phase::PlayerActions) continue;  // snapshots are action-phase states

        std::string a = writeState(s);
        GameState r = parseState(a);
        std::string b = writeState(r);
        CHECK(a == b);  // text is a fixed point of write∘parse
    }
}

TEST_CASE("parseState reconstructs a state with the same legal moves and heuristic") {
    GameState s = evolved(7, 9);
    if (s.phase == Phase::PlayerActions) {
        GameState r = parseState(writeState(s));

        // Same number of legal actions (the deterministic decision depends on this).
        CHECK(legalActions(r).size() == legalActions(s).size());

        // Heuristic terms that don't depend on the (omitted) deck order/identity match
        // exactly; h_dist depends on playerDraw.size() which we carry, so it matches too.
        HeuristicTerms hs = heuristicTerms(s), hr = heuristicTerms(r);
        CHECK(hr.dsurv == doctest::Approx(hs.dsurv));
        CHECK(hr.dcure == doctest::Approx(hs.dcure));
        CHECK(hr.cards == doctest::Approx(hs.cards));
        CHECK(hr.disc == doctest::Approx(hs.disc));
        CHECK(hr.inf == doctest::Approx(hs.inf));
        CHECK(hr.dist == doctest::Approx(hs.dist));
        CHECK(hr.cures == doctest::Approx(hs.cures));
    }
}

TEST_CASE("city name mapping is a clean bijection in the Python convention") {
    for (CityId c = 0; c < NUM_CITIES; ++c)
        CHECK(cityFromPyName(pyCityName(c)) == c);
    CHECK(pyCityName(NO_CITY) == "none");
    CHECK(cityFromPyName("not_a_city") == NO_CITY);
}
