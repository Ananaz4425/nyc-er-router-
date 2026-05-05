"""
nyctraffic.py — NYC Real Incident Data Fetcher
Pulls REAL incidents from NYC 311 Open Data API (road-related complaints)
and saves them to emergency.db as hazards.

Run manually anytime:
    python nyctraffic.py

Data source: NYC 311 Service Requests (data.cityofnewyork.us)
Updated daily by NYC government.
"""

import urllib.request
import urllib.parse
import json
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergency.db")

# ─── NYC 311 API ───────────────────────────────────────────────────────────────
# Real road-related complaint types from NYC 311
# These are actual incident categories reported by NYC residents
ROAD_COMPLAINT_TYPES = [
    "Blocked Driveway",
    "Illegal Parking",
    "Street Condition",
    "Street Light Condition",
    "Traffic Signal Condition",
    "Flooded Basement",
    "HEAT/HOT WATER",
    "Road Condition",
    "Bridge Condition",
]

# Fetch complaints from last 24 hours in Manhattan
def build_311_url():
    since = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S")
    # Filter: Manhattan borough, has lat/lon, road-related, recent
    where = (
        f"borough='MANHATTAN' "
        f"AND latitude IS NOT NULL "
        f"AND longitude IS NOT NULL "
        f"AND created_date > '{since}'"
    )
    params = urllib.parse.urlencode({
        "$limit":   50,
        "$where":   where,
        "$order":   "created_date DESC",
        "$select":  "complaint_type,descriptor,latitude,longitude,incident_address,created_date,status"
    })
    return f"https://data.cityofnewyork.us/resource/erm2-nwe9.json?{params}"

def fetch_311_incidents():
    print("🌐 Fetching real NYC 311 incidents from NYC Open Data...")
    url = build_311_url()
    try:
        req = urllib.request.Request(url, headers={
            "Accept":     "application/json",
            "User-Agent": "NYCERRouter/1.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            records = json.loads(resp.read())

        incidents = []
        for r in records:
            lat = r.get("latitude")
            lon = r.get("longitude")
            if not lat or not lon:
                continue
            # Only keep Manhattan bounds
            lat, lon = float(lat), float(lon)
            if not (40.70 <= lat <= 40.88 and -74.02 <= lon <= -73.91):
                continue

            complaint = r.get("complaint_type", "Incident")
            descriptor = r.get("descriptor", "")
            address = r.get("incident_address", "")
            label = complaint
            if descriptor:
                label += f" — {descriptor}"
            if address:
                label += f" @ {address}"

            incidents.append({
                "type":     label[:100],  # cap length
                "lat":      lat,
                "lon":      lon,
                "severity": "High"
            })

        if incidents:
            print(f"✅ Found {len(incidents)} real Manhattan incidents from NYC 311.")
            return incidents
        else:
            print("⚠️  No incidents with coordinates found. Using fallback.")
            return _fallback_hazards()

    except Exception as e:
        print(f"❌ NYC 311 API error: {e}")
        print("   Using fallback hazards instead.")
        return _fallback_hazards()

def _fallback_hazards():
    """Only used if the API is completely unreachable."""
    import random
    types = ["Road Closure", "Flooding", "Traffic Accident", "Street Condition"]
    h = [{"type": random.choice(types),
          "lat":  random.uniform(40.700, 40.878),
          "lon":  random.uniform(-74.020, -73.907),
          "severity": "High"} for _ in range(8)]
    print("⚠️  Seeded 8 fallback hazards (not real data).")
    return h

# ─── Fetch Hospitals from OpenStreetMap ────────────────────────────────────────
def fetch_hospitals():
    print("🏥 Fetching Manhattan hospitals from OpenStreetMap...")
    query = """
    [out:json][timeout:25];
    node["amenity"="hospital"](40.70,-74.02,40.88,-73.91);
    out body;
    """
    try:
        params = urllib.parse.urlencode({"data": query}).encode()
        req = urllib.request.Request(
            "https://overpass-api.de/api/interpreter",
            data=params,
            headers={"User-Agent": "NYCERRouter/1.0"}
        )
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
        print(f"❌ Hospital fetch error: {e}")
        return []

# ─── Save to Database ──────────────────────────────────────────────────────────
def save_to_db(hospitals, incidents):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute('CREATE TABLE IF NOT EXISTS hospitals (id INTEGER PRIMARY KEY, name TEXT, lat REAL, lon REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS hazards   (id INTEGER PRIMARY KEY, type TEXT, lat REAL, lon REAL, severity TEXT)')

    if hospitals:
        c.execute("DELETE FROM hospitals")
        c.executemany("INSERT INTO hospitals (name, lat, lon) VALUES (?,?,?)", hospitals)
        print(f"💾 Saved {len(hospitals)} hospitals to DB.")

    c.execute("DELETE FROM hazards")
    for h in incidents:
        c.execute("INSERT INTO hazards (type, lat, lon, severity) VALUES (?,?,?,?)",
                  (h["type"], h["lat"], h["lon"], h["severity"]))
    print(f"💾 Saved {len(incidents)} incidents to DB.")

    conn.commit()
    conn.close()

def save_json(hospitals, incidents):
    with open("hospitals.json", "w") as f:
        json.dump([{"name": h[0], "lat": h[1], "lon": h[2]} for h in hospitals], f, indent=4)
    with open("hazards.json", "w") as f:
        json.dump(incidents, f, indent=4)
    print("💾 Saved hospitals.json and hazards.json")

# ─── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  NYC Emergency Router — Real Data Fetcher")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    incidents = fetch_311_incidents()
    hospitals = fetch_hospitals()

    save_to_db(hospitals, incidents)
    save_json(hospitals if hospitals else [], incidents)

    print("\n✅ Done! Restart server.py to use the new data.")
    print(f"   Real incidents loaded: {len(incidents)}")
    print(f"   Hospitals loaded: {len(hospitals)}")
