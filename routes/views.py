import json
import logging
from functools import lru_cache

from django.http import HttpResponse

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.geocoder import geocode_location
from .services.optimizer import find_stations_near_route, optimize_fuel_stops
from .services.router import get_route

logger = logging.getLogger(__name__)


@lru_cache(maxsize=256)
def _cached_geocode(query: str):
    return geocode_location(query)


@lru_cache(maxsize=64)
def _cached_route(start_lat, start_lon, end_lat, end_lon):
    return get_route(start_lat, start_lon, end_lat, end_lon)


class RouteView(APIView):
    """
    GET /api/route/?start=<location>&finish=<location>

    Returns the optimal fuel stop plan for a US driving route.
    The vehicle is assumed to start with a full 500-mile tank (50 gal at 10 mpg).
    Total fuel cost reflects only fuel purchased at stops along the route.
    """

    def get(self, request):
        start = request.query_params.get("start", "").strip()
        finish = request.query_params.get("finish", "").strip()

        if not start or not finish:
            return Response(
                {"error": "Both 'start' and 'finish' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_coords = _cached_geocode(start)
        if not start_coords:
            return Response(
                {"error": f"Could not geocode start location: '{start}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        finish_coords = _cached_geocode(finish)
        if not finish_coords:
            return Response(
                {"error": f"Could not geocode finish location: '{finish}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            route = _cached_route(
                start_coords[0],
                start_coords[1],
                finish_coords[0],
                finish_coords[1],
            )
        except Exception as exc:
            logger.error("Routing error: %s", exc)
            return Response(
                {"error": f"Routing service error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        total_miles = route["distance_miles"]

        # Expand search radius progressively if needed
        stations_on_route = []
        for deviation in (15.0, 30.0, 50.0):
            stations_on_route = find_stations_near_route(
                route["coords"],
                route["cumulative_distances"],
                max_deviation_miles=deviation,
            )
            if stations_on_route:
                break

        if not stations_on_route:
            return Response(
                {"error": "No fuel stations found along this route."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            stops = optimize_fuel_stops(stations_on_route, total_miles)
        except ValueError as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        total_cost = round(sum(s["stop_cost"] for s in stops), 2)
        total_gallons = round(sum(s["gallons_purchased"] for s in stops), 2)

        return Response(
            {
                "start": start,
                "finish": finish,
                "start_coords": {"lat": start_coords[0], "lon": start_coords[1]},
                "finish_coords": {"lat": finish_coords[0], "lon": finish_coords[1]},
                "total_distance_miles": round(total_miles, 1),
                "total_duration_hours": round(route["duration_seconds"] / 3600, 1),
                "total_fuel_cost_usd": total_cost,
                "total_gallons_purchased": total_gallons,
                "fuel_stop_count": len(stops),
                "note": (
                    "Vehicle starts with a full 500-mile tank (not counted in cost). "
                    "Cost covers only fuel purchased at stops along the route."
                ),
                "route_geometry": route["geometry"],
                "fuel_stops": stops,
                "map_url": request.build_absolute_uri(
                    f"/api/route/map/?start={start}&finish={finish}"
                ),
            }
        )


class MapView(APIView):
    """
    GET /api/route/map/?start=<location>&finish=<location>

    Returns an interactive HTML map by default.
    Add ?format=json to get the same JSON payload as /api/route/.
    """

    def get(self, request):
        start = request.query_params.get("start", "").strip()
        finish = request.query_params.get("finish", "").strip()
        as_json = request.query_params.get("format", "").lower() == "json"

        if not start or not finish:
            if as_json:
                return Response(
                    {
                        "error": "Both 'start' and 'finish' query parameters are required."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return HttpResponse(
                "<p>Usage: /api/route/map/?start=City,State&finish=City,State</p>",
                content_type="text/html",
            )

        start_coords = _cached_geocode(start)
        finish_coords = _cached_geocode(finish)

        if not start_coords or not finish_coords:
            if as_json:
                return Response(
                    {"error": "Could not geocode one or both locations."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return HttpResponse(
                "<p>Could not geocode one or both locations.</p>",
                content_type="text/html",
            )

        try:
            route = _cached_route(
                start_coords[0],
                start_coords[1],
                finish_coords[0],
                finish_coords[1],
            )
        except Exception as exc:
            if as_json:
                return Response(
                    {"error": f"Routing service error: {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return HttpResponse(
                f"<p>Routing error: {exc}</p>", content_type="text/html"
            )

        stations_on_route = []
        for deviation in (15.0, 30.0, 50.0):
            stations_on_route = find_stations_near_route(
                route["coords"],
                route["cumulative_distances"],
                max_deviation_miles=deviation,
            )
            if stations_on_route:
                break

        stops = []
        if stations_on_route:
            try:
                stops = optimize_fuel_stops(stations_on_route, route["distance_miles"])
            except ValueError as exc:
                if as_json:
                    return Response(
                        {"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
                    )

        if as_json:
            total_cost = round(sum(s["stop_cost"] for s in stops), 2)
            total_gallons = round(sum(s["gallons_purchased"] for s in stops), 2)
            return Response(
                {
                    "start": start,
                    "finish": finish,
                    "start_coords": {"lat": start_coords[0], "lon": start_coords[1]},
                    "finish_coords": {"lat": finish_coords[0], "lon": finish_coords[1]},
                    "total_distance_miles": round(route["distance_miles"], 1),
                    "total_duration_hours": round(route["duration_seconds"] / 3600, 1),
                    "total_fuel_cost_usd": total_cost,
                    "total_gallons_purchased": total_gallons,
                    "fuel_stop_count": len(stops),
                    "note": (
                        "Vehicle starts with a full 500-mile tank (not counted in cost). "
                        "Cost covers only fuel purchased at stops along the route."
                    ),
                    "route_geometry": route["geometry"],
                    "fuel_stops": stops,
                    "map_url": request.build_absolute_uri(
                        f"/api/route/map/?start={start}&finish={finish}"
                    ),
                }
            )

        html = _build_map_html(start, finish, route, stops)
        return HttpResponse(html, content_type="text/html")


def _build_map_html(start, finish, route, stops):
    stops_json = json.dumps(stops)
    total_cost = sum(s["stop_cost"] for s in stops)
    total_miles = route["distance_miles"]

    route_latlngs = [[c[1], c[0]] for c in route["geometry"]["coordinates"]]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Fuel Route: {start} to {finish}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
#banner {{
  background: #0f172a; color: #f1f5f9; padding: 10px 18px;
  display: flex; gap: 36px; align-items: center; flex-wrap: wrap;
}}
.s-label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; }}
.s-value {{ font-size: 17px; font-weight: 600; color: #38bdf8; }}
#map {{ height: calc(100vh - 56px); }}
</style>
</head>
<body>
<div id="banner">
  <div><div class="s-label">Route</div><div class="s-value">{start} &rarr; {finish}</div></div>
  <div><div class="s-label">Distance</div><div class="s-value">{total_miles:.0f} mi</div></div>
  <div><div class="s-label">Stops</div><div class="s-value">{len(stops)}</div></div>
  <div><div class="s-label">Fuel Cost</div><div class="s-value">${total_cost:.2f}</div></div>
</div>
<div id="map"></div>
<script>
const stops = {stops_json};
const routeLL = {json.dumps(route_latlngs)};

const map = L.map('map');
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}}).addTo(map);

const poly = L.polyline(routeLL, {{color: '#38bdf8', weight: 4, opacity: 0.85}}).addTo(map);
map.fitBounds(poly.getBounds(), {{padding: [30, 30]}});

const gasIcon = L.divIcon({{
  html: '<div style="background:#f97316;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:15px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4)">&#9981;</div>',
  className: '', iconSize: [28, 28], iconAnchor: [14, 14],
}});

stops.forEach((s, i) => {{
  L.marker([s.latitude, s.longitude], {{icon: gasIcon}})
    .bindPopup(
      `<b>Stop ${{i + 1}}: ${{s.name}}</b><br>` +
      `${{s.city}}, ${{s.state}}<br>` +
      `<b>Price:</b> $${{s.price_per_gallon}}/gal<br>` +
      `<b>Gallons:</b> ${{s.gallons_purchased}}<br>` +
      `<b>Cost:</b> $$${{s.stop_cost}}<br>` +
      `<b>Mile marker:</b> ${{s.miles_from_start}}`
    )
    .addTo(map);
}});
</script>
</body>
</html>"""
