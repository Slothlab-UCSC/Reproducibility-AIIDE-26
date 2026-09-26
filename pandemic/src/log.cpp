#include "paindemic/log.h"
#include "paindemic/map_data.h"

#include <sstream>

namespace paindemic {

std::string roleName(RoleType r) {
    switch (r) {
        case RoleType::ContingencyPlanner:   return "Contingency Planner";
        case RoleType::Dispatcher:           return "Dispatcher";
        case RoleType::Medic:                return "Medic";
        case RoleType::OperationsExpert:     return "Operations Expert";
        case RoleType::QuarantineSpecialist: return "Quarantine Specialist";
        case RoleType::Researcher:           return "Researcher";
        case RoleType::Scientist:            return "Scientist";
        default:                             return "Unknown";
    }
}

std::string colorName(Color c) {
    switch (c) {
        case Color::Blue:   return "Blue";
        case Color::Yellow: return "Yellow";
        case Color::Black:  return "Black";
        case Color::Red:    return "Red";
        default:            return "None";
    }
}

namespace {
std::string cityStr(CityId c) {
    return c == NO_CITY ? "?" : std::string(cityName(c));
}
std::string who(int player, RoleType role) {
    std::ostringstream o;
    o << "P" << player << " (" << roleName(role) << ")";
    return o.str();
}
} // namespace

std::string describeAction(int player, RoleType role, const Action& a) {
    std::ostringstream o;
    o << who(player, role) << ": ";
    switch (a.type) {
        case ActionType::Pass:
            o << "Pass"; break;
        case ActionType::DriveFerry:
            o << "Drive/Ferry to " << cityStr(a.target); break;
        case ActionType::DirectFlight:
            o << "Direct Flight to " << cityStr(a.target) << " (discard " << cityStr(a.card) << ")"; break;
        case ActionType::CharterFlight:
            o << "Charter Flight to " << cityStr(a.target) << " (discard " << cityStr(a.card) << ")"; break;
        case ActionType::ShuttleFlight:
            o << "Shuttle Flight to " << cityStr(a.target); break;
        case ActionType::BuildStation:
            o << "Build research station"; break;
        case ActionType::TreatDisease:
            o << "Treat " << colorName(a.color); break;
        case ActionType::ShareGive:
            o << "Give " << cityStr(a.card) << " to P" << int(a.partner); break;
        case ActionType::ShareTake:
            o << "Take " << cityStr(a.card) << " from P" << int(a.partner); break;
        case ActionType::DiscoverCure:
            o << "Discover cure for " << colorName(a.color); break;
        case ActionType::OperationsFlight:
            o << "Ops Flight to " << cityStr(a.target) << " (discard " << cityStr(a.card) << ")"; break;
        case ActionType::DispatcherMovePawn:
            o << "Move P" << int(a.pawn) << " to " << cityStr(a.target); break;
        case ActionType::DispatcherSummon:
            o << "Summon P" << int(a.pawn) << " to " << cityStr(a.target); break;
        case ActionType::Discard:
            o << "Discard " << cityStr(a.card); break;
        default:
            o << "(action)"; break;
    }
    return o.str();
}

std::string describe(const Event& e) {
    std::ostringstream o;
    switch (e.type) {
        case EventType::TurnStart:
            o << "-- Turn: " << who(e.player, e.role) << " --";
            break;
        case EventType::ActionPerformed:
            o << "  " << describeAction(e.player, e.role, e.action);
            break;
        case EventType::PlayerCardDrawn:
            if (e.card.kind == CardKind::Epidemic)
                o << "    draws EPIDEMIC card";
            else
                o << "    draws player card: " << cityStr(e.card.city)
                  << " (" << colorName(cityColor(e.card.city)) << ")";
            break;
        case EventType::EpidemicIncrease:
            o << "    EPIDEMIC! infection rate -> " << e.amount;
            break;
        case EventType::EpidemicInfect:
            o << "    epidemic infects " << cityStr(e.city) << " with 3 "
              << colorName(cityColor(e.city)) << " cubes";
            break;
        case EventType::EpidemicIntensify:
            o << "    intensify: infection discard reshuffled onto the deck";
            break;
        case EventType::InfectionDrawn:
            o << "    infect: " << cityStr(e.city)
              << " (" << colorName(cityColor(e.city)) << ")";
            break;
        case EventType::Outbreak:
            o << "    OUTBREAK in " << cityStr(e.city) << " (" << colorName(e.color)
              << ")! outbreaks=" << e.amount;
            break;
        case EventType::HandDiscard:
            o << "    " << who(e.player, e.role) << " discards " << cityStr(e.card.city);
            break;
        case EventType::CureDiscovered:
            o << "  *** " << colorName(e.color) << " disease CURED ***";
            break;
        case EventType::Eradicated:
            o << "  *** " << colorName(e.color) << " disease ERADICATED ***";
            break;
        case EventType::GameWon:
            o << "==> GAME WON! All diseases cured.";
            break;
        case EventType::GameLost: {
            const char* why = "unknown";
            switch (static_cast<LossReason>(e.amount)) {
                case LossReason::EighthOutbreak: why = "8th outbreak"; break;
                case LossReason::CubesOut:       why = "ran out of disease cubes"; break;
                case LossReason::PlayerDeckOut:  why = "player deck exhausted"; break;
                default: break;
            }
            o << "==> GAME LOST (" << why << ").";
            break;
        }
    }
    return o.str();
}

} // namespace paindemic
