
# geocode.py
import urllib.parse
import urllib.request
import json

def geocode_address(address):
    try:
        query = urllib.parse.quote(address)
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NYC-ER-Router/1.0"}
        )

        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())

        if not data:
            return None

        return {
            "lat": float(data[0]["lat"]),
            "lon": float(data[0]["lon"]),
            "display_name": data[0]["display_name"]
        }

    except Exception:
        return None
