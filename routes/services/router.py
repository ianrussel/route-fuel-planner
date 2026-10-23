import logging
from math import asin, cos, radians, sin, sqrt

from django.conf import settings

import requests

logger = logging.getLogger(__name__)

EARTH_RADIUS_MILES = 3958.8


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in miles between two GPS coordinates."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(max(0.0, a)))


def get_route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    timeout: int = 30,
) -> dict:
    """
    Fetch a driving route from OSRM.

    Returns a dict with:
      geometry      - GeoJSON LineString (sampled, max ~1000 pts for response)
      coords        - full [[lon, lat], ...] list
      cumulative_distances - miles from start for each coord
      distance_miles
      duration_seconds
    """
    url = f"{settings.OSRM_BASE_URL}/{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
        "annotations": "false",
    }

    resp = requests.get(url, params=params, timeout=timeout or settings.ROUTING_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"OSRM error: {data.get('code', 'unknown')}")

    route = data["routes"][0]
    coords = route["geometry"]["coordinates"]  # [[lon, lat], ...]

    cumulative = _build_cumulative(coords)

    sampled_coords, sampled_dists = _sample_route(coords, cumulative, max_points=1000)

    return {
        "geometry": {
            "type": "LineString",
            "coordinates": sampled_coords,
        },
        "coords": coords,
        "cumulative_distances": cumulative,
        "distance_miles": route["distance"] / 1609.344,
        "duration_seconds": route["duration"],
    }


def _build_cumulative(coords: list) -> list:
    cumulative = [0.0]
    for i in range(1, len(coords)):
        prev_lon, prev_lat = coords[i - 1]
        cur_lon, cur_lat = coords[i]
        d = haversine(prev_lat, prev_lon, cur_lat, cur_lon)
        cumulative.append(cumulative[-1] + d)
    return cumulative


def _sample_route(coords: list, cumulative: list, max_points: int) -> tuple:
    n = len(coords)
    if n <= max_points:
        return coords, cumulative

    step = n // max_points
    indices = list(range(0, n, step))
    if indices[-1] != n - 1:
        indices.append(n - 1)

    return (
        [coords[i] for i in indices],
        [cumulative[i] for i in indices],
    )
