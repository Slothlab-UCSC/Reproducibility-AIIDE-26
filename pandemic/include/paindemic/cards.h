#pragma once
#include "paindemic/types.h"

namespace paindemic {

// A card identity. In v1 the player deck holds City and Epidemic cards only
// (Event cards are a future milestone). Infection cards are always City cards.
enum class CardKind : int8_t { City, Epidemic };

struct Card {
    CardKind kind = CardKind::City;
    CityId city = NO_CITY;   // valid when kind == City

    static Card cityCard(CityId c) { return Card{CardKind::City, c}; }
    static Card epidemic() { return Card{CardKind::Epidemic, NO_CITY}; }

    bool operator==(const Card&) const = default;
};

} // namespace paindemic
