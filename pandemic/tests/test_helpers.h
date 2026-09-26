#pragma once
#include "paindemic/engine.h"
#include "paindemic/map_data.h"
#include <algorithm>

namespace pt {
using namespace paindemic;

inline int totalCubesOnBoard(const GameState& s) {
    int t = 0;
    for (CityId c = 0; c < NUM_CITIES; ++c)
        for (int col = 0; col < NUM_COLORS; ++col)
            t += s.cubes[static_cast<size_t>(c)][col];
    return t;
}

inline int cubesOfColorOnBoard(const GameState& s, Color color) {
    int t = 0;
    for (CityId c = 0; c < NUM_CITIES; ++c)
        t += s.cubes[static_cast<size_t>(c)][static_cast<int>(color)];
    return t;
}

inline bool hasActionType(const std::vector<Action>& as, ActionType t) {
    return std::any_of(as.begin(), as.end(), [&](const Action& a) { return a.type == t; });
}

inline int countActionType(const std::vector<Action>& as, ActionType t) {
    return static_cast<int>(std::count_if(as.begin(), as.end(),
        [&](const Action& a) { return a.type == t; }));
}

// Find a legal action of a given type (asserts existence at call site).
inline const Action* findAction(const std::vector<Action>& as, ActionType t) {
    auto it = std::find_if(as.begin(), as.end(), [&](const Action& a) { return a.type == t; });
    return it == as.end() ? nullptr : &*it;
}

} // namespace pt
