"""Tests for routes/services/optimizer.py"""

from unittest.mock import MagicMock, patch

import pytest

from routes.services.optimizer import (
    _compute_fill,
    _point_to_segment,
    _station_route_info,
    find_stations_near_route,
    optimize_fuel_stops,
)


def _make_station(route_dist, price, name="Station"):
    return {
        "id": 1,
        "opis_id": 1,
        "name": name,
        "address": "123 Main St",
        "city": "Testville",
        "state": "TX",
        "latitude": 30.0,
        "longitude": -97.0,
        "price": price,
        "route_dist": route_dist,
    }


class TestPointToSegment:
    def test_point_on_segment_midpoint(self):
        # Point exactly on the midpoint of a horizontal segment
        t, dev = _point_to_segment(0.0, 0.5, 0.0, 0.0, 0.0, 1.0)
        assert abs(t - 0.5) < 0.01
        assert dev < 0.01

    def test_point_at_endpoint_a(self):
        t, dev = _point_to_segment(0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        assert t == 0.0
        assert dev < 0.01

    def test_point_at_endpoint_b(self):
        t, dev = _point_to_segment(0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        assert abs(t - 1.0) < 0.01
        assert dev < 0.01

    def test_point_off_segment_clamps_to_endpoint(self):
        # Point beyond endpoint b — t should clamp to 1.0
        t, dev = _point_to_segment(0.0, 2.0, 0.0, 0.0, 0.0, 1.0)
        assert t == 1.0

    def test_degenerate_segment_returns_distance_to_point(self):
        # Zero-length segment; should return distance to the single point
        t, dev = _point_to_segment(1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert t == 0.0
        assert dev > 0

    def test_perpendicular_deviation_nonzero(self):
        # Point above the midpoint of a horizontal segment
        t, dev = _point_to_segment(1.0, 0.5, 0.0, 0.0, 0.0, 1.0)
        assert dev > 0


class TestStationRouteInfo:
    def test_station_on_route_has_low_deviation(self):
        # Simple two-point route along the equator; station sitting on it
        route = [[-74.0, 40.0], [-76.0, 40.0]]
        cumul = [0.0, 100.0]
        dist, dev = _station_route_info(40.0, -75.0, route, cumul)
        assert dev < 1.0  # less than 1 mile off

    def test_station_far_from_route_has_high_deviation(self):
        route = [[-74.0, 40.0], [-76.0, 40.0]]
        cumul = [0.0, 100.0]
        # Station 5 degrees south
        dist, dev = _station_route_info(35.0, -75.0, route, cumul)
        assert dev > 50  # over 50 miles away

    def test_route_dist_within_bounds(self):
        route = [[-74.0, 40.0], [-76.0, 40.0]]
        cumul = [0.0, 100.0]
        dist, _ = _station_route_info(40.0, -75.0, route, cumul)
        assert 0.0 <= dist <= 100.0


class TestComputeFill:
    def test_fills_to_full_when_nothing_cheaper_ahead(self):
        station = _make_station(100, 3.0)
        ahead = [_make_station(200, 3.5)]
        fill, remaining = _compute_fill(station, [station] + ahead, 0, 500, 1000, 500)
        # Nothing cheaper ahead; should fill to full
        assert fill == 500 - remaining

    def test_fills_just_enough_when_cheaper_ahead(self):
        station = _make_station(100, 3.0)
        cheap = _make_station(300, 2.5)
        fill, remaining = _compute_fill(station, [station, cheap], 0, 500, 1000, 500)
        # Should fill just enough to reach the cheap station, not to full
        assert fill < 500 - remaining

    def test_fill_never_exceeds_tank(self):
        station = _make_station(100, 3.0)
        fill, remaining = _compute_fill(station, [station], 0, 500, 200, 500)
        assert fill <= 500 - remaining

    def test_near_destination_fills_only_what_is_needed(self):
        # Station is 50 miles from the end; remaining fuel is 0
        station = _make_station(150, 3.0)
        fill, remaining = _compute_fill(station, [station], 150, 0, 200, 500)
        # Need 50 miles of fuel to finish
        assert abs(fill - 50) < 1


class TestOptimizeFuelStops:
    def test_no_stops_when_destination_within_range(self):
        stations = [_make_station(100, 3.0)]
        # Destination at 400 miles; full 500-mile tank is enough
        stops = optimize_fuel_stops(stations, 400.0, mpg=10.0, tank_range_miles=500.0)
        assert stops == []

    def test_one_stop_when_route_exceeds_range(self):
        # Route is 800 miles; must stop once
        stations = [_make_station(300, 3.0, "Mid Stop")]
        stops = optimize_fuel_stops(stations, 800.0, mpg=10.0, tank_range_miles=500.0)
        assert len(stops) == 1
        assert stops[0]["name"] == "Mid Stop"

    def test_raises_when_no_station_in_range(self):
        # Only station is beyond tank range
        stations = [_make_station(600, 3.0)]
        with pytest.raises(ValueError, match="No fuel station"):
            optimize_fuel_stops(stations, 1000.0, mpg=10.0, tank_range_miles=500.0)

    def test_picks_cheapest_reachable_station(self):
        # Route 600 miles; both stations reachable on first leg; after stopping
        # at Cheap (250) with a full 500-mile tank we can reach the end (600).
        stations = [
            _make_station(200, 4.0, "Expensive"),
            _make_station(250, 2.5, "Cheap"),
        ]
        stops = optimize_fuel_stops(stations, 600.0, mpg=10.0, tank_range_miles=500.0)
        # Should stop at cheap one first (both in range)
        assert stops[0]["name"] == "Cheap"

    def test_stop_dict_has_required_keys(self):
        stations = [_make_station(300, 3.0)]
        stops = optimize_fuel_stops(stations, 800.0, mpg=10.0, tank_range_miles=500.0)
        required = {
            "name",
            "address",
            "city",
            "state",
            "latitude",
            "longitude",
            "price_per_gallon",
            "miles_from_start",
            "gallons_purchased",
            "stop_cost",
        }
        assert required.issubset(set(stops[0].keys()))

    def test_stop_cost_equals_gallons_times_price(self):
        stations = [_make_station(300, 3.0)]
        stops = optimize_fuel_stops(stations, 800.0, mpg=10.0, tank_range_miles=500.0)
        s = stops[0]
        assert abs(s["stop_cost"] - round(s["gallons_purchased"] * s["price_per_gallon"], 2)) < 0.01

    def test_skips_tiny_fill_when_not_needed(self):
        # Two stations close together; after filling at first the second fill is tiny
        stations = [
            _make_station(400, 2.5, "Cheap"),
            _make_station(420, 2.9, "Tiny Fill"),
        ]
        # Route 900 miles; with a full 500-mile tank, after Cheap at 400 we have
        # 500-(400-0)=100 left. Stop at Cheap, fill to full. Then Tiny Fill is
        # only 20 miles later with ~480 remaining — fill < 10 gal, should be skipped.
        stops = optimize_fuel_stops(stations, 900.0, mpg=10.0, tank_range_miles=500.0)
        names = [s["name"] for s in stops]
        assert "Tiny Fill" not in names

    def test_stops_sorted_by_miles_from_start(self):
        stations = [
            _make_station(400, 3.0, "First"),
            _make_station(800, 3.0, "Second"),
        ]
        stops = optimize_fuel_stops(stations, 1200.0, mpg=10.0, tank_range_miles=500.0)
        dists = [s["miles_from_start"] for s in stops]
        assert dists == sorted(dists)


class TestFindStationsNearRoute:
    def test_empty_route_returns_empty(self):
        result = find_stations_near_route([], [], max_deviation_miles=15.0)
        assert result == []

    @patch("routes.services.optimizer.db")
    def test_stations_within_deviation_included(self, mock_db):
        # Station sitting directly on a straight E-W route
        station = MagicMock()
        station.latitude = 40.0
        station.longitude = -75.0
        station.id = 1
        station.opis_id = 1
        station.name = "On Route"
        station.address = "1 Main"
        station.city = "City"
        station.state = "PA"
        station.retail_price = 3.0
        mock_db.get_stations_in_bbox.return_value = [station]

        route = [[-74.0, 40.0], [-76.0, 40.0]]
        cumul = [0.0, 100.0]
        result = find_stations_near_route(route, cumul, max_deviation_miles=15.0)
        assert len(result) == 1
        assert result[0]["name"] == "On Route"

    @patch("routes.services.optimizer.db")
    def test_stations_outside_deviation_excluded(self, mock_db):
        # Station 5 degrees south (~350 miles off route)
        station = MagicMock()
        station.latitude = 35.0
        station.longitude = -75.0
        station.id = 2
        station.opis_id = 2
        station.name = "Far Away"
        station.address = "2 Main"
        station.city = "South"
        station.state = "NC"
        station.retail_price = 3.0
        mock_db.get_stations_in_bbox.return_value = [station]

        route = [[-74.0, 40.0], [-76.0, 40.0]]
        cumul = [0.0, 100.0]
        result = find_stations_near_route(route, cumul, max_deviation_miles=15.0)
        assert result == []

    @patch("routes.services.optimizer.db")
    def test_result_sorted_by_route_dist(self, mock_db):
        s1 = MagicMock(
            latitude=40.0,
            longitude=-75.0,
            id=1,
            opis_id=1,
            name="B",
            address="",
            city="B",
            state="PA",
            retail_price=3.0,
        )
        s2 = MagicMock(
            latitude=40.0,
            longitude=-74.5,
            id=2,
            opis_id=2,
            name="A",
            address="",
            city="A",
            state="PA",
            retail_price=3.0,
        )
        mock_db.get_stations_in_bbox.return_value = [s1, s2]

        route = [[-74.0, 40.0], [-76.0, 40.0]]
        cumul = [0.0, 100.0]
        result = find_stations_near_route(route, cumul, max_deviation_miles=15.0)
        dists = [r["route_dist"] for r in result]
        assert dists == sorted(dists)
