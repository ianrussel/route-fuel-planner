import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

import requests as _requests
from django.conf import settings

logger = logging.getLogger(__name__)

US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
}


def _arcgis_geocode(query: str) -> tuple | None:
    """Single geocode call via ArcGIS free endpoint. Returns (lat, lon) or None."""
    try:
        resp = _requests.get(
            settings.ARCGIS_GEOCODE_URL,
            params={"singleLine": query, "f": "json", "maxLocations": "1", "outFields": "none"},
            timeout=10,
        )
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            loc = candidates[0]["location"]
            return (loc["y"], loc["x"])
    except Exception as exc:
        logger.debug("ArcGIS geocode error for '%s': %s", query, exc)
    return None


def _nominatim_geocode(query: str) -> tuple | None:
    """Geocode via Nominatim (used for user-facing location queries only). Returns (lat, lon) or None."""
    try:
        resp = _requests.get(
            settings.NOMINATIM_URL,
            params={"q": query, "format": "json", "countrycodes": "us", "limit": "1"},
            headers={"User-Agent": "FuelRoutePlanner/1.0 (educational project)"},
            timeout=10,
        )
        data = resp.json()
        if data:
            return (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception as exc:
        logger.warning("Nominatim geocode error for '%s': %s", query, exc)
    return None


@lru_cache(maxsize=512)
def geocode_location(query: str) -> tuple | None:
    """
    Geocode a user-supplied location string.
    Tries ArcGIS first, falls back to Nominatim.
    Returns (lat, lon) or None.
    """
    coords = _arcgis_geocode(f"{query}, USA")
    if coords:
        return coords
    return _nominatim_geocode(query)


def geocode_city_state(city: str, state: str) -> tuple | None:
    """Geocode a city+state pair via ArcGIS. Returns (lat, lon) or None."""
    if state not in US_STATES:
        return None
    return _arcgis_geocode(f"{city}, {state}, USA")


def batch_geocode_cities(
    city_state_pairs: list,
    max_workers: int = 100,
    progress_callback=None,
) -> dict:
    """
    Geocode many (city, state) pairs concurrently via ArcGIS.
    Returns {(city, state): (lat, lon) or None}.
    """
    results = {}
    done = 0
    total = len(city_state_pairs)

    def _geocode(cs):
        city, state = cs
        coords = geocode_city_state(city, state)
        return cs, coords

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_geocode, cs): cs for cs in city_state_pairs}
        for future in as_completed(futures):
            try:
                key, coords = future.result()
                results[key] = coords
            except Exception as exc:
                key = futures[future]
                logger.warning("Geocode worker error for %s: %s", key, exc)
                results[key] = None

            done += 1
            if progress_callback:
                progress_callback(done, total)

    return results
