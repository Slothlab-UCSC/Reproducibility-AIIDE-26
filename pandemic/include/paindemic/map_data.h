#pragma once
#include "paindemic/types.h"
#include <array>
#include <string_view>
#include <vector>

namespace paindemic {

// Stable city indices (0..47), grouped by color in the canonical board order.
namespace city {
enum : int8_t {
    // Blue (0-11)
    SanFrancisco = 0, Chicago, Atlanta, Montreal, NewYork, Washington,
    London, Madrid, Paris, Essen, Milan, StPetersburg,
    // Yellow (12-23)
    LosAngeles, MexicoCity, Miami, Bogota, Lima, Santiago,
    SaoPaulo, BuenosAires, Lagos, Kinshasa, Khartoum, Johannesburg,
    // Black (24-35)
    Algiers, Istanbul, Cairo, Moscow, Baghdad, Riyadh,
    Tehran, Karachi, Mumbai, Delhi, Kolkata, Chennai,
    // Red (36-47)
    Beijing, Seoul, Shanghai, Tokyo, Osaka, Taipei,
    HongKong, Bangkok, HoChiMinhCity, Jakarta, Manila, Sydney
};
} // namespace city

inline constexpr CityId STARTING_CITY = city::Atlanta;

struct CityInfo {
    std::string_view name;
    Color color;
    std::vector<CityId> neighbors;  // symmetric adjacency
};

// Returns the static, immutable 48-entry city table (lazily built once).
const std::array<CityInfo, NUM_CITIES>& cityTable();

inline const CityInfo& cityInfo(CityId c) { return cityTable()[static_cast<size_t>(c)]; }
inline Color cityColor(CityId c) { return cityInfo(c).color; }
inline std::string_view cityName(CityId c) { return cityInfo(c).name; }

bool areAdjacent(CityId a, CityId b);

// Shortest-path distance (in drive/ferry steps) between two cities on the base
// board, ignoring research stations. Precomputed all-pairs; O(1) lookup.
int baseDistance(CityId a, CityId b);

} // namespace paindemic
