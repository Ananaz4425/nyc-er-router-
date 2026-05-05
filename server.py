"""
NYC Emergency ER Router - server.py
Features: Address search, multi-patient, incident log, turn-by-turn directions
Run: pip install flask flask-cors && python server.py
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import heapq
import random
import math
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime

app = Flask(__name__, static_folder=".")
CORS(app)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergency.db")

# ─── Manhattan Hospitals ───────────────────────────────────────────────────────
MANHATTAN_HOSPITALS = [
    ("Bellevue Hospital Center",              40.7394, -73.9759),
    ("NYU Langone Health",                    40.7421, -73.9740),
    ("NewYork-Presbyterian/Weill Cornell",    40.7647, -73.9542),
    ("Mount Sinai Hospital",                  40.7900, -73.9523),
    ("Lenox Hill Hospital",                   40.7716, -73.9566),
    ("NYC Health + Hospitals / Harlem",       40.8116, -73.9414),
    ("NewYork-Presbyterian/Columbia",         40.8402, -73.9408),
    ("Mount Sinai West",                      40.7677, -73.9863),
    ("Mount Sinai Morningside",               40.8037, -73.9614),
    ("NYC Health + Hospitals / Metropolitan", 40.7959, -73.9389),
]

NYC_CLOSURE_API = (
    "https://data.cityofnewyork.us/resource/i6b5-j7bu.json"
    "?borough=MANHATTAN&$limit=50"
)

def fetch_real_closures():
    print("Fetching real NYC road closures...")
    try:
        req = urllib.request.Request(NYC_CLOSURE_API,
              headers={"Accept": "application/json", "User-Agent": "NYCERRouter/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            records = json.loads(resp.read())
        closures = []
        for r in records:
            loc = r.get("location", {})
            lat = loc.get("latitude") or r.get("latitude")
            lon = loc.get("longitude") or r.get("longitude")
            if not lat or not lon:
                continue
            street  = r.get("on_street", "Unknown St")
            from_st = r.get("from_street", "")
            to_st   = r.get("to_street", "")
            label   = f"Road Closure - {street}"
            if from_st and to_st:
                label += f" ({from_st} to {to_st})"
            closures.append({"type": label, "lat": float(lat), "lon": float(lon), "severity": "High"})
        if closures:
            print(f"Loaded {len(closures)} real closures.")
            return closures
        return _fallback_hazards()
    except Exception as e:
        print(f"NYC API unavailable ({e}). Using fallback.")
        return _fallback_hazards()

def _fallback_hazards():
    types = ["Road Closure", "Flooded Road", "Traffic Accident", "Bridge Closure"]
    h = [{"type": random.choice(types), "lat": random.uniform(40.700, 40.878),
           "lon": random.uniform(-74.020, -73.907), "severity": "High"} for _ in range(6)]
    print("Seeded 6 random fallback hazards.")
    return h

# ─── Database ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS hospitals (id INTEGER PRIMARY KEY, name TEXT, lat REAL, lon REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS hazards (id INTEGER PRIMARY KEY, type TEXT, lat REAL, lon REAL, severity TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS incident_log (
                 id INTEGER PRIMARY KEY,
                 timestamp TEXT,
                 patient_label TEXT,
                 patient_lat REAL,
                 patient_lon REAL,
                 patient_address TEXT,
                 hospital_name TEXT,
                 distance_km REAL,
                 road_distance_km REAL,
                 duration_min REAL
               )''')
    if c.execute("SELECT COUNT(*) FROM hospitals").fetchone()[0] == 0:
        c.executemany("INSERT INTO hospitals (name, lat, lon) VALUES (?,?,?)", MANHATTAN_HOSPITALS)
        print(f"Seeded {len(MANHATTAN_HOSPITALS)} Manhattan hospitals.")
    c.execute("DELETE FROM hazards")
    for h in fetch_real_closures():
        c.execute("INSERT INTO hazards (type, lat, lon, severity) VALUES (?,?,?,?)",
                  (h["type"], h["lat"], h["lon"], h["severity"]))
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ─── Haversine ─────────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# ─── Dijkstra ──────────────────────────────────────────────────────────────────
def dijkstra_nearest_er(p_lat, p_lon, hospitals, hazards, hazard_radius_km=0.8):
    heap = []
    visited = set()
    for i, h in enumerate(hospitals):
        dist = haversine(p_lat, p_lon, h["lat"], h["lon"])
        penalty = 0
        for haz in hazards:
            mid_lat = (p_lat + h["lat"]) / 2
            mid_lon = (p_lon + h["lon"]) / 2
            if haversine(mid_lat, mid_lon, haz["lat"], haz["lon"]) < hazard_radius_km:
                penalty += 10
            if haversine(h["lat"], h["lon"], haz["lat"], haz["lon"]) < hazard_radius_km:
                penalty += 999
        heapq.heappush(heap, (dist + penalty, i, dist))
    while heap:
        cost, idx, raw_dist = heapq.heappop(heap)
        if idx in visited:
            continue
        visited.add(idx)
        if cost < 500:
            h = hospitals[idx]
            return {"name": h["name"], "lat": h["lat"], "lon": h["lon"],
                    "path_cost_km": round(raw_dist, 2), "adjusted_cost": round(cost, 2)}
    return None

# ─── Address Geocoding (Nominatim - free, no key needed) ──────────────────────
def geocode_address(address):
    """Convert a Manhattan address string to lat/lon using OpenStreetMap Nominatim."""
    query = urllib.parse.quote(f"{address}, Manhattan, New York City, NY")
    url   = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NYCERRouter/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            results = json.loads(resp.read())
        if results:
            return {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"]),
                    "display": results[0]["display_name"]}
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None

# ─── Turn-by-turn Directions ───────────────────────────────────────────────────
def parse_directions(steps):
    """Parse OSRM steps into simple turn-by-turn instructions."""
    directions = []
    for step in steps:
        maneuver = step.get("maneuver", {})
        mtype    = maneuver.get("type", "")
        modifier = maneuver.get("modifier", "")
        name     = step.get("name", "unnamed road")
        distance = step.get("distance", 0)
        duration = step.get("duration", 0)

        if mtype == "depart":
            instr = f"Start on {name}"
        elif mtype == "arrive":
            instr = "Arrive at destination"
        elif mtype == "turn":
            instr = f"Turn {modifier} onto {name}"
        elif mtype == "new name":
            instr = f"Continue onto {name}"
        elif mtype == "merge":
            instr = f"Merge onto {name}"
        elif mtype == "roundabout":
            instr = f"Enter roundabout, take exit onto {name}"
        else:
            instr = f"Continue on {name}"

        if distance > 0:
            dist_str = f"{distance:.0f}m" if distance < 1000 else f"{distance/1000:.1f}km"
            instr += f" ({dist_str})"

        directions.append({"instruction": instr, "distance_m": distance, "duration_s": duration})
    return directions

# ─── API Routes ────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/status")
def status():
    conn = get_db()
    hcount   = conn.execute("SELECT COUNT(*) FROM hospitals").fetchone()[0]
    hazcount = conn.execute("SELECT COUNT(*) FROM hazards").fetchone()[0]
    logcount = conn.execute("SELECT COUNT(*) FROM incident_log").fetchone()[0]
    conn.close()
    return jsonify({"ready": True, "hospitals_loaded": hcount, "hazards_loaded": hazcount,
                    "incidents_logged": logcount, "engine": "Dijkstra (min-heap)",
                    "data_source": "NYC DOT Open Data (live)"})

@app.route("/api/hospitals")
def get_hospitals():
    conn = get_db()
    rows = conn.execute("SELECT name, lat, lon FROM hospitals").fetchall()
    conn.close()
    return jsonify([{"name": r["name"], "lat": r["lat"], "lon": r["lon"]} for r in rows])

@app.route("/api/hazards")
def get_hazards():
    conn = get_db()
    rows = conn.execute("SELECT type, lat, lon, severity FROM hazards").fetchall()
    conn.close()
    return jsonify([{"type": r["type"], "lat": r["lat"], "lon": r["lon"], "severity": r["severity"]} for r in rows])

@app.route("/api/geocode", methods=["POST"])
def geocode():
    """Convert address to lat/lon."""
    data    = request.get_json()
    address = data.get("address", "")
    if not address:
        return jsonify({"error": "No address provided"})
    result = geocode_address(address)
    if result:
        return jsonify(result)
    return jsonify({"error": "Address not found"})

@app.route("/api/nearest-er", methods=["POST"])
def nearest_er():
    data  = request.get_json()
    p_lat, p_lon = float(data["lat"]), float(data["lon"])
    conn = get_db()
    hospitals = [{"name": r["name"], "lat": r["lat"], "lon": r["lon"]}
                 for r in conn.execute("SELECT name, lat, lon FROM hospitals").fetchall()]
    hazards   = [{"lat": r["lat"], "lon": r["lon"]}
                 for r in conn.execute("SELECT lat, lon FROM hazards").fetchall()]
    conn.close()
    result = dijkstra_nearest_er(p_lat, p_lon, hospitals, hazards)
    return jsonify(result) if result else jsonify({"error": "No safe hospitals found."})

@app.route("/api/route", methods=["POST"])
def get_route():
    data = request.get_json()
    url  = (f"http://router.project-osrm.org/route/v1/driving/"
            f"{data['from_lon']},{data['from_lat']};"
            f"{data['to_lon']},{data['to_lat']}"
            f"?overview=full&geometries=geojson&steps=true")
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            rd = json.loads(resp.read())
        route = rd["routes"][0]
        # Extract steps from all legs for turn-by-turn
        all_steps = []
        for leg in route.get("legs", []):
            all_steps.extend(leg.get("steps", []))
        directions = parse_directions(all_steps)
        return jsonify({
            "geometry":   route["geometry"],
            "distance_m": route["distance"],
            "duration_s": route["duration"],
            "directions": directions
        })
    except Exception:
        return jsonify({
            "geometry": {"type": "LineString", "coordinates": [
                [data["from_lon"], data["from_lat"]],
                [data["to_lon"],   data["to_lat"]]]},
            "distance_m": haversine(data["from_lat"], data["from_lon"],
                                    data["to_lat"],   data["to_lon"]) * 1000,
            "duration_s": 0,
            "directions": [{"instruction": "Proceed directly to hospital", "distance_m": 0, "duration_s": 0}],
            "note": "Straight-line fallback"
        })

@app.route("/api/log-incident", methods=["POST"])
def log_incident():
    """Save a routing event to the incident log."""
    data = request.get_json()
    conn = get_db()
    conn.execute('''INSERT INTO incident_log
                    (timestamp, patient_label, patient_lat, patient_lon, patient_address,
                     hospital_name, distance_km, road_distance_km, duration_min)
                    VALUES (?,?,?,?,?,?,?,?,?)''', (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        data.get("patient_label", "Patient"),
        data.get("patient_lat"),
        data.get("patient_lon"),
        data.get("patient_address", ""),
        data.get("hospital_name"),
        data.get("distance_km"),
        data.get("road_distance_km"),
        data.get("duration_min")
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/incident-log")
def get_incident_log():
    """Return all logged incidents."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM incident_log ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/clear-log", methods=["POST"])
def clear_log():
    conn = get_db()
    conn.execute("DELETE FROM incident_log")
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/refresh-closures", methods=["POST"])
def refresh_closures():
    conn = get_db()
    conn.execute("DELETE FROM hazards")
    count = 0
    for h in fetch_real_closures():
        conn.execute("INSERT INTO hazards (type, lat, lon, severity) VALUES (?,?,?,?)",
                     (h["type"], h["lat"], h["lon"], h["severity"]))
        count += 1
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "closures_loaded": count})

if __name__ == "__main__":
    print("NYC Emergency ER Router starting...")
    init_db()
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
else:
    init_db()
