"""
Phase D2: Find nearby hospitals/clinics using OpenStreetMap Nominatim and Overpass.
No API keys. All calls in try/except; returns [] on failure.
- Nominatim: geocode location text to (lat, lon); also fallback text search.
- Overpass: query by (lat, lon) for hospitals/clinics with phone, website when available.
"""
import time
from typing import List, Dict, Any, Optional, Tuple

import requests

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
OVERPASS_BASE = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "HealBee/1.0 (health app; nominatim usage)"}
MIN_REQUEST_INTERVAL = 1.0

# Map symptom/condition (from chat conclusion) to OSM search hints for relevant facilities.
# Used to prefer or filter nearby results (e.g. dermatology for skin issues).
CONDITION_TO_SEARCH_HINTS = {
    "dandruff": ["dermatology", "skin", "clinic", "hospital"],
    "hair fall": ["dermatology", "clinic", "hospital"],
    "pimples and acne": ["dermatology", "skin", "clinic", "hospital"],
    "dry skin": ["dermatology", "clinic", "hospital"],
    "dark spots and pigmentation": ["dermatology", "clinic", "hospital"],
    "skin rash": ["dermatology", "clinic", "hospital"],
    "Alzheimer's disease": ["neurology", "geriatric", "hospital", "clinic"],
    "chest pain": ["hospital", "cardiac", "clinic"],
    "shortness of breath": ["hospital", "clinic"],
    "fever": ["hospital", "clinic"],
    "cough": ["hospital", "clinic"],
    "headache": ["hospital", "clinic"],
    "stomach ache": ["hospital", "clinic"],
    "diarrhea": ["hospital", "clinic"],
    "vomiting": ["hospital", "clinic"],
    "joint pain": ["hospital", "clinic", "orthopaedic"],
    "fatigue": ["hospital", "clinic"],
    "dizziness": ["hospital", "clinic"],
    "eye redness": ["hospital", "clinic", "eye"],
    "dental pain": ["dentist", "dental", "clinic", "hospital"],
}
DEFAULT_SEARCH_HINTS = ["hospital", "clinic"]


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


def _geocode_location(location_text: str) -> Optional[Tuple[float, float]]:
    """
    Geocode location text to (lat, lon) using Nominatim.
    Returns None on failure or if no result.
    """
    if not location_text or not location_text.strip():
        return None
    try:
        time.sleep(MIN_REQUEST_INTERVAL)
        rows = _search(location_text.strip(), limit=1)
        if not rows:
            return None
        r = rows[0]
        lat, lon = r.get("lat"), r.get("lon")
        if lat is None or lon is None:
            return None
        return (float(lat), float(lon))
    except Exception:
        return None


def _overpass_health_near(lat: float, lon: float, radius_m: int = 8000, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Query Overpass for hospitals/clinics/healthcare near (lat, lon).
    Returns list of {name, address, phone, website, lat, lon, type} with contact when available.
    """
    try:
        radius = min(max(500, radius_m), 15000)
        query = f"""
        [out:json][timeout:25];
        (
          node(around:{radius},{lat},{lon})["amenity"~"hospital|clinic|doctors"];
          node(around:{radius},{lat},{lon})["healthcare"];
          way(around:{radius},{lat},{lon})["amenity"~"hospital|clinic|doctors"];
          way(around:{radius},{lat},{lon})["healthcare"];
        );
        out center body;
        """
        r = requests.post(
            OVERPASS_BASE,
            data={"data": query},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        elements = data.get("elements") or []
        seen = set()
        out: List[Dict[str, Any]] = []
        for elem in elements:
            place = _extract_place_from_element(elem)
            if not place or not place.get("name"):
                continue
            key = (place.get("lat"), place.get("lon"), (place.get("name") or "")[:60])
            if key in seen:
                continue
            seen.add(key)
            out.append(place)
        return out[:limit]
    except Exception:
        return []


def search_nearby_health_places(location_text: str, limit_per_type: int = 8) -> List[Dict[str, Any]]:
    """
    Search for hospitals, clinics, and primary health centres near the given location.
    Uses Overpass when possible (after geocoding) to get name, address, phone, website.
    location_text: city name, locality, or area (e.g. "Mumbai", "Velachery", "Connaught Place Delhi").
    Returns list of {"name", "type", "address", "phone", "website", "lat", "lon"}. Empty list on failure.
    """
    if not location_text or not location_text.strip():
        return []
    loc = location_text.strip()
    # 1) Geocode and query Overpass for contact-rich data (phone, website)
    coords = _geocode_location(loc)
    if coords is not None:
        lat, lon = coords
        time.sleep(MIN_REQUEST_INTERVAL)
        overpass_results = _overpass_health_near(lat, lon, radius_m=8000, limit=20)
        if overpass_results:
            return overpass_results
    # 2) Fallback: Nominatim text search (no phone/website from OSM for these)
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
                "phone": "",
                "website": "",
                "lat": lat,
                "lon": lon,
            })
    return out[:30]


def make_osm_link(lat: str, lon: str) -> str:
    """OpenStreetMap link for directions (no Google/Mapbox)."""
    if not lat or not lon:
        return ""
    return f"https://www.openstreetmap.org/directions?from=&to={lat}%2C{lon}"


def _extract_place_from_element(elem: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse one Overpass node/way into {name, address, phone, website, lat, lon, type}."""
    tags = elem.get("tags") or {}
    name = tags.get("name") or tags.get("brand") or ""
    if not name and elem.get("type") == "way":
        name = tags.get("addr:street") or tags.get("addr:full") or "Healthcare facility"
    addr_parts = [
        tags.get("addr:full"),
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:postcode"),
    ]
    address = ", ".join(str(p).strip() for p in addr_parts if p and str(p).strip()) or tags.get("addr:street") or ""
    phone = tags.get("contact:phone") or tags.get("phone") or tags.get("contact:mobile") or ""
    website = tags.get("contact:website") or tags.get("website") or tags.get("contact:url") or ""
    if isinstance(phone, list):
        phone = phone[0] if phone else ""
    if isinstance(website, list):
        website = website[0] if website else ""
    lat, lon = None, None
    if elem.get("type") == "node":
        lat, lon = elem.get("lat"), elem.get("lon")
    elif elem.get("type") == "way" and elem.get("center"):
        lat = elem["center"].get("lat")
        lon = elem["center"].get("lon")
    if lat is None or lon is None:
        return None
    place_type = tags.get("amenity") or tags.get("healthcare") or "healthcare"
    return {
        "name": name.strip() or "Healthcare facility",
        "address": address.strip(),
        "phone": str(phone).strip() if phone else "",
        "website": str(website).strip() if website else "",
        "lat": str(lat),
        "lon": str(lon),
        "type": place_type,
    }


def search_nearby_by_gps(
    lat: float,
    lon: float,
    radius_m: int = 10000,
    condition_hints: Optional[List[str]] = None,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """
    Search for hospitals/clinics near (lat, lon) using Overpass API (within 10 km by default).
    Returns list of {name, address, phone, website, lat, lon, type} (5–6 for UI).
    condition_hints: optional list of keywords (e.g. dermatology, neurology) to rank results.
    """
    try:
        radius = min(max(500, radius_m), 15000)  # default 10 km, max 15 km
        query = f"""
        [out:json][timeout:25];
        (
          node(around:{radius},{lat},{lon})["amenity"~"hospital|clinic|doctors"];
          node(around:{radius},{lat},{lon})["healthcare"];
          way(around:{radius},{lat},{lon})["amenity"~"hospital|clinic|doctors"];
          way(around:{radius},{lat},{lon})["healthcare"];
        );
        out center body;
        """
        r = requests.post(
            OVERPASS_BASE,
            data={"data": query},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        elements = data.get("elements") or []
        seen = set()
        out: List[Dict[str, Any]] = []
        hints = (condition_hints or DEFAULT_SEARCH_HINTS)
        hints_lower = [h.lower() for h in hints]

        def score(place: Dict[str, Any]) -> int:
            name_type = (place.get("name") or "") + " " + (place.get("type") or "")
            n = name_type.lower()
            for i, h in enumerate(hints_lower):
                if h in n:
                    return len(hints_lower) - i
            return 0

        for elem in elements:
            place = _extract_place_from_element(elem)
            if not place or not place.get("name"):
                continue
            key = (place.get("lat"), place.get("lon"), (place.get("name") or "")[:60])
            if key in seen:
                continue
            seen.add(key)
            place["_score"] = score(place)
            out.append(place)

        out.sort(key=lambda p: (-p.pop("_score", 0), p.get("name") or ""))
        return out[:limit]
    except Exception:
        return []


def get_condition_hints_from_symptoms(symptom_names: List[str]) -> List[str]:
    """Map symptom/condition names (from chat conclusion) to search hints for nearby facilities."""
    if not symptom_names:
        return DEFAULT_SEARCH_HINTS
    hints_set = set()
    for s in symptom_names:
        s_clean = (s or "").strip().lower()
        for cond, hints in CONDITION_TO_SEARCH_HINTS.items():
            if cond.lower() == s_clean or cond.lower() in s_clean or s_clean in cond.lower():
                hints_set.update(hints)
                break
    return list(hints_set) if hints_set else DEFAULT_SEARCH_HINTS
