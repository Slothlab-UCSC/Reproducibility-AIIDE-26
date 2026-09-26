#include "paindemic/engine.h"
#include "paindemic/log.h"
#include "paindemic/map_data.h"

#include <algorithm>
#include <numeric>
#include <set>
#include <sstream>

namespace paindemic {
namespace {

int colorIdx(Color c) { return static_cast<int>(c); }

int cardsToCure(RoleType r) {
    return r == RoleType::Scientist ? 4 : 5;
}

// Append an event iff logging is enabled. The nullptr path (search/agents) does no
// work, so the pure applyAction stays allocation-free.
inline void emit(EventLog* log, const Event& e) {
    if (log) log->push_back(e);
}

// --- Cube / infection mechanics ------------------------------------------------

// Is placement of a `color` cube in `city` prevented by a role or eradication?
bool placementPrevented(const GameState& s, CityId city, Color color) {
    if (s.cures[colorIdx(color)] == CureStatus::Eradicated) return true;
    for (const Player& p : s.players) {
        if (p.role == RoleType::QuarantineSpecialist) {
            if (p.location == city || areAdjacent(p.location, city)) return true;
        }
        if (p.role == RoleType::Medic) {
            // Medic prevents cubes of a *cured* disease in his own city.
            if (p.location == city && s.cures[colorIdx(color)] != CureStatus::Uncured)
                return true;
        }
    }
    return false;
}

void markLost(GameState& s, EventLog* log, LossReason reason) {
    s.status = GameStatus::Lost;
    s.phase = Phase::GameOver;
    Event e; e.type = EventType::GameLost; e.amount = static_cast<int>(reason);
    emit(log, e);
}

// Add one cube of `color` to `city`, resolving outbreaks recursively. `outbroken`
// tracks cities that have already burst during this single infection resolution so
// none bursts twice (and chains terminate).
void addCube(GameState& s, CityId city, Color color, std::set<CityId>& outbroken, EventLog* log) {
    if (s.status != GameStatus::InProgress) return;
    if (placementPrevented(s, city, color)) return;

    int ci = colorIdx(color);
    uint8_t& count = s.cubes[static_cast<size_t>(city)][ci];
    if (count >= 3) {
        // Outbreak.
        if (outbroken.count(city)) return;
        outbroken.insert(city);
        if (++s.outbreakCount >= MAX_OUTBREAKS) {
            Event e; e.type = EventType::Outbreak; e.city = city; e.color = color;
            e.amount = s.outbreakCount; emit(log, e);
            markLost(s, log, LossReason::EighthOutbreak);
            return;
        }
        Event e; e.type = EventType::Outbreak; e.city = city; e.color = color;
        e.amount = s.outbreakCount; emit(log, e);
        for (CityId n : cityInfo(city).neighbors) {
            addCube(s, n, color, outbroken, log);
            if (s.status != GameStatus::InProgress) return;
        }
    } else {
        if (s.cubesSupply[ci] == 0) { markLost(s, log, LossReason::CubesOut); return; }
        ++count;
        --s.cubesSupply[ci];
    }
}

// Resolve drawing one infection card for `city`.
void infectCity(GameState& s, CityId city, EventLog* log) {
    std::set<CityId> outbroken;
    addCube(s, city, cityColor(city), outbroken, log);
}

// --- Eradication ---------------------------------------------------------------

void updateEradication(GameState& s, Color color, EventLog* log) {
    int ci = colorIdx(color);
    if (s.cures[ci] == CureStatus::Cured && s.cubesSupply[ci] == CUBES_PER_COLOR) {
        s.cures[ci] = CureStatus::Eradicated;  // cured + zero cubes on board
        Event e; e.type = EventType::Eradicated; e.color = color; emit(log, e);
    }
}

// --- Movement (with Medic auto-treat) -----------------------------------------

void movePawn(GameState& s, int playerIdx, CityId dest, EventLog* log) {
    Player& p = s.players[static_cast<size_t>(playerIdx)];
    p.location = dest;
    if (p.role == RoleType::Medic) {
        // Medic auto-removes cubes of cured diseases from the city he enters.
        for (int c = 0; c < NUM_COLORS; ++c) {
            if (s.cures[c] != CureStatus::Uncured) {
                uint8_t& cnt = s.cubes[static_cast<size_t>(dest)][c];
                s.cubesSupply[c] = static_cast<uint8_t>(s.cubesSupply[c] + cnt);
                cnt = 0;
                updateEradication(s, static_cast<Color>(c), log);
            }
        }
    }
}

// --- Win / loss ----------------------------------------------------------------

void checkWin(GameState& s, EventLog* log) {
    bool all = std::all_of(s.cures.begin(), s.cures.end(),
                           [](CureStatus c) { return c != CureStatus::Uncured; });
    if (all) {
        s.status = GameStatus::Won;
        s.phase = Phase::GameOver;
        Event e; e.type = EventType::GameWon; emit(log, e);
    }
}

// --- Deck-structure metadata (for rollout re-determinization) ------------------
// All metadata vectors are bottom->top; updates are no-ops when metadata is unset
// (e.g. hand-built test states), so the rest of the engine is unaffected.

void infectionTopDrawn(GameState& s) {  // a card was removed from the top
    if (s.infectionBlockSizes.empty()) return;
    if (--s.infectionBlockSizes.back() == 0) s.infectionBlockSizes.pop_back();
}
void infectionBottomDrawn(GameState& s) {  // a card was removed from the bottom
    if (s.infectionBlockSizes.empty()) return;
    if (--s.infectionBlockSizes.front() == 0)
        s.infectionBlockSizes.erase(s.infectionBlockSizes.begin());
}
void infectionPushTopBlock(GameState& s, size_t n) {  // an intensify reshuffle
    if (!s.infectionBlockSizes.empty() && n > 0)
        s.infectionBlockSizes.push_back(static_cast<uint8_t>(n));
}
void playerTopDrawn(GameState& s, bool wasEpidemic) {  // a player card was drawn
    if (s.playerPileSizes.empty()) return;
    if (wasEpidemic && !s.playerPileHasEpidemic.empty())
        s.playerPileHasEpidemic.back() = 0;
    if (--s.playerPileSizes.back() == 0) {
        s.playerPileSizes.pop_back();
        if (!s.playerPileHasEpidemic.empty()) s.playerPileHasEpidemic.pop_back();
    }
}

// --- Epidemic / draw / infect flow --------------------------------------------

void doEpidemic(GameState& s, EventLog* log) {
    // 1. Increase.
    if (s.infectionRateIndex + 1 < static_cast<int>(INFECTION_RATE_TRACK.size()))
        ++s.infectionRateIndex;
    { Event e; e.type = EventType::EpidemicIncrease; e.amount = s.infectionRate(); emit(log, e); }
    // 2. Infect the bottom city card with 3 cubes.
    if (!s.infectionDraw.empty()) {
        CityId bottom = s.infectionDraw.front();
        s.infectionDraw.erase(s.infectionDraw.begin());
        infectionBottomDrawn(s);
        { Event e; e.type = EventType::EpidemicInfect; e.city = bottom; emit(log, e); }
        std::set<CityId> outbroken;
        for (int i = 0; i < 3; ++i) {
            addCube(s, bottom, cityColor(bottom), outbroken, log);
            if (s.status != GameStatus::InProgress) return;
        }
        s.infectionDiscard.push_back(bottom);
    }
    // 3. Intensify: shuffle the infection discard and place it on top of the deck.
    std::shuffle(s.infectionDiscard.begin(), s.infectionDiscard.end(), s.rng);
    infectionPushTopBlock(s, s.infectionDiscard.size());
    s.infectionDraw.insert(s.infectionDraw.end(),
                           s.infectionDiscard.begin(), s.infectionDiscard.end());
    s.infectionDiscard.clear();
    { Event e; e.type = EventType::EpidemicIntensify; emit(log, e); }
}

void runInfectPhase(GameState& s, EventLog* log) {
    int rate = s.infectionRate();
    for (int i = 0; i < rate; ++i) {
        if (s.infectionDraw.empty()) break;
        CityId city = s.infectionDraw.back();
        s.infectionDraw.pop_back();
        infectionTopDrawn(s);
        s.infectionDiscard.push_back(city);
        { Event e; e.type = EventType::InfectionDrawn; e.city = city; emit(log, e); }
        infectCity(s, city, log);
        if (s.status != GameStatus::InProgress) return;
    }
}

void startNextTurn(GameState& s, EventLog* log) {
    s.currentPlayer = static_cast<uint8_t>((s.currentPlayer + 1) % s.players.size());
    s.actionsRemaining = ACTIONS_PER_TURN;
    s.opsFlightUsedThisTurn = false;
    s.phase = Phase::PlayerActions;
    Event e; e.type = EventType::TurnStart; e.player = static_cast<int8_t>(s.currentPlayer);
    e.role = s.cur().role; emit(log, e);
}

void finishTurnAfterDraw(GameState& s, EventLog* log) {
    runInfectPhase(s, log);
    if (s.status != GameStatus::InProgress) return;
    startNextTurn(s, log);
}

// After the active player's actions are done: draw 2, handle epidemics, then either
// pause for discards or run the infect phase and pass the turn.
void runDrawAndAfter(GameState& s, EventLog* log) {
    for (int i = 0; i < 2; ++i) {
        if (s.playerDraw.empty()) { markLost(s, log, LossReason::PlayerDeckOut); return; }
        Card c = s.playerDraw.back();
        s.playerDraw.pop_back();
        playerTopDrawn(s, c.kind == CardKind::Epidemic);
        { Event e; e.type = EventType::PlayerCardDrawn; e.player = static_cast<int8_t>(s.currentPlayer);
          e.role = s.cur().role; e.card = c; emit(log, e); }
        if (c.kind == CardKind::Epidemic) {
            s.playerDiscard.push_back(c);
            doEpidemic(s, log);
            if (s.status != GameStatus::InProgress) return;
        } else {
            s.cur().hand.push_back(c.city);
        }
    }
    // Hand-limit checkpoint for the player who drew.
    if (static_cast<int>(s.cur().hand.size()) > HAND_LIMIT) {
        s.discardingPlayer = static_cast<int8_t>(s.currentPlayer);
        s.phase = Phase::Discard;
        return;
    }
    finishTurnAfterDraw(s, log);
}

// Called when the player's action phase ends (4th action spent, or Pass).
void endActionPhase(GameState& s, EventLog* log) {
    s.actionsRemaining = 0;
    s.phase = Phase::Draw;
    runDrawAndAfter(s, log);
}

// End the action phase, but only resolve the stochastic draw/infect when
// `autoResolve` is set. With autoResolve=false the state stops at the pre-draw
// boundary (Phase::Draw) — this is what planning/heuristic search uses to explore
// action sequences without revealing hidden cards.
void endActionPhaseMaybe(GameState& s, EventLog* log, bool autoResolve) {
    if (autoResolve) {
        endActionPhase(s, log);
    } else {
        s.actionsRemaining = 0;
        s.phase = Phase::Draw;
    }
}

// --- Cure helpers --------------------------------------------------------------

void discardNCardsOfColor(Player& p, Color color, int n, std::vector<Card>& discardPile) {
    int removed = 0;
    for (auto it = p.hand.begin(); it != p.hand.end() && removed < n;) {
        if (cityColor(*it) == color) {
            discardPile.push_back(Card::cityCard(*it));
            it = p.hand.erase(it);
            ++removed;
        } else {
            ++it;
        }
    }
}

} // namespace

// ===========================================================================
// newGame
// ===========================================================================
GameState newGame(const std::vector<RoleType>& roles, unsigned seed, int epidemics) {
    GameState s;
    s.rng.seed(seed);
    s.cubesSupply.fill(CUBES_PER_COLOR);
    s.cures.fill(CureStatus::Uncured);

    // Players, all starting in Atlanta.
    int n = std::clamp(static_cast<int>(roles.size()), 2, MAX_PLAYERS);
    for (int i = 0; i < n; ++i) {
        Player p;
        p.role = roles[static_cast<size_t>(i)];
        p.location = STARTING_CITY;
        s.players.push_back(p);
    }

    // Starting research station in Atlanta.
    s.stations[STARTING_CITY] = true;
    s.stationCount = 1;

    // Infection deck: all 48 city cards, shuffled.
    s.infectionDraw.resize(NUM_CITIES);
    std::iota(s.infectionDraw.begin(), s.infectionDraw.end(), static_cast<CityId>(0));
    std::shuffle(s.infectionDraw.begin(), s.infectionDraw.end(), s.rng);

    // Player deck: 48 city cards, shuffled (event cards are out of scope in v1).
    std::vector<Card> playerCards;
    playerCards.reserve(NUM_CITIES);
    for (int c = 0; c < NUM_CITIES; ++c)
        playerCards.push_back(Card::cityCard(static_cast<CityId>(c)));
    std::shuffle(playerCards.begin(), playerCards.end(), s.rng);

    // Deal starting hands: 4/3/2 cards for 2/3/4 players.
    int handSize = (n == 2) ? 4 : (n == 3) ? 3 : 2;
    for (int i = 0; i < n; ++i) {
        for (int k = 0; k < handSize; ++k) {
            s.players[static_cast<size_t>(i)].hand.push_back(playerCards.back().city);
            playerCards.pop_back();
        }
    }

    // Build the draw deck by splitting the remaining cards into `epidemics` piles,
    // shuffling one Epidemic card into each, then stacking the piles.
    int eps = std::clamp(epidemics, 4, 6);
    int remaining = static_cast<int>(playerCards.size());
    std::vector<Card> deck;
    deck.reserve(remaining + eps);
    int base = remaining / eps, extra = remaining % eps, idx = 0;
    for (int pile = 0; pile < eps; ++pile) {
        int sz = base + (pile < extra ? 1 : 0);
        std::vector<Card> chunk(playerCards.begin() + idx, playerCards.begin() + idx + sz);
        idx += sz;
        chunk.push_back(Card::epidemic());
        std::shuffle(chunk.begin(), chunk.end(), s.rng);
        deck.insert(deck.end(), chunk.begin(), chunk.end());
        // Append order is bottom->top; each pile holds exactly one epidemic.
        s.playerPileSizes.push_back(static_cast<uint8_t>(chunk.size()));
        s.playerPileHasEpidemic.push_back(1);
    }
    s.playerDraw = std::move(deck);
    s.initialPlayerDeckSize = static_cast<uint16_t>(s.playerDraw.size());

    // Initial infections: 3 cities x3 cubes, 3 x2, 3 x1.
    for (int cubesEach = 3; cubesEach >= 1; --cubesEach) {
        for (int k = 0; k < 3; ++k) {
            CityId city = s.infectionDraw.back();
            s.infectionDraw.pop_back();
            s.infectionDiscard.push_back(city);
            std::set<CityId> outbroken;
            for (int j = 0; j < cubesEach; ++j)
                addCube(s, city, cityColor(city), outbroken, nullptr);
        }
    }
    // The undrawn infection deck is a single block of unknown order until the first
    // epidemic reshuffle splits it.
    s.infectionBlockSizes.assign(1, static_cast<uint8_t>(s.infectionDraw.size()));

    s.currentPlayer = 0;
    s.actionsRemaining = ACTIONS_PER_TURN;
    s.phase = Phase::PlayerActions;
    return s;
}

// ===========================================================================
// legalActions
// ===========================================================================
std::vector<Action> legalActions(const GameState& s) {
    std::vector<Action> out;
    if (s.status != GameStatus::InProgress) return out;

    // Discard phase: the over-limit player must discard a card.
    if (s.phase == Phase::Discard) {
        const Player& p = s.players[static_cast<size_t>(s.discardingPlayer)];
        std::set<CityId> seen;
        for (CityId c : p.hand)
            if (seen.insert(c).second)
                out.push_back(Action::discardCard(c));
        return out;
    }

    if (s.phase != Phase::PlayerActions) return out;  // draw/infect are internal

    const Player& p = s.cur();
    CityId here = p.location;
    int me = s.currentPlayer;

    // Pass is always available.
    out.push_back(Action::pass());

    // Drive / Ferry: to any adjacent city.
    for (CityId nb : cityInfo(here).neighbors)
        out.push_back(Action::drive(nb));

    // Direct Flight: discard a city card to move to that city.
    for (CityId c : p.hand) {
        if (c == here) continue;
        Action a; a.type = ActionType::DirectFlight; a.target = c; a.card = c;
        out.push_back(a);
    }

    // Charter Flight: discard the current-city card to move anywhere.
    if (p.hasCityCard(here)) {
        for (CityId c = 0; c < NUM_CITIES; ++c) {
            if (c == here) continue;
            Action a; a.type = ActionType::CharterFlight; a.target = c; a.card = here;
            out.push_back(a);
        }
    }

    // Shuttle Flight: between research stations.
    if (s.hasStation(here)) {
        for (CityId c = 0; c < NUM_CITIES; ++c)
            if (c != here && s.hasStation(c)) {
                Action a; a.type = ActionType::ShuttleFlight; a.target = c;
                out.push_back(a);
            }
    }

    // Build research station.
    if (!s.hasStation(here) && s.stationCount < MAX_RESEARCH_STATIONS) {
        bool free = (p.role == RoleType::OperationsExpert);
        if (free || p.hasCityCard(here))
            out.push_back(Action::build());
    }

    // Treat disease: any color present in the current city.
    for (int c = 0; c < NUM_COLORS; ++c)
        if (s.cubeCount(here, static_cast<Color>(c)) > 0)
            out.push_back(Action::treat(static_cast<Color>(c)));

    // Discover a cure: at a station, with enough same-color cards.
    if (s.hasStation(here)) {
        int need = cardsToCure(p.role);
        for (int c = 0; c < NUM_COLORS; ++c) {
            Color color = static_cast<Color>(c);
            if (s.cures[c] == CureStatus::Uncured && p.colorCount(color) >= need) {
                Action a; a.type = ActionType::DiscoverCure; a.color = color;
                out.push_back(a);
            }
        }
    }

    // Share knowledge: with another player in the same city.
    for (int q = 0; q < static_cast<int>(s.players.size()); ++q) {
        if (q == me) continue;
        const Player& other = s.players[static_cast<size_t>(q)];
        if (other.location != here) continue;

        // Give: normally only the current-city card; the Researcher may give any.
        bool researcherGiver = (p.role == RoleType::Researcher);
        if (static_cast<int>(other.hand.size()) < HAND_LIMIT) {
            if (researcherGiver) {
                for (CityId c : p.hand) {
                    Action a; a.type = ActionType::ShareGive; a.partner = static_cast<int8_t>(q); a.card = c;
                    out.push_back(a);
                }
            } else if (p.hasCityCard(here)) {
                Action a; a.type = ActionType::ShareGive; a.partner = static_cast<int8_t>(q); a.card = here;
                out.push_back(a);
            }
        }
        // Take: normally only the current-city card; from a Researcher, any card.
        if (static_cast<int>(p.hand.size()) < HAND_LIMIT) {
            if (other.role == RoleType::Researcher) {
                for (CityId c : other.hand) {
                    Action a; a.type = ActionType::ShareTake; a.partner = static_cast<int8_t>(q); a.card = c;
                    out.push_back(a);
                }
            } else if (other.hasCityCard(here)) {
                Action a; a.type = ActionType::ShareTake; a.partner = static_cast<int8_t>(q); a.card = here;
                out.push_back(a);
            }
        }
    }

    // Operations Expert: once per turn, from a station, discard any card to move
    // to any city.
    if (p.role == RoleType::OperationsExpert && s.hasStation(here) && !s.opsFlightUsedThisTurn) {
        for (CityId card : p.hand) {
            for (CityId dest = 0; dest < NUM_CITIES; ++dest) {
                if (dest == here) continue;
                Action a; a.type = ActionType::OperationsFlight; a.target = dest; a.card = card;
                out.push_back(a);
            }
        }
    }

    // Dispatcher: move any other pawn to a city containing another pawn (summon),
    // or drive any pawn to an adjacent city. (Card-based moving of other pawns is a
    // documented v1 simplification.)
    if (p.role == RoleType::Dispatcher) {
        for (int q = 0; q < static_cast<int>(s.players.size()); ++q) {
            CityId from = s.players[static_cast<size_t>(q)].location;
            // Drive any pawn to an adjacent city.
            for (CityId nb : cityInfo(from).neighbors) {
                Action a; a.type = ActionType::DispatcherMovePawn; a.pawn = static_cast<int8_t>(q); a.target = nb;
                out.push_back(a);
            }
            // Summon: move pawn q to any other pawn's city.
            for (int r = 0; r < static_cast<int>(s.players.size()); ++r) {
                if (r == q) continue;
                CityId dest = s.players[static_cast<size_t>(r)].location;
                if (dest == from) continue;
                Action a; a.type = ActionType::DispatcherSummon; a.pawn = static_cast<int8_t>(q); a.target = dest;
                out.push_back(a);
            }
        }
    }

    return out;
}

// ===========================================================================
// applyAction (logging overload + pure forward)
// ===========================================================================
static GameState applyImpl(const GameState& s0, const Action& a, EventLog* log, bool autoResolve) {
    GameState s = s0;  // value semantics: operate on an independent copy
    if (s.status != GameStatus::InProgress) return s;

    // Discard phase.
    if (s.phase == Phase::Discard) {
        Player& dp = s.players[static_cast<size_t>(s.discardingPlayer)];
        if (a.type == ActionType::Discard) {
            { Event e; e.type = EventType::ActionPerformed; e.player = s.discardingPlayer;
              e.role = dp.role; e.action = a; emit(log, e); }
            dp.removeCard(a.card);
            s.playerDiscard.push_back(Card::cityCard(a.card));
            { Event e; e.type = EventType::HandDiscard; e.player = s.discardingPlayer;
              e.role = dp.role; e.card = Card::cityCard(a.card); emit(log, e); }
        }
        if (static_cast<int>(dp.hand.size()) <= HAND_LIMIT) {
            s.discardingPlayer = -1;
            finishTurnAfterDraw(s, log);  // resume: infect, then next turn
        }
        return s;
    }

    if (s.phase != Phase::PlayerActions) return s;

    Player& p = s.cur();
    CityId here = p.location;
    { Event e; e.type = EventType::ActionPerformed; e.player = static_cast<int8_t>(s.currentPlayer);
      e.role = p.role; e.action = a; emit(log, e); }
    bool spent = true;  // most actions consume one of the four

    switch (a.type) {
        case ActionType::Pass:
            spent = false;
            endActionPhaseMaybe(s, log, autoResolve);
            return s;

        case ActionType::DriveFerry:
            movePawn(s, s.currentPlayer, a.target, log);
            break;

        case ActionType::DirectFlight:
            p.removeCard(a.card);
            s.playerDiscard.push_back(Card::cityCard(a.card));
            movePawn(s, s.currentPlayer, a.target, log);
            break;

        case ActionType::CharterFlight:
            p.removeCard(here);
            s.playerDiscard.push_back(Card::cityCard(here));
            movePawn(s, s.currentPlayer, a.target, log);
            break;

        case ActionType::ShuttleFlight:
            movePawn(s, s.currentPlayer, a.target, log);
            break;

        case ActionType::BuildStation:
            if (p.role != RoleType::OperationsExpert) {
                p.removeCard(here);
                s.playerDiscard.push_back(Card::cityCard(here));
            }
            s.stations[static_cast<size_t>(here)] = true;
            ++s.stationCount;
            break;

        case ActionType::TreatDisease: {
            int ci = colorIdx(a.color);
            uint8_t& cnt = s.cubes[static_cast<size_t>(here)][ci];
            bool removeAll = (p.role == RoleType::Medic) || (s.cures[ci] != CureStatus::Uncured);
            int removed = removeAll ? cnt : (cnt > 0 ? 1 : 0);
            cnt = static_cast<uint8_t>(cnt - removed);
            s.cubesSupply[ci] = static_cast<uint8_t>(s.cubesSupply[ci] + removed);
            updateEradication(s, a.color, log);
            break;
        }

        case ActionType::ShareGive: {
            Player& other = s.players[static_cast<size_t>(a.partner)];
            p.removeCard(a.card);
            other.hand.push_back(a.card);
            break;
        }

        case ActionType::ShareTake: {
            Player& other = s.players[static_cast<size_t>(a.partner)];
            other.removeCard(a.card);
            p.hand.push_back(a.card);
            break;
        }

        case ActionType::DiscoverCure: {
            int ci = colorIdx(a.color);
            discardNCardsOfColor(p, a.color, cardsToCure(p.role), s.playerDiscard);
            s.cures[ci] = CureStatus::Cured;
            { Event e; e.type = EventType::CureDiscovered; e.color = a.color; emit(log, e); }
            // Medic instantly clears cubes of the newly cured disease from his city.
            for (Player& mp : s.players)
                if (mp.role == RoleType::Medic) {
                    uint8_t& cnt = s.cubes[static_cast<size_t>(mp.location)][ci];
                    s.cubesSupply[ci] = static_cast<uint8_t>(s.cubesSupply[ci] + cnt);
                    cnt = 0;
                }
            updateEradication(s, a.color, log);
            checkWin(s, log);
            break;
        }

        case ActionType::OperationsFlight:
            p.removeCard(a.card);
            s.playerDiscard.push_back(Card::cityCard(a.card));
            movePawn(s, s.currentPlayer, a.target, log);
            s.opsFlightUsedThisTurn = true;
            break;

        case ActionType::DispatcherMovePawn:
        case ActionType::DispatcherSummon:
            movePawn(s, a.pawn, a.target, log);
            break;

        default:
            spent = false;
            break;
    }

    if (s.status != GameStatus::InProgress) return s;

    if (spent) {
        --s.actionsRemaining;
        if (s.actionsRemaining == 0)
            endActionPhaseMaybe(s, log, autoResolve);
    }
    return s;
}

GameState applyAction(const GameState& s, const Action& a, EventLog* log) {
    return applyImpl(s, a, log, /*autoResolve=*/true);
}

GameState applyAction(const GameState& s, const Action& a) {
    return applyImpl(s, a, nullptr, /*autoResolve=*/true);
}

// ===========================================================================
// Planning support: deterministic action stepping + stochastic turn resolution
// ===========================================================================
GameState stepAction(const GameState& s, const Action& a) {
    // Apply one action without resolving the end-of-turn draw/infect. A turn-ending
    // action leaves the state at Phase::Draw with decks/infections untouched.
    return applyImpl(s, a, nullptr, /*autoResolve=*/false);
}

GameState resolveTurnEnd(const GameState& s0, EventLog* log) {
    GameState s = s0;
    if (s.status != GameStatus::InProgress) return s;
    // From the pre-draw boundary, perform the draw + epidemic + infect phases.
    if (s.phase == Phase::Draw) {
        runDrawAndAfter(s, log);
    }
    // Auto-resolve any forced discards with a simple policy so rollouts run to the
    // next turn: drop a card of an already-cured color first, else the card whose
    // color the holder has fewest of (least useful toward a cure).
    while (s.status == GameStatus::InProgress && s.phase == Phase::Discard) {
        Player& dp = s.players[static_cast<size_t>(s.discardingPlayer)];
        CityId best = dp.hand.front();
        int bestScore = 1 << 30;
        for (CityId c : dp.hand) {
            Color col = cityColor(c);
            int score;
            if (s.cures[colorIdx(col)] != CureStatus::Uncured)
                score = -1;  // cured/eradicated color: discard first
            else
                score = dp.colorCount(col);  // fewer of this color -> less useful
            if (score < bestScore) { bestScore = score; best = c; }
        }
        s = applyImpl(s, Action::discardCard(best), log, /*autoResolve=*/true);
    }
    return s;
}

GameState advanceTurnSkippingDraws(const GameState& s0) {
    GameState s = s0;
    if (s.status != GameStatus::InProgress) return s;
    // Same player, fresh actions, no draw / infect / other-player turns.
    s.phase = Phase::PlayerActions;
    s.actionsRemaining = ACTIONS_PER_TURN;
    s.opsFlightUsedThisTurn = false;
    return s;
}

GameState advanceToNextPlayerSkippingDraws(const GameState& s0) {
    GameState s = s0;
    if (s.status != GameStatus::InProgress) return s;
    // Hand the turn to the NEXT player (no draw / infect, no teammate turns simulated) —
    // for multi-turn cooperative lookahead. Mirrors startNextTurn minus the draw/infect.
    s.currentPlayer = static_cast<uint8_t>((s.currentPlayer + 1) % s.players.size());
    s.phase = Phase::PlayerActions;
    s.actionsRemaining = ACTIONS_PER_TURN;
    s.opsFlightUsedThisTurn = false;
    return s;
}

GameState determinizeHiddenDecks(GameState s, std::mt19937& rng) {
    // --- Infection deck: shuffle within each block (membership stays public) ---
    size_t infTotal = 0;
    for (uint8_t b : s.infectionBlockSizes) infTotal += b;
    if (infTotal == s.infectionDraw.size() && !s.infectionDraw.empty()) {
        size_t i = 0;
        for (uint8_t b : s.infectionBlockSizes) {
            std::shuffle(s.infectionDraw.begin() + i, s.infectionDraw.begin() + i + b, rng);
            i += b;
        }
    } else {
        std::shuffle(s.infectionDraw.begin(), s.infectionDraw.end(), rng);  // fallback
    }

    // --- Player deck: rebuild piles from the publicly-known remaining card set ---
    size_t pileTotal = 0;
    for (uint8_t p : s.playerPileSizes) pileTotal += p;
    if (pileTotal == s.playerDraw.size() &&
        s.playerPileSizes.size() == s.playerPileHasEpidemic.size() &&
        !s.playerDraw.empty()) {
        // Cities still in the draw deck = all cities not in a hand or the discard.
        std::array<bool, NUM_CITIES> inDeck;
        inDeck.fill(true);
        for (const Player& pl : s.players)
            for (CityId c : pl.hand) inDeck[static_cast<size_t>(c)] = false;
        for (const Card& c : s.playerDiscard)
            if (c.kind == CardKind::City) inDeck[static_cast<size_t>(c.city)] = false;
        std::vector<CityId> cities;
        for (CityId c = 0; c < NUM_CITIES; ++c)
            if (inDeck[static_cast<size_t>(c)]) cities.push_back(c);
        std::shuffle(cities.begin(), cities.end(), rng);

        std::vector<Card> deck;
        deck.reserve(s.playerDraw.size());
        size_t ci = 0;
        for (size_t p = 0; p < s.playerPileSizes.size(); ++p) {
            int total = s.playerPileSizes[p];
            bool hasEp = s.playerPileHasEpidemic[p] != 0;
            int cityCount = total - (hasEp ? 1 : 0);
            std::vector<Card> pile;
            pile.reserve(static_cast<size_t>(total));
            for (int k = 0; k < cityCount && ci < cities.size(); ++k)
                pile.push_back(Card::cityCard(cities[ci++]));
            if (hasEp) pile.push_back(Card::epidemic());
            std::shuffle(pile.begin(), pile.end(), rng);  // intra-pile order is hidden
            deck.insert(deck.end(), pile.begin(), pile.end());
        }
        if (deck.size() == s.playerDraw.size()) s.playerDraw = std::move(deck);
    }
    return s;
}

// ===========================================================================
// serialize
// ===========================================================================
std::string serialize(const GameState& s) {
    static const char* kColorName[] = {"Blue", "Yellow", "Black", "Red"};
    static const char* kCure[] = {"-", "CURED", "ERAD"};
    std::ostringstream o;

    o << "=== PAIndemic ===\n";
    o << "status=" << (s.status == GameStatus::InProgress ? "InProgress"
                       : s.status == GameStatus::Won ? "Won" : "Lost")
      << " phase=" << static_cast<int>(s.phase)
      << " outbreaks=" << static_cast<int>(s.outbreakCount)
      << " infRate=" << s.infectionRate() << "\n";

    o << "cures:";
    for (int c = 0; c < NUM_COLORS; ++c)
        o << " " << kColorName[c] << "=" << kCure[static_cast<int>(s.cures[c])]
          << "(" << static_cast<int>(s.cubesSupply[c]) << " left)";
    o << "\n";

    o << "stations(" << static_cast<int>(s.stationCount) << "):";
    for (CityId c = 0; c < NUM_CITIES; ++c)
        if (s.hasStation(c)) o << " " << cityName(c);
    o << "\n";

    for (int i = 0; i < static_cast<int>(s.players.size()); ++i) {
        const Player& p = s.players[static_cast<size_t>(i)];
        o << (i == s.currentPlayer ? "* " : "  ") << "P" << i
          << " role=" << static_cast<int>(p.role)
          << " at " << cityName(p.location) << " hand=[";
        for (size_t k = 0; k < p.hand.size(); ++k)
            o << (k ? "," : "") << cityName(p.hand[k]);
        o << "]\n";
    }

    o << "infected cities:";
    for (CityId c = 0; c < NUM_CITIES; ++c) {
        int total = 0;
        for (int col = 0; col < NUM_COLORS; ++col) total += s.cubes[static_cast<size_t>(c)][col];
        if (total == 0) continue;
        o << "\n  " << cityName(c) << ":";
        for (int col = 0; col < NUM_COLORS; ++col)
            if (s.cubes[static_cast<size_t>(c)][col])
                o << " " << kColorName[col] << "=" << static_cast<int>(s.cubes[static_cast<size_t>(c)][col]);
    }
    o << "\n";
    o << "actionsRemaining=" << static_cast<int>(s.actionsRemaining)
      << " playerDeck=" << s.playerDraw.size()
      << " infDeck=" << s.infectionDraw.size() << "\n";
    return o.str();
}

} // namespace paindemic
