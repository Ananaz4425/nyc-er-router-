/*
 * navigation.cpp
 * NYC Emergency ER Router — C++ Implementation
 *
 * This file mirrors the Dijkstra algorithm used in server.py.
 * It finds the nearest safe hospital from a patient location,
 * avoiding hazard zones using a min-heap priority queue.
 *
 * Compile:  g++ -O2 -o navigation navigation.cpp
 * Run:      ./navigation
 */

#include <iostream>
#include <vector>
#include <queue>
#include <cmath>
#include <string>
#include <limits>

// ─── Constants ────────────────────────────────────────────────────────────────
const double PI             = 3.14159265358979323846;
const double EARTH_RADIUS   = 6371.0;   // km
const double HAZARD_RADIUS  = 0.8;      // km — same as server.py
const double BLOCK_PENALTY  = 999.0;    // hospital inside hazard zone
const double PATH_PENALTY   = 10.0;     // path midpoint near hazard

// ─── Data Structures ──────────────────────────────────────────────────────────
struct Hospital {
    std::string name;
    double lat, lon;
};

struct Hazard {
    double lat, lon;
};

// Min-heap node: (cost, hospital_index, raw_distance)
struct Node {
    double cost;
    int    index;
    double raw_dist;

    // Min-heap: smallest cost first
    bool operator>(const Node& other) const {
        return cost > other.cost;
    }
};

struct Result {
    std::string name;
    double lat, lon;
    double path_cost_km;
    double adjusted_cost;
    bool   found;
};

// ─── Haversine Distance ───────────────────────────────────────────────────────
double toRad(double deg) {
    return deg * PI / 180.0;
}

double haversine(double lat1, double lon1, double lat2, double lon2) {
    double dlat = toRad(lat2 - lat1);
    double dlon = toRad(lon2 - lon1);
    double a = std::sin(dlat / 2) * std::sin(dlat / 2)
             + std::cos(toRad(lat1)) * std::cos(toRad(lat2))
             * std::sin(dlon / 2) * std::sin(dlon / 2);
    return EARTH_RADIUS * 2.0 * std::asin(std::sqrt(a));
}

// ─── Dijkstra Algorithm ───────────────────────────────────────────────────────
Result navigation(double p_lat, double p_lon,
                const std::vector<Hospital>& hospitals,
                const std::vector<Hazard>&   hazards) {

    // Priority queue: min-heap ordered by cost
    std::priority_queue<Node, std::vector<Node>, std::greater<Node>> heap;
    std::vector<bool> visited(hospitals.size(), false);

    // Push all hospitals into the heap with their costs
    for (int i = 0; i < (int)hospitals.size(); i++) {
        double dist = haversine(p_lat, p_lon, hospitals[i].lat, hospitals[i].lon);
        double penalty = 0.0;

        for (const auto& haz : hazards) {
            // Check if midpoint of path is inside a hazard zone
            double mid_lat = (p_lat + hospitals[i].lat) / 2.0;
            double mid_lon = (p_lon + hospitals[i].lon) / 2.0;
            if (haversine(mid_lat, mid_lon, haz.lat, haz.lon) < HAZARD_RADIUS) {
                penalty += PATH_PENALTY;
            }
            // Block hospitals inside a hazard zone
            if (haversine(hospitals[i].lat, hospitals[i].lon, haz.lat, haz.lon) < HAZARD_RADIUS) {
                penalty += BLOCK_PENALTY;
            }
        }

        heap.push({dist + penalty, i, dist});
    }

    // Pop the lowest-cost hospital (Dijkstra greedy extraction)
    while (!heap.empty()) {
        Node current = heap.top();
        heap.pop();

        if (visited[current.index]) continue;
        visited[current.index] = true;

        // Accept first non-blocked hospital (blocked ones have cost >= 999)
        if (current.cost < 500.0) {
            const Hospital& h = hospitals[current.index];
            return {h.name, h.lat, h.lon,
                    current.raw_dist, current.cost, true};
        }
    }

    return {"", 0, 0, 0, 0, false}; // No safe hospital found
}

// ─── Main ─────────────────────────────────────────────────────────────────────
int main() {

    // Manhattan Hospitals (matches server.py)
    std::vector<Hospital> hospitals = {
        {"Bellevue Hospital Center",              40.7394, -73.9759},
        {"NYU Langone Health",                    40.7421, -73.9740},
        {"NewYork-Presbyterian/Weill Cornell",    40.7647, -73.9542},
        {"Mount Sinai Hospital",                  40.7900, -73.9523},
        {"Lenox Hill Hospital",                   40.7716, -73.9566},
        {"NYC Health + Hospitals / Harlem",       40.8116, -73.9414},
        {"NewYork-Presbyterian/Columbia",         40.8402, -73.9408},
        {"Mount Sinai West",                      40.7677, -73.9863},
        {"Mount Sinai Morningside",               40.8037, -73.9614},
        {"NYC Health + Hospitals / Metropolitan", 40.7959, -73.9389},
    };

    // Example hazards
    std::vector<Hazard> hazards = {
        {40.748, -73.985},
        {40.761, -73.978},
        {40.780, -73.950},
    };

    // Test patient locations
    std::vector<std::pair<std::string, std::pair<double,double>>> test_locations = {
        {"Times Square",      {40.7580, -73.9855}},
        {"Central Park",      {40.7851, -73.9683}},
        {"Harlem",            {40.8116, -73.9465}},
        {"Lower East Side",   {40.7157, -73.9863}},
        {"Upper West Side",   {40.7870, -73.9754}},
    };

    std::cout << "=== NYC Emergency ER Router — C++ Dijkstra ===" << std::endl;
    std::cout << "Hazard radius: " << HAZARD_RADIUS << " km" << std::endl;
    std::cout << "Hospitals loaded: " << hospitals.size() << std::endl;
    std::cout << "Hazards loaded: " << hazards.size() << std::endl;
    std::cout << std::string(50, '-') << std::endl;

    for (const auto& loc : test_locations) {
        double lat = loc.second.first;
        double lon = loc.second.second;

        Result r = navigation(lat, lon, hospitals, hazards);

        std::cout << "Patient: " << loc.first << std::endl;

        if (r.found) {
            std::cout << "  -> Nearest ER : " << r.name << std::endl;
            std::cout << "  -> Distance   : " << r.path_cost_km << " km" << std::endl;
            std::cout << "  -> Adj. cost  : " << r.adjusted_cost << std::endl;
        } else {
            std::cout << "  -> No safe hospital found!" << std::endl;
        }
        std::cout << std::string(50, '-') << std::endl;
    }

    return 0;
}
