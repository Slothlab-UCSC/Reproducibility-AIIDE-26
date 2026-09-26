#include "paindemic/state_io.h"
#include "paindemic/map_data.h"

#include <array>
#include <cctype>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace paindemic {
namespace {

// Color order used in every serialized array (matches the Color enum index).
constexpr std::array<const char*, NUM_COLORS> kColorTok = {"blue", "yellow", "black", "red"};

// Restricted-Pandemic roles use these tokens; the full set is mapped for completeness.
const char* roleTok(RoleType r) {
    switch (r) {
        case RoleType::Scientist:            return "scientist";
        case RoleType::Researcher:           return "researcher";
        case RoleType::QuarantineSpecialist: return "quarantine";
        case RoleType::Medic:                return "medic";
        case RoleType::Dispatcher:           return "dispatcher";
        case RoleType::OperationsExpert:     return "operations";
        case RoleType::ContingencyPlanner:   return "contingency";
        default:                             return "scientist";
    }
}
RoleType roleFromTok(std::string_view t) {
    if (t == "scientist")  return RoleType::Scientist;
    if (t == "researcher") return RoleType::Researcher;
    if (t == "quarantine") return RoleType::QuarantineSpecialist;
    if (t == "medic")      return RoleType::Medic;
    if (t == "dispatcher") return RoleType::Dispatcher;
    if (t == "operations") return RoleType::OperationsExpert;
    if (t == "contingency") return RoleType::ContingencyPlanner;
    throw std::runtime_error("unknown role token: " + std::string(t));
}

// Normalize a C++ display name ("New York", "St. Petersburg") to the Python key
// ("new_york", "st_petersburg"): lowercase, '.'/space -> '_', collapse repeats.
std::string normalize(std::string_view name) {
    std::string out;
    out.reserve(name.size());
    for (char c : name) {
        if (c == ' ' || c == '.') {
            if (!out.empty() && out.back() != '_') out.push_back('_');
        } else {
            out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        }
    }
    while (!out.empty() && out.back() == '_') out.pop_back();
    return out;
}

const std::unordered_map<std::string, CityId>& nameToId() {
    static const std::unordered_map<std::string, CityId> m = [] {
        std::unordered_map<std::string, CityId> map;
        for (CityId c = 0; c < NUM_CITIES; ++c) map.emplace(normalize(cityName(c)), c);
        return map;
    }();
    return m;
}

// --- small parsing helpers ---------------------------------------------------

std::vector<std::string> split(std::string_view s, char delim) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : s) {
        if (c == delim) { out.push_back(cur); cur.clear(); }
        else cur.push_back(c);
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

} // namespace

std::string pyCityName(CityId c) {
    return (c >= 0 && c < NUM_CITIES) ? normalize(cityName(c)) : std::string("none");
}

CityId cityFromPyName(std::string_view name) {
    auto it = nameToId().find(std::string(name));
    return it == nameToId().end() ? NO_CITY : it->second;
}

std::string writeState(const GameState& s) {
    std::ostringstream o;
    o << "meta players=" << s.players.size()
      << " current=" << static_cast<int>(s.currentPlayer)
      << " phase=actions"
      << " actions=" << static_cast<int>(s.actionsRemaining)
      << " infrate=" << s.infectionRate()
      << " outbreaks=" << static_cast<int>(s.outbreakCount)
      << " turn=0"
      << " deck=" << s.playerDraw.size()
      << " initdeck=" << s.initialPlayerDeckSize << "\n";

    for (size_t i = 0; i < s.players.size(); ++i) {
        const Player& p = s.players[i];
        o << "player " << i << " role=" << roleTok(p.role)
          << " loc=" << pyCityName(p.location) << " hand=";
        for (size_t k = 0; k < p.hand.size(); ++k)
            o << (k ? "," : "") << pyCityName(p.hand[k]);
        o << "\n";
    }

    o << "cubes";
    for (CityId c = 0; c < NUM_CITIES; ++c) {
        int tot = 0;
        for (int k = 0; k < NUM_COLORS; ++k) tot += s.cubes[static_cast<size_t>(c)][k];
        if (!tot) continue;
        o << " " << pyCityName(c) << "=";
        for (int k = 0; k < NUM_COLORS; ++k)
            o << (k ? "," : "") << static_cast<int>(s.cubes[static_cast<size_t>(c)][k]);
    }
    o << "\n";

    o << "supply";
    for (int k = 0; k < NUM_COLORS; ++k) o << (k ? "," : " ") << static_cast<int>(s.cubesSupply[k]);
    o << "\n";

    o << "stations";
    bool first = true;
    for (CityId c = 0; c < NUM_CITIES; ++c)
        if (s.hasStation(c)) { o << (first ? " " : ",") << pyCityName(c); first = false; }
    o << "\n";

    o << "cures";
    for (int k = 0; k < NUM_COLORS; ++k)
        o << (k ? "," : " ") << static_cast<int>(s.cures[k]);
    o << "\n";

    o << "discard";
    first = true;
    for (const Card& c : s.playerDiscard)
        if (c.kind == CardKind::City) { o << (first ? " " : ",") << pyCityName(c.city); first = false; }
    o << "\n";
    return o.str();
}

GameState parseState(std::string_view block) {
    GameState s;
    s.status = GameStatus::InProgress;
    s.phase = Phase::PlayerActions;
    s.discardingPlayer = -1;
    s.opsFlightUsedThisTurn = false;
    for (auto& row : s.cubes) row.fill(0);
    s.stations.fill(false);
    s.stationCount = 0;
    s.cures.fill(CureStatus::Uncured);

    int nplayers = 0, deckSize = 0;

    std::istringstream in{std::string(block)};
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        auto tok = split(line, ' ');
        // drop empty tokens (from double spaces)
        std::vector<std::string> t;
        for (auto& x : tok) if (!x.empty()) t.push_back(x);
        if (t.empty()) continue;
        const std::string& head = t[0];

        if (head == "meta") {
            for (size_t i = 1; i < t.size(); ++i) {
                auto eq = t[i].find('=');
                if (eq == std::string::npos) continue;
                std::string k = t[i].substr(0, eq), v = t[i].substr(eq + 1);
                if (k == "players") { nplayers = std::stoi(v); s.players.resize(static_cast<size_t>(nplayers)); }
                else if (k == "current") s.currentPlayer = static_cast<uint8_t>(std::stoi(v));
                else if (k == "actions") s.actionsRemaining = static_cast<uint8_t>(std::stoi(v));
                else if (k == "outbreaks") s.outbreakCount = static_cast<uint8_t>(std::stoi(v));
                else if (k == "deck") deckSize = std::stoi(v);
                else if (k == "initdeck") s.initialPlayerDeckSize = static_cast<uint16_t>(std::stoi(v));
                else if (k == "infrate") {
                    int r = std::stoi(v);  // map rate value -> a track index giving that rate
                    s.infectionRateIndex = static_cast<uint8_t>(r <= 2 ? 0 : r == 3 ? 3 : 5);
                }
            }
        } else if (head == "player") {
            if (t.size() < 4) throw std::runtime_error("bad player line: " + line);
            int idx = std::stoi(t[1]);
            Player p;
            for (size_t i = 2; i < t.size(); ++i) {
                auto eq = t[i].find('=');
                if (eq == std::string::npos) continue;
                std::string k = t[i].substr(0, eq), v = t[i].substr(eq + 1);
                if (k == "role") p.role = roleFromTok(v);
                else if (k == "loc") p.location = cityFromPyName(v);
                else if (k == "hand") {
                    if (!v.empty())
                        for (auto& nm : split(v, ',')) p.hand.push_back(cityFromPyName(nm));
                }
            }
            s.players[static_cast<size_t>(idx)] = p;
        } else if (head == "cubes") {
            for (size_t i = 1; i < t.size(); ++i) {
                auto eq = t[i].find('=');
                if (eq == std::string::npos) continue;
                CityId c = cityFromPyName(t[i].substr(0, eq));
                auto counts = split(t[i].substr(eq + 1), ',');
                for (int k = 0; k < NUM_COLORS && k < static_cast<int>(counts.size()); ++k)
                    s.cubes[static_cast<size_t>(c)][k] = static_cast<uint8_t>(std::stoi(counts[k]));
            }
        } else if (head == "supply") {
            auto vals = split(t.size() > 1 ? t[1] : "", ',');
            for (int k = 0; k < NUM_COLORS && k < static_cast<int>(vals.size()); ++k)
                s.cubesSupply[k] = static_cast<uint8_t>(std::stoi(vals[k]));
        } else if (head == "stations") {
            if (t.size() > 1)
                for (auto& nm : split(t[1], ',')) {
                    CityId c = cityFromPyName(nm);
                    if (c != NO_CITY) { s.stations[static_cast<size_t>(c)] = true; ++s.stationCount; }
                }
        } else if (head == "cures") {
            auto vals = split(t.size() > 1 ? t[1] : "", ',');
            for (int k = 0; k < NUM_COLORS && k < static_cast<int>(vals.size()); ++k)
                s.cures[k] = static_cast<CureStatus>(std::stoi(vals[k]));
        } else if (head == "discard") {
            if (t.size() > 1)
                for (auto& nm : split(t[1], ',')) {
                    CityId c = cityFromPyName(nm);
                    if (c != NO_CITY) s.playerDiscard.push_back(Card::cityCard(c));
                }
        }
    }

    // Reconstruct a dummy draw pile of the recorded size (only .size() feeds the heuristic).
    s.playerDraw.assign(static_cast<size_t>(deckSize), Card::cityCard(0));
    if (s.initialPlayerDeckSize == 0)
        s.initialPlayerDeckSize = static_cast<uint16_t>(deckSize);
    if (s.players.empty()) throw std::runtime_error("state has no players");
    return s;
}

} // namespace paindemic
