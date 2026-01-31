"""
Phase D2: Find nearby hospitals/clinics using OpenStreetMap Nominatim only.
No API keys. All calls in try/except; returns [] on failure.
"""
import time
from typing import List, Dict, Any

import requests

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
# Nominatim usage policy requires a valid User-Agent identifying the application
HEADERS = {"User-Agent": "HealBee/1.0 (health app; nominatim usage)"}
# Be polite: 1 request per second
MIN_REQUEST_INTERVAL = 1.0


def _search(q: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Run a single Nominatim search. Returns [] on error."""
    try:
        r = requests.get(
            f"{NOMINATIM_BASE}/search",
            params={"q": q, "format": "json", "limit": limit},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def search_nearby_health_places(location_text: str, limit_per_type: int = 8) -> List[Dict[str, Any]]:
    """
    Search for hospitals, clinics, and primary health centres near the given location.
    location_text: city name, locality, or area (e.g. "Mumbai", "Connaught Place Delhi").
    Returns list of {"name", "type", "address", "lat", "lon"}. Empty list on failure.
    """
    if not location_text or not location_text.strip():
        return []
    loc = location_text.strip()
    seen = set()
    out: List[Dict[str, Any]] = []

    queries = [
        ("hospital", f"hospital in {loc}"),
        ("clinic", f"clinic in {loc}"),
        ("primary health centre", f"primary health centre in {loc}"),
        ("PHC", f"PHC in {loc}"),
    ]

    for place_type, q in queries:
        time.sleep(MIN_REQUEST_INTERVAL)
        rows = _search(q, limit=limit_per_type)
        for r in rows:
            lat = r.get("lat")
            lon = r.get("lon")
            display_name = r.get("display_name") or ""
            key = (lat, lon, display_name[:80])
            if key in seen:
                continue
            seen.add(key)
            name = r.get("name") or display_name.split(",")[0].strip() or "—"
            out.append({
                "name": name,
                "type": place_type,
                "address": display_name,
                "lat": lat,
                "lon": lon,
            })

    return out[:30]


def make_osm_link(lat: str, lon: str) -> str:
    """OpenStreetMap link for directions (no Google/Mapbox)."""
    if not lat or not lon:
        return ""
    return f"https://www.openstreetmap.org/directions?from=&to={lat}%2C{lon}"
