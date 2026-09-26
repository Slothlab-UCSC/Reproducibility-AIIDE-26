#include "paindemic/map_data.h"

#include <algorithm>
#include <mutex>
#include <utility>

namespace paindemic {
namespace {

using namespace city;

struct CityDef {
    std::string_view name;
    Color color;
};

// Names + colors in canonical index order (must match the city:: enum).
constexpr CityDef kCities[NUM_CITIES] = {
    // Blue
    {"San Francisco", Color::Blue}, {"Chicago", Color::Blue},
    {"Atlanta", Color::Blue},       {"Montreal", Color::Blue},
    {"New York", Color::Blue},      {"Washington", Color::Blue},
    {"London", Color::Blue},        {"Madrid", Color::Blue},
    {"Paris", Color::Blue},         {"Essen", Color::Blue},
    {"Milan", Color::Blue},         {"St. Petersburg", Color::Blue},
    // Yellow
    {"Los Angeles", Color::Yellow}, {"Mexico City", Color::Yellow},
    {"Miami", Color::Yellow},        {"Bogota", Color::Yellow},
    {"Lima", Color::Yellow},         {"Santiago", Color::Yellow},
    {"Sao Paulo", Color::Yellow},    {"Buenos Aires", Color::Yellow},
    {"Lagos", Color::Yellow},        {"Kinshasa", Color::Yellow},
    {"Khartoum", Color::Yellow},     {"Johannesburg", Color::Yellow},
    // Black
    {"Algiers", Color::Black},  {"Istanbul", Color::Black},
    {"Cairo", Color::Black},    {"Moscow", Color::Black},
    {"Baghdad", Color::Black},  {"Riyadh", Color::Black},
    {"Tehran", Color::Black},   {"Karachi", Color::Black},
    {"Mumbai", Color::Black},   {"Delhi", Color::Black},
    {"Kolkata", Color::Black},  {"Chennai", Color::Black},
    // Red
    {"Beijing", Color::Red},   {"Seoul", Color::Red},
    {"Shanghai", Color::Red},  {"Tokyo", Color::Red},
    {"Osaka", Color::Red},     {"Taipei", Color::Red},
    {"Hong Kong", Color::Red}, {"Bangkok", Color::Red},
    {"Ho Chi Minh City", Color::Red}, {"Jakarta", Color::Red},
    {"Manila", Color::Red},    {"Sydney", Color::Red},
};

// Undirected edge list for the standard Pandemic board. Each edge is added in
// both directions when the table is built, so symmetry is guaranteed.
const std::pair<CityId, CityId> kEdges[] = {
    // Blue cluster
    {SanFrancisco, Chicago}, {SanFrancisco, LosAngeles},
    {Chicago, LosAngeles}, {Chicago, MexicoCity}, {Chicago, Atlanta}, {Chicago, Montreal},
    {Atlanta, Washington}, {Atlanta, Miami},
    {Montreal, NewYork}, {Montreal, Washington},
    {NewYork, Washington}, {NewYork, London}, {NewYork, Madrid},
    {London, Madrid}, {London, Paris}, {London, Essen},
    {Madrid, Paris}, {Madrid, Algiers}, {Madrid, SaoPaulo},
    {Paris, Essen}, {Paris, Milan}, {Paris, Algiers},
    {Essen, Milan}, {Essen, StPetersburg},
    {Milan, Istanbul},
    {StPetersburg, Moscow}, {StPetersburg, Istanbul},
    // Yellow cluster
    {LosAngeles, MexicoCity}, {LosAngeles, Sydney},
    {MexicoCity, Miami}, {MexicoCity, Bogota}, {MexicoCity, Lima},
    {Miami, Bogota},
    {Bogota, Lima}, {Bogota, BuenosAires}, {Bogota, SaoPaulo},
    {Lima, Santiago},
    {SaoPaulo, BuenosAires}, {SaoPaulo, Lagos},
    {Lagos, Khartoum}, {Lagos, Kinshasa},
    {Kinshasa, Khartoum}, {Kinshasa, Johannesburg},
    {Khartoum, Johannesburg}, {Khartoum, Cairo},
    // Black cluster
    {Algiers, Istanbul}, {Algiers, Cairo},
    {Istanbul, Cairo}, {Istanbul, Baghdad}, {Istanbul, Moscow},
    {Cairo, Baghdad}, {Cairo, Riyadh},
    {Moscow, Tehran},
    {Baghdad, Riyadh}, {Baghdad, Tehran}, {Baghdad, Karachi},
    {Riyadh, Karachi},
    {Tehran, Karachi}, {Tehran, Delhi},
    {Karachi, Delhi}, {Karachi, Mumbai},
    {Mumbai, Delhi}, {Mumbai, Chennai},
    {Delhi, Chennai}, {Delhi, Kolkata},
    {Kolkata, Chennai}, {Kolkata, Bangkok}, {Kolkata, HongKong},
    {Chennai, Bangkok}, {Chennai, Jakarta},
    // Red cluster
    {Beijing, Shanghai}, {Beijing, Seoul},
    {Seoul, Shanghai}, {Seoul, Tokyo},
    {Shanghai, Tokyo}, {Shanghai, Taipei}, {Shanghai, HongKong},
    {Tokyo, Osaka}, {Tokyo, SanFrancisco},
    {Osaka, Taipei},
    {Taipei, HongKong}, {Taipei, Manila},
    {HongKong, Bangkok}, {HongKong, HoChiMinhCity}, {HongKong, Manila},
    {Bangkok, HoChiMinhCity}, {Bangkok, Jakarta},
    {HoChiMinhCity, Jakarta}, {HoChiMinhCity, Manila},
    {Jakarta, Sydney},
    {Manila, SanFrancisco}, {Manila, Sydney},
};

std::array<CityInfo, NUM_CITIES> buildTable() {
    std::array<CityInfo, NUM_CITIES> t{};
    for (int i = 0; i < NUM_CITIES; ++i) {
        t[i].name = kCities[i].name;
        t[i].color = kCities[i].color;
    }
    for (const auto& [a, b] : kEdges) {
        t[a].neighbors.push_back(b);
        t[b].neighbors.push_back(a);
    }
    for (auto& ci : t) {
        std::sort(ci.neighbors.begin(), ci.neighbors.end());
    }
    return t;
}

} // namespace

const std::array<CityInfo, NUM_CITIES>& cityTable() {
    static const std::array<CityInfo, NUM_CITIES> table = buildTable();
    return table;
}

bool areAdjacent(CityId a, CityId b) {
    const auto& n = cityInfo(a).neighbors;
    return std::find(n.begin(), n.end(), b) != n.end();
}

namespace {
// All-pairs shortest paths via Floyd-Warshall over the base adjacency, built once.
const std::array<std::array<int16_t, NUM_CITIES>, NUM_CITIES>& distanceTable() {
    static const auto table = [] {
        constexpr int16_t INF = 1000;
        std::array<std::array<int16_t, NUM_CITIES>, NUM_CITIES> d{};
        for (int i = 0; i < NUM_CITIES; ++i)
            for (int j = 0; j < NUM_CITIES; ++j)
                d[i][j] = (i == j) ? 0 : INF;
        for (int i = 0; i < NUM_CITIES; ++i)
            for (CityId nb : cityInfo(static_cast<CityId>(i)).neighbors)
                d[i][nb] = 1;
        for (int k = 0; k < NUM_CITIES; ++k)
            for (int i = 0; i < NUM_CITIES; ++i)
                for (int j = 0; j < NUM_CITIES; ++j)
                    if (d[i][k] + d[k][j] < d[i][j])
                        d[i][j] = static_cast<int16_t>(d[i][k] + d[k][j]);
        return d;
    }();
    return table;
}
} // namespace

int baseDistance(CityId a, CityId b) {
    return distanceTable()[static_cast<size_t>(a)][static_cast<size_t>(b)];
}

} // namespace paindemic
