#include "paindemic/heuristic.h"
#include "paindemic/map_data.h"

#include <algorithm>
#include <array>

namespace paindemic {
namespace {

// Paper eq.8 weights (grid-searched in the paper).
constexpr double W_DSURV = 0.5;
constexpr double W_DCURE = 0.5;
constexpr double W_CARDS = 1.0;
constexpr double W_DISC  = 0.5;
constexpr double W_INF   = 0.6;
constexpr double W_DIST  = 0.6;
constexpr double W_CURES = 24.0;

int colorIdx(Color c) { return static_cast<int>(c); }

// Per-state distance helper that folds in research-station shuttle links: any two
// stations are one step apart, so reaching a destination may be cheaper by walking
// to the nearest station, shuttling, and walking out.
struct Distances {
    std::array<int, NUM_CITIES> nearestStation;
    bool canShuttle;

    explicit Distances(const GameState& s) {
        canShuttle = s.stationCount >= 2;
        for (CityId c = 0; c < NUM_CITIES; ++c) {
            int best = 1000;
            for (CityId t = 0; t < NUM_CITIES; ++t)
                if (s.hasStation(t)) best = std::min(best, baseDistance(c, t));
            nearestStation[static_cast<size_t>(c)] = best;
        }
    }

    int between(CityId a, CityId b) const {
        int d = baseDistance(a, b);
        if (canShuttle) {
            int viaStation = nearestStation[static_cast<size_t>(a)] + 1 +
                             nearestStation[static_cast<size_t>(b)];
            d = std::min(d, viaStation);
        }
        return d;
    }
};

int cureRequirement(RoleType r) { return r == RoleType::Scientist ? 4 : 5; }

} // namespace

HeuristicTerms heuristicTerms(const GameState& s) {
    const Distances dist(s);
    HeuristicTerms h{};

    // Cube counts.
    int totalCubes = 0;
    for (CityId c = 0; c < NUM_CITIES; ++c)
        for (int k = 0; k < NUM_COLORS; ++k)
            totalCubes += s.cubes[static_cast<size_t>(c)][k];

    bool active[NUM_COLORS];
    for (int k = 0; k < NUM_COLORS; ++k)
        active[k] = (s.cures[k] == CureStatus::Uncured);

    // eq.1 h_dsurv: average over cubes of player-to-infected-city distance.
    double dsurvSum = 0.0;
    for (const Player& p : s.players)
        for (CityId c = 0; c < NUM_CITIES; ++c) {
            int cubes = 0;
            for (int k = 0; k < NUM_COLORS; ++k) cubes += s.cubes[static_cast<size_t>(c)][k];
            if (cubes) dsurvSum += dist.between(p.location, c) * cubes;
        }
    h.dsurv = totalCubes > 0 ? dsurvSum / totalCubes : 0.0;

    // eq.2 h_dcure: each player's distance to the closest research station.
    double dcure = 0.0;
    for (const Player& p : s.players)
        dcure += dist.nearestStation[static_cast<size_t>(p.location)];
    h.dcure = dcure;

    // eq.3 h_cards: per active color, fewest cards any player still needs.
    // eq.4 h_disc: per active color, cards of that color already discarded.
    std::array<int, NUM_COLORS> discardByColor{};
    for (const Card& c : s.playerDiscard)
        if (c.kind == CardKind::City)
            discardByColor[colorIdx(cityColor(c.city))]++;

    double cards = 0.0, disc = 0.0;
    for (int k = 0; k < NUM_COLORS; ++k) {
        if (!active[k]) continue;
        Color color = static_cast<Color>(k);
        int missing = 1 << 30;
        for (const Player& p : s.players) {
            int need = cureRequirement(p.role) - p.colorCount(color);
            missing = std::min(missing, std::max(0, need));
        }
        cards += missing;
        disc += discardByColor[k];
    }
    h.cards = cards;
    h.disc = disc;

    // eq.5 h_inf: total cubes on the board.
    h.inf = totalCubes;

    // eq.6 h_dist: mean pairwise city distance, scaled by fraction of turns left.
    double pairSum = 0.0;
    for (CityId a = 0; a < NUM_CITIES; ++a)
        for (CityId b = 0; b < NUM_CITIES; ++b)
            if (a != b) pairSum += dist.between(a, b);
    double meanPair = pairSum / (NUM_CITIES * (NUM_CITIES - 1));
    double turnsRatio = s.initialPlayerDeckSize > 0
        ? static_cast<double>(s.playerDraw.size()) / s.initialPlayerDeckSize
        : 1.0;
    h.dist = meanPair * turnsRatio;

    // eq.7 h_cures: diseases still lacking a cure.
    int uncured = 0;
    for (int k = 0; k < NUM_COLORS; ++k)
        if (s.cures[k] == CureStatus::Uncured) ++uncured;
    h.cures = uncured;

    return h;
}

double HeuristicTerms::total() const {
    return total(true, true);
}

// Goal-toggled: the paper zeroes h_dsurv unless pursuing "survive" (findDiseases) and
// h_dcure unless pursuing "discover cure" (findRs). All other terms are always included.
double HeuristicTerms::total(bool findDiseases, bool findRs) const {
    return W_DSURV * (findDiseases ? dsurv : 0.0) +
           W_DCURE * (findRs ? dcure : 0.0) +
           W_CARDS * cards + W_DISC * disc + W_INF * inf + W_DIST * dist + W_CURES * cures;
}

double evaluateState(const GameState& s) {
    return heuristicTerms(s).total();
}

double evaluateState(const GameState& s, bool findDiseases, bool findRs) {
    return heuristicTerms(s).total(findDiseases, findRs);
}

} // namespace paindemic
