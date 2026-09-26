#include "paindemic/agent.h"
#include "paindemic/engine.h"
#include "paindemic/heuristic.h"
#include "paindemic/map_data.h"

#include <algorithm>
#include <deque>
#include <queue>
#include <random>
#include <unordered_set>

namespace paindemic {
namespace {

// Uniform random choice over the legal moves.
class RandomAgent : public Agent {
public:
    explicit RandomAgent(unsigned seed) : rng_(seed) {}
    std::string name() const override { return "random"; }
    Action chooseAction(const GameState&, const std::vector<Action>& legal) override {
        std::uniform_int_distribution<size_t> pick(0, legal.size() - 1);
        return legal[pick(rng_)];
    }
private:
    std::mt19937 rng_;
};

// A naive baseline heuristic: score each legal action and take the best, breaking
// ties randomly. Intentionally simple — a starting point for stronger agents.
class GreedyAgent : public Agent {
public:
    explicit GreedyAgent(unsigned seed) : rng_(seed) {}
    std::string name() const override { return "greedy"; }

    Action chooseAction(const GameState& s, const std::vector<Action>& legal) override {
        CityId here = s.cur().location;

        double best = -1e18;
        std::vector<const Action*> bestActions;
        for (const Action& a : legal) {
            double score = scoreAction(s, here, a);
            if (score > best + 1e-9) {
                best = score;
                bestActions = {&a};
            } else if (score > best - 1e-9) {
                bestActions.push_back(&a);
            }
        }
        std::uniform_int_distribution<size_t> pick(0, bestActions.size() - 1);
        return *bestActions[pick(rng_)];
    }

private:
    std::mt19937 rng_;

    // Total cubes of any color sitting in a city.
    static int cubesIn(const GameState& s, CityId c) {
        int t = 0;
        for (int col = 0; col < NUM_COLORS; ++col)
            t += s.cubes[static_cast<size_t>(c)][col];
        return t;
    }

    double scoreAction(const GameState& s, CityId here, const Action& a) const {
        switch (a.type) {
            case ActionType::DiscoverCure:
                return 1000.0;  // winning the game runs through cures
            case ActionType::TreatDisease:
                // Prefer treating where the most cubes are (current city).
                return 100.0 + s.cubeCount(here, a.color);
            case ActionType::BuildStation:
                // Useful early; mild incentive while stations are scarce.
                return 60.0 - 5.0 * s.stationCount;
            case ActionType::DriveFerry:
            case ActionType::ShuttleFlight:
            case ActionType::CharterFlight:
            case ActionType::DirectFlight:
            case ActionType::OperationsFlight:
                // Move toward cubes: reward destinations that need treating.
                return 10.0 + 3.0 * cubesIn(s, a.target);
            case ActionType::ShareGive:
            case ActionType::ShareTake:
                return 5.0;   // mild: helps assemble cure sets
            case ActionType::DispatcherSummon:
            case ActionType::DispatcherMovePawn:
                return 4.0 + 3.0 * cubesIn(s, a.target);
            case ActionType::Pass:
                return -1.0;  // last resort
            default:
                return 0.0;
        }
    }
};

// --- Paper agents (Sauma-Chacón & Eger, AIIDE-20) -----------------------------

int cureReq(RoleType r) { return r == RoleType::Scientist ? 4 : 5; }

// Card-distance metric used by the paper's MCTSModeling.predict (Heuristics.py): for a
// single player, sum over ALL colors of |R - held|, R = cure requirement. This differs
// from the heuristic's h_cards term, which clamps at 0 (no overshoot penalty), skips
// cured colors, and minimizes across players. predict measures only the planning player
// and penalizes overshoot, so it is kept as its own helper.
double cardDistance(const GameState& s, int playerIdx) {
    const Player& p = s.players[static_cast<size_t>(playerIdx)];
    int R = cureReq(p.role);
    double d = 0.0;
    for (int k = 0; k < NUM_COLORS; ++k) {
        int diff = R - p.colorCount(static_cast<Color>(k));
        d += diff < 0 ? -diff : diff;
    }
    return d;
}

// Paper MCTSModeling.predict term weights (Heuristics.py: wCards, wDiseases, wDiscard).
constexpr double PRED_W_CARDS    = 1.0;
constexpr double PRED_W_DISEASES = 0.6;
constexpr double PRED_W_DISCARD  = 6.0;  // applied to (expected overflow / 12)

int discoveredCures(const GameState& s) {
    int n = 0;
    for (int k = 0; k < NUM_COLORS; ++k)
        if (s.cures[k] != CureStatus::Uncured) ++n;
    return n;
}

// Station-aware shortest distance between two cities, mirroring the heuristic's
// Distances::between and the paper's calculate_distances: any two research stations are
// one shuttle hop apart, so the trip may be cheaper via the nearest stations.
int cityDistance(const GameState& s, CityId a, CityId b) {
    int d = baseDistance(a, b);
    if (s.stationCount >= 2) {
        int na = 1000, nb = 1000;
        for (CityId c = 0; c < NUM_CITIES; ++c)
            if (s.hasStation(c)) {
                na = std::min(na, baseDistance(a, c));
                nb = std::min(nb, baseDistance(b, c));
            }
        d = std::min(d, na + 1 + nb);
    }
    return d;
}

// Does `p` hold a card of `color` they could legally hand to a co-located teammate? In
// Restricted Pandemic a card may be given only if it names the giver's current city, or
// the giver is the Researcher (who may give any card). Mirrors the paper's
// `card.name==p.position or p.playerrole==RESEARCHER` test.
bool playerCanGiveColor(const Player& p, Color color) {
    bool researcher = p.role == RoleType::Researcher;
    for (CityId c : p.hand)
        if (cityColor(c) == color && (researcher || c == p.location))
            return true;
    return false;
}

// The paper's goal_heuristic_chooser (Players.py): pursue the discover-cure goal when,
// for some color, EITHER (a) the current player already holds enough cards to cure it,
// (b) the player is one card short and a teammate within distance 4 can hand over the
// missing card, or (c) the player can hand a card to a teammate who is one short of
// curing it. Cases (b)/(c) are the cooperative hand-off setups our old single-case
// trigger missed. Otherwise the agent pursues the survive goal.
bool wantsCureGoal(const GameState& s) {
    const Player& me = s.cur();
    const int reqMe = cureReq(me.role);
    for (int k = 0; k < NUM_COLORS; ++k) {
        const Color color = static_cast<Color>(k);
        const int cnt = me.colorCount(color);
        if (cnt >= reqMe) return true;  // (a) I can cure this color myself

        if (cnt == reqMe - 1) {
            // (b) a teammate within 4 holds (and can give) the one card I still need.
            for (size_t pi = 0; pi < s.players.size(); ++pi) {
                if (pi == s.currentPlayer) continue;
                const Player& p = s.players[pi];
                if (p.colorCount(color) > 0 &&
                    cityDistance(s, p.location, me.location) <= 4 &&
                    playerCanGiveColor(p, color))
                    return true;
            }
        } else if (cnt > 0) {
            // (c) I can give a card to a teammate within 4 who is one short of curing.
            for (size_t pi = 0; pi < s.players.size(); ++pi) {
                if (pi == s.currentPlayer) continue;
                const Player& p = s.players[pi];
                if (p.colorCount(color) == cureReq(p.role) - 1 &&
                    cityDistance(s, p.location, me.location) <= 4 &&
                    playerCanGiveColor(me, color))
                    return true;
            }
        }
    }
    return false;
}

// Greedy pick minimizing eq.8 on the deterministic next state. Shared by the
// heuristic agent and as the planner's fallback.
Action greedyHeuristicChoice(const GameState& s, const std::vector<Action>& legal,
                             std::mt19937& rng) {
    double best = 1e300;
    std::vector<const Action*> ties;
    for (const Action& a : legal) {
        double score = evaluateState(stepAction(s, a));
        if (score < best - 1e-9) { best = score; ties = {&a}; }
        else if (score < best + 1e-9) ties.push_back(&a);
    }
    std::uniform_int_distribution<size_t> pick(0, ties.size() - 1);
    return *ties[pick(rng)];
}

// The planner never *chooses* to forfeit actions: like the paper's available_actions
// (Game.py, which has no no_action), Pass is excluded from A* expansion so a turn ends only
// by spending all four actions. Pass remains a real engine move for play/greedy.
std::vector<Action> planExpandActions(const GameState& s) {
    std::vector<Action> a = legalActions(s);
    a.erase(std::remove_if(a.begin(), a.end(),
                [](const Action& x) { return x.type == ActionType::Pass; }),
            a.end());
    return a;
}

// Play out one full turn for the current player with the greedy eq.8 policy, then
// resolve their draw/infect. Used to model "other players" as vaguely-useful (rather
// than skipped or passing) inside planner3's coupled rollouts. `rng` drives only the
// heuristic tie-breaking; the draws/infections use the state's own carried RNG.
GameState playHeuristicTurn(GameState s, std::mt19937& rng) {
    int guard = 0;
    while (s.status == GameStatus::InProgress && s.phase == Phase::PlayerActions &&
           guard++ < 50) {
        std::vector<Action> legal = legalActions(s);
        if (legal.empty()) break;
        s = stepAction(s, greedyHeuristicChoice(s, legal, rng));
    }
    if (s.status == GameStatus::InProgress && s.phase == Phase::Draw)
        s = resolveTurnEnd(s);
    return s;
}

// The paper's greedy baseline using the planning heuristic.
class HeuristicAgent : public Agent {
public:
    explicit HeuristicAgent(unsigned seed) : rng_(seed) {}
    std::string name() const override { return "heuristic"; }
    Action chooseAction(const GameState& s, const std::vector<Action>& legal) override {
        return greedyHeuristicChoice(s, legal, rng_);
    }
private:
    std::mt19937 rng_;
};

// The planning agent: A* over the current player's turn(s) with draw/infect skipped,
// goal states evaluated by Monte Carlo rollouts of the hidden draws.
//
// horizon == 1 ("planner")  — searches the current turn; the survive goal is reached
//                             at this turn's end, evaluated by one infect rollout.
// horizon == 2 ("planner2") — a literal reading of the paper's "2 turns ahead": the
//                             search crosses its own turn boundary (draws/infections
//                             skipped, other players ignored) into a second turn, and
//                             evaluates by rolling a full round of infections forward.
//                             Only the FIRST turn's actions are actually executed; the
//                             second turn is lookahead used to pick those first actions.
// horizon == 3 ("planner3") — couples the second-turn search with the rollouts: the
//                             outer A* covers only turn 1, and each rollout samples a
//                             fresh intervening round (my draw/infect + heuristic
//                             teammate turns) and *re-plans* turn 2 on that realistic
//                             board. So the second turn's action choices and their
//                             evaluation are both made on sampled boards, then averaged.
// horizon == 4 ("planner4") — the paper's FAITHFUL "n turns ahead": the search crosses
//                             each turn boundary into the NEXT player's turn (draws
//                             skipped) and plans that player's actions too — valid in a
//                             cooperative game with known hands — for `turnsAhead_` turns
//                             (default 2). Evaluation is identical to planner2, so the
//                             only difference from planner2 is the player rotation.
class PlannerAgent : public Agent {
public:
    PlannerAgent(unsigned seed, int rollouts, int horizon, int planTurns = 2,
                 bool deterministic = false, int nodeCapOverride = 0)
        : rng_(seed), rollouts_(std::max(1, rollouts)), horizon_(horizon),
          nodeCap_(nodeCapOverride > 0 ? nodeCapOverride
                                       : ((horizon == 2 || horizon == 4) ? 5000 : 2500)),
          turnsAhead_(std::max(1, planTurns)), deterministic_(deterministic) {}
    std::string name() const override {
        return horizon_ == 4 ? "planner4"
             : horizon_ == 3 ? "planner3"
             : horizon_ == 2 ? "planner2" : "planner";
    }

    Action chooseAction(const GameState& s, const std::vector<Action>& legal) override {
        // Discards (and any non-action phase) are handled greedily.
        if (s.phase != Phase::PlayerActions)
            return greedyHeuristicChoice(s, legal, rng_);

        // Dispense the cached plan while it stays valid for the presented state.
        if (planPos_ < plan_.size()) {
            const Action& a = plan_[planPos_];
            if (std::find(legal.begin(), legal.end(), a) != legal.end()) { ++planPos_; return a; }
            plan_.clear(); planPos_ = 0;  // diverged -> replan
        }

        plan_ = computePlan(s);
        planPos_ = 0;
        if (plan_.empty()) {
            // No goal found within budget: fall back to greedy, but still refuse to forfeit
            // actions — only pass when it is the sole legal move.
            std::vector<Action> noPass = planExpandActions(s);
            const std::vector<Action>& pick = noPass.empty() ? legal : noPass;
            return greedyHeuristicChoice(s, pick, rng_);
        }
        return plan_[planPos_++];
    }

private:
    std::mt19937 rng_;
    int rollouts_;
    int horizon_;
    int nodeCap_;
    int nodeCapInner_ = 1500;  // budget for planner3's nested second-turn search
    int turnsAhead_ = 2;       // planner4 look-ahead horizon, in players' turns
    size_t topGoals_ = 6;
    unsigned rolloutBase_ = 0; // sample seed base, fixed per planning call (CRN across goals)
    bool deterministic_ = false;  // differential harness: rank goals by g+h only (no predictor)
    std::vector<Action> plan_;
    size_t planPos_ = 0;

    struct Node {
        GameState state;
        std::vector<Action> path;
        double f;
        bool crossed = false;     // has the search jumped past the 1st turn boundary?
        size_t firstTurnLen = 0;  // #actions belonging to the turn we actually execute
        int turnsCrossed = 0;     // planner4: #turn boundaries crossed so far
    };

    static size_t signature(const GameState& s) {
        size_t h = 1469598103934665603ULL;
        auto mix = [&](uint64_t v) { h ^= v; h *= 1099511628211ULL; };
        mix(s.currentPlayer); mix(s.actionsRemaining); mix(static_cast<uint64_t>(s.phase));
        mix(s.stationCount);
        for (int k = 0; k < NUM_COLORS; ++k) mix(static_cast<uint64_t>(s.cures[k]));
        for (const Player& p : s.players) {
            mix(static_cast<uint64_t>(p.location) + 1);
            std::vector<CityId> hand = p.hand;
            std::sort(hand.begin(), hand.end());
            for (CityId c : hand) mix(static_cast<uint64_t>(c) + 100);
        }
        for (CityId c = 0; c < NUM_CITIES; ++c)
            for (int k = 0; k < NUM_COLORS; ++k)
                mix(s.cubes[static_cast<size_t>(c)][k] * 7u + static_cast<unsigned>(c));
        return h;
    }

    // Visited key distinguishes pre- and post-boundary states with the same board.
    static size_t key(const GameState& s, bool crossed) {
        return signature(s) * 2 + (crossed ? 1 : 0);
    }

    // planner4 visited key: distinguishes states by how many turn boundaries were crossed.
    size_t keyN(const GameState& s, int turnsCrossed) const {
        return signature(s) * static_cast<size_t>(turnsAhead_ + 1) +
               static_cast<size_t>(turnsCrossed);
    }

    // Value of a rollout's terminal state = the paper's eq.8 heuristic, with no extra
    // loss penalty: a rollout that loses but got close to winning (e.g. 3 of 4 cures)
    // keeps its real cube/cure value rather than being treated as catastrophic.
    double terminalValue(const GameState& s) const {
        return evaluateState(s);
    }

    // Faithful reimplementation of the paper's MCTSModeling.predict: the expected
    // ONE-STEP cost of the current player's end-of-turn — drawing 2 player cards (with
    // any epidemic) and the infect phase — decomposed into three terms and clamped at 0.
    // No teammate turns are simulated (the paper models only this player's immediate
    // draw/infect). `resolveTurnEnd` performs exactly that single step, with correct
    // epidemic/outbreak/eradication/quarantine handling. Returned value is the paper's
    // `draws_h`, to be ADDED to the goal's A* heuristic at the call site (g + h + draws_h).
    //
    // Sample seeds derive from rolloutBase_ (fixed once per planning call): because the
    // hidden decks are identical at every goal within a turn (draws are skipped during
    // search), every goal sees the same determinized draws — the paper's "same 100 samples
    // reused for all goals" (common random numbers across goals).
    double evalGoal(const GameState& goal) {
        GameState atDraw = goal;
        if (atDraw.status == GameStatus::InProgress && atDraw.phase == Phase::PlayerActions)
            atDraw = stepAction(atDraw, Action::pass());  // end the turn to enable draws
        if (atDraw.status != GameStatus::InProgress)
            return 0.0;  // won/lost goal: no end-of-turn draw/infect remains -> no delta

        const int planner = atDraw.currentPlayer;
        const double startCardDist = cardDistance(atDraw, planner);
        int startSupply = 0;
        for (int k = 0; k < NUM_COLORS; ++k) startSupply += atDraw.cubesSupply[k];
        const int rate = atDraw.infectionRate();

        double cardDeltaSum = 0.0, diseaseDeltaSum = 0.0, discardSum = 0.0;
        for (int r = 0; r < rollouts_; ++r) {
            std::mt19937 drng(rolloutBase_ + static_cast<unsigned>(r) * 2654435761u);
            GameState rs = determinizeHiddenDecks(atDraw, drng);
            rs.rng = drng;  // keep the advanced RNG so epidemic intensify shuffles vary
            rs = resolveTurnEnd(rs);  // the paper's one step: draw 2 -> epidemic -> infect

            // Card + discard terms read the planner's POST-DRAW hand (before any forced
            // discard, matching the paper, which keeps overflow cards for card distance).
            cardDeltaSum += cardDistance(rs, planner) - startCardDist;
            int handAfter = static_cast<int>(rs.players[static_cast<size_t>(planner)].hand.size());
            discardSum += std::max(0, handAfter - HAND_LIMIT);

            // Overflow pauses before the infect phase; discard greedily so applyAction
            // finishes the infect and the disease term is always measured.
            while (rs.status == GameStatus::InProgress && rs.phase == Phase::Discard) {
                std::vector<Action> legal = legalActions(rs);
                rs = applyAction(rs, greedyHeuristicChoice(rs, legal, drng));
            }
            int supplyAfter = 0;
            for (int k = 0; k < NUM_COLORS; ++k) supplyAfter += rs.cubesSupply[k];
            diseaseDeltaSum += (startSupply + rate) - supplyAfter;
        }

        double totalC = PRED_W_CARDS    * (cardDeltaSum    / rollouts_);
        double totalD = PRED_W_DISEASES * (diseaseDeltaSum / rollouts_);
        double totalR = PRED_W_DISCARD  * ((discardSum / rollouts_) / 12.0);
        return std::max(0.0, totalC + totalD + totalR);
    }

    // --- planner3 helpers --------------------------------------------------------

    // Cheap leaf for the nested second-turn search: end the turn and judge survival
    // against a single determinized infect phase. No nested rollouts (keeps the
    // coupled search from blowing up). Uses the state's carried RNG, so it is a pure
    // function of the rollout that produced `goal`.
    double cheapLeaf(const GameState& goal) {
        GameState rs = goal;
        if (rs.status == GameStatus::InProgress && rs.phase == Phase::PlayerActions)
            rs = stepAction(rs, Action::pass());
        if (rs.status != GameStatus::InProgress) return terminalValue(rs);
        std::mt19937 d = rs.rng;
        rs = determinizeHiddenDecks(rs, d);
        rs.rng = d;
        rs = resolveTurnEnd(rs);
        return terminalValue(rs);
    }

    // planner3's leaf: value a turn-1 end state by sampling the intervening round and
    // re-planning the second turn on the resulting (re-infected, teammate-helped) board.
    double evalCoupled(const GameState& goal) {
        GameState atDraw = goal;
        if (atDraw.status == GameStatus::InProgress && atDraw.phase == Phase::PlayerActions)
            atDraw = stepAction(atDraw, Action::pass());  // end turn 1 to enable draws
        if (atDraw.status != GameStatus::InProgress) return terminalValue(atDraw);
        const int me = atDraw.currentPlayer;
        double sum = 0.0;
        const unsigned base = rng_();
        for (int r = 0; r < rollouts_; ++r) {
            const unsigned sd = base + static_cast<unsigned>(r) * 2654435761u;
            GameState rs = atDraw;
            std::mt19937 drng(sd);
            rs = determinizeHiddenDecks(rs, drng);
            rs.rng = drng;
            rs = resolveTurnEnd(rs);  // my draw + infect
            if (rs.status != GameStatus::InProgress) { sum += terminalValue(rs); continue; }

            // The intervening round: every teammate plays a vaguely-useful turn.
            std::mt19937 trng(sd ^ 0x9e3779b9u);
            int guard = 0;
            while (rs.status == GameStatus::InProgress && rs.currentPlayer != me &&
                   guard++ <= static_cast<int>(rs.players.size()))
                rs = playHeuristicTurn(rs, trng);
            if (rs.status != GameStatus::InProgress) { sum += terminalValue(rs); continue; }

            // Re-plan my second turn on this realistic board, then resolve it.
            std::vector<Action> plan2 =
                planSingleTurn(rs, [this](const GameState& g, double) { return cheapLeaf(g); },
                               nodeCapInner_);
            for (const Action& a : plan2) {
                if (rs.status != GameStatus::InProgress || rs.phase != Phase::PlayerActions)
                    break;
                rs = stepAction(rs, a);
            }
            if (rs.status == GameStatus::InProgress && rs.phase == Phase::PlayerActions)
                rs = stepAction(rs, Action::pass());
            if (rs.status == GameStatus::InProgress && rs.phase == Phase::Draw)
                rs = resolveTurnEnd(rs);
            sum += terminalValue(rs);
        }
        return sum / rollouts_;
    }

    // Single-turn A* (no boundary crossing). Goal states are valued by `leafEval`, which
    // receives (goalState, f) where f = g + h; the lowest-valued plan is returned. Shared
    // by `planner` (leaf adds the paper's predict delta to f: g + h + draws_h) and
    // `planner3` (outer leaf = evalCoupled; nested leaf = cheapLeaf, both ignoring f).
    template <class LeafEval>
    std::vector<Action> planSingleTurn(const GameState& start, LeafEval leafEval,
                                       int nodeCap) {
        const int startCures = discoveredCures(start);
        const bool cureGoal = wantsCureGoal(start);

        std::deque<Node> pool;
        auto cmp = [](const Node* a, const Node* b) { return a->f > b->f; };
        std::priority_queue<Node*, std::vector<Node*>, decltype(cmp)> pq(cmp);
        std::unordered_set<size_t> visited;

        auto push = [&](GameState st, std::vector<Action> path) {
            double f = static_cast<double>(path.size()) +
                       evaluateState(st, /*survive=dsurv*/ !cureGoal, /*cure=dcure*/ cureGoal);
            pool.push_back(Node{std::move(st), std::move(path), f, false, 0});
            pq.push(&pool.back());
        };

        visited.insert(signature(start));
        push(start, {});

        std::vector<Node*> goals;
        int expanded = 0;
        while (!pq.empty() && expanded < nodeCap) {
            Node* n = pq.top(); pq.pop();

            bool isGoal = false;
            if (n->state.status != GameStatus::InProgress) isGoal = true;
            else if (cureGoal && discoveredCures(n->state) > startCures) isGoal = true;
            else if (n->state.phase == Phase::Draw) isGoal = true;

            if (isGoal) { if (!n->path.empty()) goals.push_back(n); continue; }
            if (n->state.phase != Phase::PlayerActions) continue;  // dead end

            ++expanded;
            for (const Action& a : planExpandActions(n->state)) {
                GameState ns = stepAction(n->state, a);
                if (!visited.insert(signature(ns)).second) continue;
                std::vector<Action> np = n->path;
                np.push_back(a);
                push(std::move(ns), std::move(np));
            }
        }

        if (goals.empty()) return {};
        std::sort(goals.begin(), goals.end(),
                  [](const Node* a, const Node* b) { return a->f < b->f; });
        size_t limit = std::min(topGoals_, goals.size());
        double bestVal = 1e300;
        const Node* best = nullptr;
        for (size_t i = 0; i < limit; ++i) {
            double v = leafEval(goals[i]->state, goals[i]->f);
            if (v < bestVal) { bestVal = v; best = goals[i]; }
        }
        if (!best) return {};
        return best->path;
    }

    std::vector<Action> computePlan(const GameState& start) {
        // Fix the rollout sample base once per planning call so every goal evaluated in
        // this pass sees the same determinized draws (common random numbers).
        rolloutBase_ = rng_();
        if (horizon_ == 4) return computePlanNextPlayers(start);
        if (horizon_ == 3)
            return planSingleTurn(
                start, [this](const GameState& g, double) { return evalCoupled(g); }, nodeCap_);
        if (horizon_ == 2) return computePlanTwoTurn(start);
        // planner: goal value = g + h + predict (the paper's frontier key).
        return planSingleTurn(
            start, [this](const GameState& g, double f) {
                return f + (deterministic_ ? 0.0 : evalGoal(g));
            }, nodeCap_);
    }

    // planner4: A* over the next `turnsAhead_` turns, crossing each boundary into the
    // NEXT player's turn and planning their actions too (cooperative look-ahead). Only
    // the first turn's actions are executed; evaluation reuses evalGoal (identical to
    // planner2), so the sole difference from planner2 is the per-turn player rotation.
    std::vector<Action> computePlanNextPlayers(const GameState& start) {
        const int startCures = discoveredCures(start);
        const bool cureGoal = wantsCureGoal(start);
        // The paper's *survive* goal is fixed at 2 turns (mine + the next player's), but its
        // *discover-cure* goal has no turn limit — it searches across turns (bounded only by
        // the node budget) until a new cure is reached, so a card hand-off that takes several
        // turns to set up and complete can be found. Cross far enough to return to my own turn
        // after a full round plus a buffer; the node cap (nodeCap_) bounds the real depth.
        const int horizonTurns =
            cureGoal ? static_cast<int>(start.players.size()) + 2 : turnsAhead_;

        std::deque<Node> pool;
        auto cmp = [](const Node* a, const Node* b) { return a->f > b->f; };
        std::priority_queue<Node*, std::vector<Node*>, decltype(cmp)> pq(cmp);
        std::unordered_set<size_t> visited;

        auto push = [&](GameState st, std::vector<Action> path, int turnsCrossed,
                        size_t firstLen) {
            double f = static_cast<double>(path.size()) +
                       evaluateState(st, /*survive=dsurv*/ !cureGoal, /*cure=dcure*/ cureGoal);
            Node n{std::move(st), std::move(path), f, turnsCrossed > 0, firstLen, turnsCrossed};
            pool.push_back(std::move(n));
            pq.push(&pool.back());
        };

        visited.insert(keyN(start, 0));
        push(start, {}, 0, 0);

        std::vector<Node*> goals;
        int expanded = 0;
        while (!pq.empty() && expanded < nodeCap_) {
            Node* n = pq.top(); pq.pop();

            bool isGoal = false;
            if (n->state.status != GameStatus::InProgress) isGoal = true;
            else if (cureGoal && discoveredCures(n->state) > startCures) isGoal = true;
            else if (n->state.phase == Phase::Draw) {
                if (n->turnsCrossed + 1 < horizonTurns) {
                    // In cure mode we may cross many turns chasing a hand-off; keep the end
                    // of my own first turn as a survive fallback so a plan always exists even
                    // if no cure is reached within budget. (Survive mode is unchanged: only
                    // the deep end-of-turn below is a goal.)
                    if (cureGoal && n->turnsCrossed == 0 && !n->path.empty())
                        goals.push_back(n);
                    // Hand the turn to the next player and keep planning their turn.
                    GameState ns = advanceToNextPlayerSkippingDraws(n->state);
                    size_t firstLen = n->turnsCrossed == 0 ? n->path.size() : n->firstTurnLen;
                    if (visited.insert(keyN(ns, n->turnsCrossed + 1)).second)
                        push(std::move(ns), n->path, n->turnsCrossed + 1, firstLen);
                    continue;
                }
                isGoal = true;  // end of the n-th planned turn = survive goal
            }

            if (isGoal) { if (!n->path.empty()) goals.push_back(n); continue; }
            if (n->state.phase != Phase::PlayerActions) continue;  // dead end

            ++expanded;
            for (const Action& a : planExpandActions(n->state)) {
                GameState ns = stepAction(n->state, a);
                if (!visited.insert(keyN(ns, n->turnsCrossed)).second) continue;
                std::vector<Action> np = n->path;
                np.push_back(a);
                push(std::move(ns), std::move(np), n->turnsCrossed, n->firstTurnLen);
            }
        }

        if (goals.empty()) return {};

        std::sort(goals.begin(), goals.end(),
                  [](const Node* a, const Node* b) { return a->f < b->f; });
        size_t limit = std::min(topGoals_, goals.size());
        double bestVal = 1e300;
        const Node* best = nullptr;
        for (size_t i = 0; i < limit; ++i) {
            double v = goals[i]->f + (deterministic_ ? 0.0 : evalGoal(goals[i]->state));
            if (v < bestVal) { bestVal = v; best = goals[i]; }
        }
        if (!best) return {};

        // Execute only the first turn's actions; the rest was cooperative look-ahead.
        size_t execLen = best->turnsCrossed > 0 ? best->firstTurnLen : best->path.size();
        return std::vector<Action>(best->path.begin(), best->path.begin() + execLen);
    }

    std::vector<Action> computePlanTwoTurn(const GameState& start) {
        const int startCures = discoveredCures(start);
        const bool cureGoal = wantsCureGoal(start);

        std::deque<Node> pool;
        auto cmp = [](const Node* a, const Node* b) { return a->f > b->f; };
        std::priority_queue<Node*, std::vector<Node*>, decltype(cmp)> pq(cmp);
        std::unordered_set<size_t> visited;

        auto push = [&](GameState st, std::vector<Action> path, bool crossed, size_t firstLen) {
            double f = static_cast<double>(path.size()) +
                       evaluateState(st, /*survive=dsurv*/ !cureGoal, /*cure=dcure*/ cureGoal);
            pool.push_back(Node{std::move(st), std::move(path), f, crossed, firstLen});
            pq.push(&pool.back());
        };

        visited.insert(key(start, false));
        push(start, {}, false, 0);

        std::vector<Node*> goals;
        int expanded = 0;
        while (!pq.empty() && expanded < nodeCap_) {
            Node* n = pq.top(); pq.pop();

            bool isGoal = false;
            if (n->state.status != GameStatus::InProgress) isGoal = true;
            else if (cureGoal && discoveredCures(n->state) > startCures) isGoal = true;
            else if (n->state.phase == Phase::Draw) {
                if (horizon_ >= 2 && !n->crossed) {
                    // Jump past our own turn boundary into a second turn of lookahead.
                    GameState ns = advanceTurnSkippingDraws(n->state);
                    if (visited.insert(key(ns, true)).second)
                        push(std::move(ns), n->path, true, n->path.size());
                    continue;
                }
                isGoal = true;  // end of the (last) planned turn = survive goal
            }

            if (isGoal) { if (!n->path.empty()) goals.push_back(n); continue; }
            if (n->state.phase != Phase::PlayerActions) continue;  // dead end

            ++expanded;
            for (const Action& a : planExpandActions(n->state)) {
                GameState ns = stepAction(n->state, a);
                if (!visited.insert(key(ns, n->crossed)).second) continue;
                std::vector<Action> np = n->path;
                np.push_back(a);
                push(std::move(ns), std::move(np), n->crossed, n->firstTurnLen);
            }
        }

        if (goals.empty()) return {};

        // Rollout-evaluate the most promising goals (cheap static order first). Scoring ALL
        // collected goals instead (the paper's behaviour, B.3) was measured to be byte-for-byte
        // identical over 3000 games — the one-step predictor never promotes a goal past the
        // static top-K — so the prefilter is a lossless ~10% speedup, kept deliberately.
        std::sort(goals.begin(), goals.end(),
                  [](const Node* a, const Node* b) { return a->f < b->f; });
        size_t limit = std::min(topGoals_, goals.size());
        double bestVal = 1e300;
        const Node* best = nullptr;
        for (size_t i = 0; i < limit; ++i) {
            double v = goals[i]->f + (deterministic_ ? 0.0 : evalGoal(goals[i]->state));
            if (v < bestVal) { bestVal = v; best = goals[i]; }
        }
        if (!best) return {};

        // Execute only the first turn's actions; the rest was lookahead.
        size_t execLen = best->crossed ? best->firstTurnLen : best->path.size();
        return std::vector<Action>(best->path.begin(), best->path.begin() + execLen);
    }
};

} // namespace

std::unique_ptr<Agent> makeAgent(const std::string& name, unsigned seed, int rollouts,
                                 int planTurns, bool deterministic, int nodeCap) {
    auto planner = [&](int horizon, int turns) {
        return std::make_unique<PlannerAgent>(seed, rollouts, horizon, turns, deterministic,
                                              nodeCap);
    };
    if (name == "greedy")    return std::make_unique<GreedyAgent>(seed);
    if (name == "heuristic") return std::make_unique<HeuristicAgent>(seed);
    if (name == "planner")   return planner(1, planTurns);
    if (name == "planner2")  return planner(2, planTurns);
    if (name == "planner3")  return planner(3, planTurns);
    if (name == "planner4")  return planner(4, planTurns);
    // Default / "random" / unknown.
    return std::make_unique<RandomAgent>(seed);
}

bool plannerPursuesCure(const GameState& s) { return wantsCureGoal(s); }

std::vector<std::string> agentNames() {
    return {"random", "greedy", "heuristic", "planner", "planner2", "planner3", "planner4"};
}

} // namespace paindemic
