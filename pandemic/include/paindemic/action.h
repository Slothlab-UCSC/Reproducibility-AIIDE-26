#pragma once
#include "paindemic/types.h"

namespace paindemic {

// A single, fully-specified move. A small fixed set of integer args covers every
// ActionType; unused args stay at their defaults. Keeping Action a flat, copyable
// value makes it trivial for an agent to enumerate, index, store, and serialize.
struct Action {
    ActionType type = ActionType::Pass;

    CityId target = NO_CITY;   // destination city, or city referenced by the action
    Color color = Color::None; // disease color (TreatDisease / DiscoverCure)
    int8_t partner = -1;       // other player index (ShareGive/ShareTake/Dispatcher)
    CityId card = NO_CITY;     // a card to discard/use distinct from `target`
                               // (DirectFlight uses target as both; DiscoverCure/
                               //  Discard use this; OperationsFlight discards `card`)
    int8_t pawn = -1;          // pawn being moved (Dispatcher), defaults to current

    bool operator==(const Action&) const = default;

    // Convenience constructors for the common cases.
    static Action pass() { return Action{ActionType::Pass}; }
    static Action drive(CityId to) { Action a; a.type = ActionType::DriveFerry; a.target = to; return a; }
    static Action build() { return Action{ActionType::BuildStation}; }
    static Action treat(Color c) { Action a; a.type = ActionType::TreatDisease; a.color = c; return a; }
    static Action discardCard(CityId c) { Action a; a.type = ActionType::Discard; a.card = c; return a; }
};

} // namespace paindemic
