"""
nyctraffic.py — NYC Hospital & Hazard Data Fetcher
Run this separately to refresh hospital data from OpenStreetMap:
    python nyctraffic.py

It will update the emergency.db database with real NYC hospital locations.
"""

import urllib.request
import urllib.parse
import json
import sqlite3
import random
import os

# ─── Config ───────────────────────────────────────────────────────────────────
DB_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergency.db")
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Manhattan bounds only
MANHATTAN_BOUNDS = "40.70,-74.02,40.88,-73.91"

# ─── Fetch Real Hospitals from OpenStreetMap ──────────────────────────────────
def fetch_hospitals():
    print("🛰  Fetching Manhattan hospitals from OpenStreetMap...")
    query = f"""
    [out:json][timeout:25];
    node["amenity"="hospital"]({MANHATTAN_BOUNDS});
    out body;
    """
    try:
        params = urllib.parse.urlencode({"data": query}).encode()
        req    = urllib.request.Request(OVERPASS_URL, data=params,
                 headers={"User-Agent": "NYCERRouter/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read()).get("elements", [])

        hospitals = []
        for item in data:
            name = item.get("tags", {}).get("name", "NYC Hospital")
            lat  = item.get("lat")
            lon  = item.get("lon")
            if lat and lon:
                hospitals.append((name, float(lat), float(lon)))

        print(f"✅ Found {len(hospitals)} Manhattan hospitals.")
        return hospitals

    except Exception as e:
        print(f"❌ Error fetching hospitals: {e}")
        return []

# ─── Generate Hazards ─────────────────────────────────────────────────────────
def generate_hazards():
    """Generates random Manhattan hazards as fallback."""
    types = ["Accident", "Flooding", "Road Closure", "Bridge Closure"]
    hazards = []
    for i in range(10):
        hazards.append({
            "type":     random.choice(types),
            "lat":      random.uniform(40.700, 40.878),
            "lon":      random.uniform(-74.020, -73.907),
            "severity": "High"
        })
    print(f"✅ Generated {len(hazards)} hazards.")
    return hazards

# ─── Save to Database ─────────────────────────────────────────────────────────
def save_to_db(hospitals, hazards):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # Make sure tables exist
    c.execute('CREATE TABLE IF NOT EXISTS hospitals (id INTEGER PRIMARY KEY, name TEXT, lat REAL, lon REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS hazards (id INTEGER PRIMARY KEY, type TEXT, lat REAL, lon REAL, severity TEXT)')

    # Replace hospitals
    if hospitals:
        c.execute("DELETE FROM hospitals")
        c.executemany("INSERT INTO hospitals (name, lat, lon) VALUES (?,?,?)", hospitals)
        print(f"💾 Saved {len(hospitals)} hospitals to DB.")

    # Replace hazards
    c.execute("DELETE FROM hazards")
    for h in hazards:
        c.execute("INSERT INTO hazards (type, lat, lon, severity) VALUES (?,?,?,?)",
                  (h["type"], h["lat"], h["lon"], h["severity"]))
    print(f"💾 Saved {len(hazards)} hazards to DB.")

    conn.commit()
    conn.close()

# ─── Also save JSON files for reference ───────────────────────────────────────
def save_json(hospitals, hazards):
    with open("hospitals.json", "w") as f:
        json.dump([{"name": h[0], "lat": h[1], "lon": h[2]} for h in hospitals], f, indent=4)
    with open("hazards.json", "w") as f:
        json.dump(hazards, f, indent=4)
    print("💾 Also saved hospitals.json and hazards.json")

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  NYC Emergency Router — Data Fetcher")
    print("=" * 50)

    hospitals = fetch_hospitals()
    hazards   = generate_hazards()

    if hospitals:
        save_to_db(hospitals, hazards)
        save_json(hospitals, hazards)
        print("\n✅ Done! Restart server.py to use the new data.")
    else:
        print("\n⚠️  No hospitals fetched. Database not changed.")
        print("    Try again in 30 seconds (Overpass API may be busy).")
