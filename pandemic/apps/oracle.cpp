// Differential decision oracle.
//
// Reads a corpus of game-state snapshots (the format in state_io.h) framed as:
//
//   IDX <n>
//   <state lines...>
//   PY <python's decision line, ignored here>
//   <blank line>
//
// For each record it reconstructs the GameState, runs the C++ planning agent in
// DETERMINISTIC mode (goals ranked by g+h only — no Monte-Carlo predictor), and prints
// one line capturing the decision and the heuristic breakdown, so an external script can
// diff it against the Python reference's choice on the identical state:
//
//   CPP idx=<n> goal=<survive|cure> action=<tok> nlegal=<k> h=<f>
//       dsurv=<f> dcure=<f> cards=<f> disc=<f> inf=<f> dist=<f> cures=<f>
//
// Sampling is intentionally excluded (deterministic pass); see the harness plan.

#include "paindemic/agent.h"
#include "paindemic/engine.h"
#include "paindemic/heuristic.h"
#include "paindemic/state_io.h"

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace paindemic;

namespace {

const char* colorTok(Color c) {
    switch (c) {
        case Color::Blue:   return "blue";
        case Color::Yellow: return "yellow";
        case Color::Black:  return "black";
        case Color::Red:    return "red";
        default:            return "none";
    }
}

// Canonical action token shared with the Python side (see compare.py).
std::string actionToken(const Action& a) {
    switch (a.type) {
        case ActionType::DriveFerry:    return "drive:" + pyCityName(a.target);
        case ActionType::DirectFlight:  return "direct:" + pyCityName(a.target);
        case ActionType::CharterFlight: return "charter:" + pyCityName(a.target);
        case ActionType::ShuttleFlight: return "shuttle:" + pyCityName(a.target);
        case ActionType::BuildStation:  return "build";
        case ActionType::TreatDisease:  return std::string("treat:") + colorTok(a.color);
        case ActionType::ShareGive:
            return "give:" + std::to_string(a.partner) + ":" + pyCityName(a.card);
        case ActionType::ShareTake:
            return "take:" + std::to_string(a.partner) + ":" + pyCityName(a.card);
        case ActionType::DiscoverCure:  return std::string("cure:") + colorTok(a.color);
        case ActionType::Pass:          return "pass";
        default:                        return "other";
    }
}

void emit(int idx, const std::string& block) {
    GameState s;
    try {
        s = parseState(block);
    } catch (const std::exception& e) {
        std::cout << "CPP idx=" << idx << " error=" << e.what() << "\n";
        return;
    }

    std::vector<Action> legal = legalActions(s);
    HeuristicTerms h = heuristicTerms(s);
    bool cure = plannerPursuesCure(s);

    // Fresh deterministic planner4 per record (no stale plan cache), node cap aligned to
    // the paper's expanded_limit = 3500.
    auto agent = makeAgent("planner4", /*seed=*/1u, /*rollouts=*/1, /*planTurns=*/2,
                           /*deterministic=*/true, /*nodeCap=*/3500);
    std::string action = legal.empty() ? "none" : actionToken(agent->chooseAction(s, legal));

    // Emit WEIGHTED term contributions (raw * eq.8 weight) so they are directly comparable
    // to the Python reference and sum to h. Weights are eq.8 (heuristic.cpp): 0.5 dsurv,
    // 0.5 dcure, 1 cards, 0.5 disc, 0.6 inf, 0.6 dist, 24 cures.
    std::cout << "CPP idx=" << idx
              << " goal=" << (cure ? "cure" : "survive")
              << " action=" << action
              << " nlegal=" << legal.size()
              << " h=" << h.total()
              << " dsurv=" << 0.5 * h.dsurv << " dcure=" << 0.5 * h.dcure
              << " cards=" << 1.0 * h.cards << " disc=" << 0.5 * h.disc
              << " inf=" << 0.6 * h.inf << " dist=" << 0.6 * h.dist
              << " cures=" << 24.0 * h.cures << "\n";
}

} // namespace

int main() {
    std::string line;
    int idx = -1;
    std::ostringstream block;
    bool inRecord = false;

    auto flush = [&] {
        if (inRecord) emit(idx, block.str());
        block.str("");
        block.clear();
        inRecord = false;
    };

    while (std::getline(std::cin, line)) {
        if (line.rfind("IDX ", 0) == 0) {
            flush();
            idx = std::stoi(line.substr(4));
            inRecord = true;
        } else if (line.rfind("PY ", 0) == 0) {
            // Python's decision line — not part of the state; ignore.
        } else if (inRecord) {
            block << line << "\n";
        }
    }
    flush();
    return 0;
}
