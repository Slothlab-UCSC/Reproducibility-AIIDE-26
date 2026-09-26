#pragma once
#include "paindemic/types.h"
#include "paindemic/map_data.h"

#include <algorithm>
#include <vector>

namespace paindemic {

struct Player {
    RoleType role = RoleType::Scientist;
    CityId location = STARTING_CITY;
    std::vector<CityId> hand;  // city cards held (by city id)

    bool hasCityCard(CityId c) const {
        return std::find(hand.begin(), hand.end(), c) != hand.end();
    }

    // Number of cards of a given color in hand (used for cure eligibility).
    int colorCount(Color color) const {
        int n = 0;
        for (CityId c : hand)
            if (cityColor(c) == color) ++n;
        return n;
    }

    void removeCard(CityId c) {
        auto it = std::find(hand.begin(), hand.end(), c);
        if (it != hand.end()) hand.erase(it);
    }
};

} // namespace paindemic
