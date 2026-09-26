#include "doctest.h"
#include "test_helpers.h"

#include "paindemic/agent.h"
#include "paindemic/log.h"

#include <algorithm>

using namespace paindemic;
using namespace pt;

TEST_CASE("event log records player-card draws and infections on a turn-ending Pass") {
    GameState s = newGame({RoleType::Medic, RoleType::Scientist}, 1234, 5);
    EventLog log;
    s = applyAction(s, Action::pass(), &log);

    auto has = [&](EventType t) {
        return std::any_of(log.begin(), log.end(),
                           [&](const Event& e) { return e.type == t; });
    };
    CHECK(has(EventType::ActionPerformed));
    CHECK(has(EventType::PlayerCardDrawn));  // drew 2 player cards
    CHECK(has(EventType::InfectionDrawn));   // infect phase ran
    CHECK(has(EventType::TurnStart));        // passed to next player

    // describe() produces non-empty text for every event.
    for (const Event& e : log) CHECK_FALSE(describe(e).empty());
}

TEST_CASE("logging overload matches the pure overload byte-for-byte") {
    const std::vector<RoleType> roles = {RoleType::Dispatcher, RoleType::Researcher};
    for (unsigned seed = 0; seed < 50; ++seed) {
        GameState a = newGame(roles, seed, 5);
        GameState b = a;  // independent copy

        // Drive both with the same action stream; only one logs.
        std::mt19937 chooser(seed + 1);
        EventLog log;
        for (int step = 0; step < 40 && !isTerminal(a); ++step) {
            auto legal = legalActions(a);
            std::uniform_int_distribution<size_t> pick(0, legal.size() - 1);
            Action act = legal[pick(chooser)];
            a = applyAction(a, act);          // pure
            b = applyAction(b, act, &log);    // logging
            REQUIRE(serialize(a) == serialize(b));
        }
    }
}

TEST_CASE("agents always return a legal action") {
    for (const std::string& name : {std::string("random"), std::string("greedy")}) {
        auto agent = makeAgent(name, 7);
        CHECK(agent->name() == name);

        GameState s = newGame({RoleType::Medic, RoleType::Scientist,
                               RoleType::Dispatcher, RoleType::Researcher}, 3, 5);
        for (int step = 0; step < 200 && !isTerminal(s); ++step) {
            auto legal = legalActions(s);
            REQUIRE_FALSE(legal.empty());
            Action a = agent->chooseAction(s, legal);
            // The chosen action must be one the engine offered.
            CHECK(std::find(legal.begin(), legal.end(), a) != legal.end());
            s = applyAction(s, a);
        }
    }
}

TEST_CASE("makeAgent falls back to random for unknown names") {
    auto agent = makeAgent("does-not-exist", 1);
    CHECK(agent->name() == "random");
}
