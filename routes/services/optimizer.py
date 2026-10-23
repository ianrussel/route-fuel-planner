import logging
from .router import haversine

logger = logging.getLogger(__name__)

MPG = 10.0
TANK_RANGE_MILES = 500.0


def _point_to_segment(pt_lat, pt_lon, a_lat, a_lon, b_lat, b_lon):
    """
    Closest distance (miles) from point to segment, plus the parameter t in [0,1].
    Uses flat-earth 2D projection in lat/lon space, accurate enough for short segments.
    """
    dlat = b_lat - a_lat
    dlon = b_lon - a_lon
    len_sq = dlat * dlat + dlon * dlon

    if len_sq < 1e-12:
        return 0.0, haversine(pt_lat, pt_lon, a_lat, a_lon)

    t = ((pt_lat - a_lat) * dlat + (pt_lon - a_lon) * dlon) / len_sq
    t = max(0.0, min(1.0, t))

    proj_lat = a_lat + t * dlat
    proj_lon = a_lon + t * dlon
    return t, haversine(pt_lat, pt_lon, proj_lat, proj_lon)


def _station_route_info(station_lat, station_lon, route_coords, cumulative_dists):
    """
    Compute the station's distance along the route and its perpendicular deviation.
    route_coords: [[lon, lat], ...]
    Returns (route_miles_from_start, deviation_miles).
    """
    best_dev = float("inf")
    best_route_dist = 0.0

    for i in range(len(route_coords) - 1):
        lon_a, lat_a = route_coords[i]
        lon_b, lat_b = route_coords[i + 1]

        t, dev = _point_to_segment(station_lat, station_lon, lat_a, lon_a, lat_b, lon_b)

        if dev < best_dev:
            best_dev = dev
            seg_len = cumulative_dists[i + 1] - cumulative_dists[i]
            best_route_dist = cumulative_dists[i] + t * seg_len

    return best_route_dist, best_dev


def find_stations_near_route(
    stations_qs,
    route_coords: list,
    cumulative_dists: list,
    max_deviation_miles: float = 15.0,
) -> list:
    """
    Return stations within max_deviation_miles of the route, sorted by route distance.
    Each item is a dict ready for the optimizer.
    """
    if not route_coords:
        return []

    lats = [c[1] for c in route_coords]
    lons = [c[0] for c in route_coords]
    pad = max_deviation_miles / 55.0  # ~1 degree lat = 69 miles

    candidates = stations_qs.filter(
        latitude__isnull=False,
        latitude__gte=min(lats) - pad,
        latitude__lte=max(lats) + pad,
        longitude__gte=min(lons) - pad,
        longitude__lte=max(lons) + pad,
    )

    # Use a coarser sample of the route for speed; each segment is <=5 miles
    sample_step = max(1, len(route_coords) // 600)
    sc = route_coords[::sample_step]
    sd = cumulative_dists[::sample_step]
    if sc[-1] != route_coords[-1]:
        sc = list(sc) + [route_coords[-1]]
        sd = list(sd) + [cumulative_dists[-1]]

    result = []
    for station in candidates:
        route_dist, deviation = _station_route_info(
            station.latitude, station.longitude, sc, sd
        )
        if deviation <= max_deviation_miles:
            result.append(
                {
                    "id": station.id,
                    "opis_id": station.opis_id,
                    "name": station.name,
                    "address": station.address,
                    "city": station.city,
                    "state": station.state,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "price": station.retail_price,
                    "route_dist": route_dist,
                }
            )

    return sorted(result, key=lambda s: s["route_dist"])


def _compute_fill(station, all_stations, pos, fuel, total_distance_miles, tank_range_miles):
    """Compute how many miles of fuel to buy at this station."""
    dist_to_station = station["route_dist"] - pos
    remaining = fuel - dist_to_station

    ahead = [
        s for s in all_stations
        if station["route_dist"] < s["route_dist"] <= station["route_dist"] + tank_range_miles
    ]

    if ahead:
        next_cheapest = min(ahead, key=lambda s: s["price"])
        if next_cheapest["price"] < station["price"]:
            needed = next_cheapest["route_dist"] - station["route_dist"]
            buffer = min(40.0, (tank_range_miles - needed) * 0.25)
            fill_miles = max(0.0, needed + buffer - remaining)
        else:
            fill_miles = tank_range_miles - remaining
    else:
        dist_to_end = total_distance_miles - station["route_dist"]
        fill_miles = max(0.0, dist_to_end - remaining)

    return min(fill_miles, tank_range_miles - remaining), remaining


def optimize_fuel_stops(
    stations_on_route: list,
    total_distance_miles: float,
    mpg: float = MPG,
    tank_range_miles: float = TANK_RANGE_MILES,
) -> list:
    """
    Greedy look-ahead algorithm to pick cheapest fuel stops.

    - Vehicle starts with a full tank (tank_range_miles of fuel).
    - At each stop, the algorithm decides how much to fill based on whether
      a cheaper station lies ahead within one tank's reach.
    - Skips stations where the fill would be trivially small (<10 gal) if
      additional stations remain reachable without buying there.
    - Returns a list of stop dicts sorted by miles_from_start.
    """
    MIN_FILL_GALLONS = 10.0
    stops = []
    pos = 0.0
    fuel = tank_range_miles

    while pos + fuel < total_distance_miles:
        reachable = [
            s for s in stations_on_route
            if pos < s["route_dist"] <= pos + fuel
        ]

        if not reachable:
            raise ValueError(
                f"No fuel station within {tank_range_miles:.0f} miles of mile marker "
                f"{pos:.0f}. The route may pass through an area with no truck stops."
            )

        best = min(reachable, key=lambda s: s["price"])
        fill_miles, remaining_at_best = _compute_fill(
            best, stations_on_route, pos, fuel, total_distance_miles, tank_range_miles
        )
        gallons = fill_miles / mpg

        # Skip tiny fills if we can still reach another station (or destination) without buying here.
        if gallons < MIN_FILL_GALLONS:
            fuel_after_pass = remaining_at_best
            can_continue = (
                best["route_dist"] + fuel_after_pass >= total_distance_miles
                or any(
                    s["route_dist"] <= best["route_dist"] + fuel_after_pass
                    for s in stations_on_route
                    if s["route_dist"] > best["route_dist"]
                )
            )
            if can_continue:
                pos = best["route_dist"]
                fuel = fuel_after_pass
                continue

        cost = gallons * best["price"]
        stops.append(
            {
                "name": best["name"],
                "address": best["address"],
                "city": best["city"],
                "state": best["state"],
                "latitude": best["latitude"],
                "longitude": best["longitude"],
                "price_per_gallon": round(best["price"], 3),
                "miles_from_start": round(best["route_dist"], 1),
                "gallons_purchased": round(gallons, 2),
                "stop_cost": round(cost, 2),
            }
        )

        pos = best["route_dist"]
        fuel = remaining_at_best + fill_miles

    return stops
