// paindemic_driver — run N games with chosen agents and print a full trace:
// the starting configuration, then every action and every hidden reveal.
#include "paindemic/engine.h"
#include "paindemic/agent.h"
#include "paindemic/log.h"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <random>
#include <string>
#include <vector>

using namespace paindemic;

namespace {

struct Options {
    int games = 1;
    unsigned seed = 1;
    std::string agent = "random";
    int players = 4;
    int epidemics = 5;
    long maxTurns = 2000;
    int rollouts = 30;
    int planTurns = 2;
};

// Default role lineup (first `players` entries), avoiding the currently-inert
// Contingency Planner unless the table is full.
const RoleType kDefaultRoles[] = {
    RoleType::Medic, RoleType::Scientist, RoleType::Researcher, RoleType::Dispatcher,
    RoleType::OperationsExpert, RoleType::QuarantineSpecialist, RoleType::ContingencyPlanner};

// The paper's agents play "Restricted Pandemic" with only these four roles.
const RoleType kRestrictedRoles[] = {
    RoleType::Scientist, RoleType::Researcher, RoleType::QuarantineSpecialist, RoleType::Medic};

bool isPaperAgent(const std::string& a) {
    return a == "planner" || a == "planner2" || a == "planner3" || a == "planner4" ||
           a == "heuristic";
}

void printUsage() {
    std::cout <<
        "paindemic_driver [options]\n"
        "  -n, --games N      number of games to run        (default 1)\n"
        "      --seed S       base RNG seed; game i uses S+i (default 1)\n"
        "      --agent NAME   agent for all players: ";
    for (const auto& n : agentNames()) std::cout << n << " ";
    std::cout <<
        "(default random)\n"
        "      --players P    2..4 players                  (default 4)\n"
        "      --epidemics E  epidemics in the deck (4..6)  (default 5)\n"
        "      --rollouts N   planner Monte Carlo samples   (default 30)\n"
        "      --turns N      planner4 look-ahead horizon    (default 2)\n"
        "      --max-turns T  safety cap per game           (default 2000)\n"
        "  -h, --help\n"
        "\nNote: the 'planner', 'planner2', 'planner3', 'planner4', and 'heuristic' agents\n"
        "play Restricted Pandemic (only Scientist/Researcher/Quarantine Specialist/Medic).\n"
        "'planner' uses a 1-turn horizon; 'planner2' a literal 2-turn horizon (its own\n"
        "next turn); 'planner3' re-plans turn 2 inside each rollout with heuristic\n"
        "teammates; 'planner4' plans the next --turns players' turns (the paper's\n"
        "faithful cooperative horizon).\n";
}

// Returns false if parsing should stop the program (help or error).
bool parseArgs(int argc, char** argv, Options& o, int& exitCode) {
    auto needValue = [&](int& i) -> const char* {
        if (i + 1 >= argc) {
            std::cerr << "error: missing value for " << argv[i] << "\n";
            exitCode = 2;
            return nullptr;
        }
        return argv[++i];
    };
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "-h" || arg == "--help") { printUsage(); exitCode = 0; return false; }
        else if (arg == "-n" || arg == "--games") { const char* v = needValue(i); if (!v) return false; o.games = std::atoi(v); }
        else if (arg == "--seed") { const char* v = needValue(i); if (!v) return false; o.seed = static_cast<unsigned>(std::strtoul(v, nullptr, 10)); }
        else if (arg == "--agent") { const char* v = needValue(i); if (!v) return false; o.agent = v; }
        else if (arg == "--players") { const char* v = needValue(i); if (!v) return false; o.players = std::atoi(v); }
        else if (arg == "--epidemics") { const char* v = needValue(i); if (!v) return false; o.epidemics = std::atoi(v); }
        else if (arg == "--rollouts") { const char* v = needValue(i); if (!v) return false; o.rollouts = std::atoi(v); }
        else if (arg == "--turns") { const char* v = needValue(i); if (!v) return false; o.planTurns = std::atoi(v); }
        else if (arg == "--max-turns") { const char* v = needValue(i); if (!v) return false; o.maxTurns = std::atol(v); }
        else { std::cerr << "error: unknown option '" << arg << "'\n"; printUsage(); exitCode = 2; return false; }
    }
    if (o.games < 1) o.games = 1;
    if (o.players < 2) o.players = 2;
    if (o.players > MAX_PLAYERS) o.players = MAX_PLAYERS;
    return true;
}

struct GameResult {
    GameStatus status;
    int curesDiscovered;
};

// Run a single game; returns its outcome and how many cures were discovered.
GameResult runGame(const Options& o, int gameIndex) {
    unsigned seed = o.seed + static_cast<unsigned>(gameIndex);

    // The paper's agents play Restricted Pandemic (four roles only), with a RANDOM
    // distinct subset of those roles each game (the paper averages over all role
    // combinations). The shuffle is seeded from the per-game seed, so the assignment is
    // reproducible per --seed and varies from game to game.
    std::vector<RoleType> roles(static_cast<size_t>(o.players));
    if (isPaperAgent(o.agent)) {
        std::array<RoleType, 4> pool = {kRestrictedRoles[0], kRestrictedRoles[1],
                                        kRestrictedRoles[2], kRestrictedRoles[3]};
        std::mt19937 rolernd(seed * 2654435761u + 0x9e3779b9u);  // decorrelate from deck RNG
        std::shuffle(pool.begin(), pool.end(), rolernd);
        for (int i = 0; i < o.players; ++i)
            roles[static_cast<size_t>(i)] = pool[static_cast<size_t>(i)];
    } else {
        for (int i = 0; i < o.players; ++i)
            roles[static_cast<size_t>(i)] = kDefaultRoles[i];
    }

    // One agent per player. Each agent gets a distinct, reproducible seed.
    std::vector<std::unique_ptr<Agent>> agents;
    for (int i = 0; i < o.players; ++i)
        agents.push_back(makeAgent(o.agent, seed * 1000u + static_cast<unsigned>(i),
                                   o.rollouts, o.planTurns));

    GameState s = newGame(roles, seed, o.epidemics);

    std::cout << "\n================ Game " << (gameIndex + 1)
              << " (seed=" << seed << ", agent=" << o.agent
              << ", players=" << o.players << ", epidemics=" << o.epidemics << ") ================\n";
    std::cout << "Roles:";
    for (int i = 0; i < o.players; ++i)
        std::cout << " P" << i << "=" << roleName(roles[static_cast<size_t>(i)]);
    std::cout << "\n\nStarting configuration:\n" << serialize(s) << "\n";
    std::cout << "-- Turn: P0 (" << roleName(s.cur().role) << ") --\n";

    long turns = 1;
    EventLog log;
    size_t printed = 0;
    while (!isTerminal(s) && turns <= o.maxTurns) {
        Agent& agent = *agents[s.currentPlayer];
        auto legal = legalActions(s);
        if (legal.empty()) break;  // defensive; should never happen while in progress
        Action a = agent.chooseAction(s, legal);
        s = applyAction(s, a, &log);

        for (; printed < log.size(); ++printed) {
            const Event& e = log[printed];
            std::cout << describe(e) << "\n";
            if (e.type == EventType::TurnStart) ++turns;
        }
    }

    int cures = 0;
    for (int k = 0; k < NUM_COLORS; ++k)
        if (s.cures[k] != CureStatus::Uncured) ++cures;

    std::cout << "\nResult: " << (s.status == GameStatus::Won ? "WON"
                                  : s.status == GameStatus::Lost ? "LOST" : "UNFINISHED")
              << " after ~" << turns << " turns, " << cures << "/4 cures discovered.\n";
    return {s.status, cures};
}

} // namespace

int main(int argc, char** argv) {
    Options o;
    int exitCode = 0;
    if (!parseArgs(argc, argv, o, exitCode)) return exitCode;

    int wins = 0, losses = 0, other = 0;
    long totalCures = 0;
    for (int g = 0; g < o.games; ++g) {
        GameResult r = runGame(o, g);
        if (r.status == GameStatus::Won) ++wins;
        else if (r.status == GameStatus::Lost) ++losses;
        else ++other;
        totalCures += r.curesDiscovered;
    }

    std::cout << "\n================ Summary ================\n";
    std::cout << "games=" << o.games << " wins=" << wins << " losses=" << losses;
    if (other) std::cout << " unfinished=" << other;
    std::cout << "  (win rate " << (o.games ? 100.0 * wins / o.games : 0.0) << "%)"
              << "  avg cures/game=" << (o.games ? static_cast<double>(totalCures) / o.games : 0.0)
              << "\n";
    return 0;
}
