// search.js

let patientMarker = null;

// Main function: search address → place marker → trigger routing
async function searchAddress() {
  const input = document.getElementById("address-input").value.trim();
  if (!input) {
    alert("Please enter an address");
    return;
  }

  try {
    // Call backend geocode API
    const res = await fetch("/api/geocode", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ address: input })
    });

    const data = await res.json();

    if (data.error) {
      alert("Address not found");
      return;
    }

    const lat = data.lat;
    const lng = data.lon;

    // Remove previous patient
    if (patientMarker) {
      map.removeLayer(patientMarker);
    }

    // Add new patient marker
    patientMarker = L.marker([lat, lng], { icon: patientIcon })
      .addTo(map)
      .bindPopup(`<b style="color:#f0b429">Patient</b><br>${data.display_name}`)
      .openPopup();

    // Move map
    map.setView([lat, lng], 15);

    // Trigger your existing routing logic
    routePatient(lat, lng);

  } catch (err) {
    console.error(err);
    alert("Search failed");
  }
}


// 🔹 This reuses your existing routing logic (clean separation)
async function routePatient(lat, lng) {
  const out = document.getElementById('routing-output');
  out.innerHTML = '<p class="computing">⚙ Running Dijkstra…</p>';

  try {
    const er = await fetch(`/api/nearest-er`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ lat, lon: lng })
    }).then(r => r.json());

    if (er.error) {
      out.innerHTML = `<div class="hazard-card">${er.error}</div>`;
      return;
    }

    const route = await fetch(`/api/route`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        from_lat: lat,
        from_lon: lng,
        to_lat: er.lat,
        to_lon: er.lon
      })
    }).then(r => r.json());

    const roadKm = (route.distance_m / 1000).toFixed(2);
    const mins = route.duration_s ? Math.ceil(route.duration_s / 60) : '—';

    out.innerHTML = `
      <div class="result-card">
        <div class="hosp-name">🏥 ${er.name}</div>
        <div class="meta">
          Road dist: <b>${roadKm} km</b><br>
          Est. time: <b>${mins} min</b>
        </div>
      </div>`;

    // Draw route
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.geoJSON(route.geometry, {
      style: { color: '#388bfd', weight: 5, opacity: 0.85 }
    }).addTo(map);

    map.fitBounds(routeLayer.getBounds(), { padding: [60, 60] });

  } catch (err) {
    console.error(err);
    out.innerHTML = '<div class="hazard-card">Routing failed.</div>';
  }
}


// 🔹 Press ENTER to search
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("address-input");
  if (input) {
    input.addEventListener("keypress", function(e) {
      if (e.key === "Enter") {
        searchAddress();
      }
    });
  }
});
