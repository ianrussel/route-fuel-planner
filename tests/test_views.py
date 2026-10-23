"""Tests for routes/views.py — RouteView and MapView"""

from unittest.mock import patch

from django.test import TestCase, override_settings

# Run all view tests with auth disabled so they focus on view logic, not auth.
_no_auth = override_settings(API_KEY="")

MOCK_ROUTE = {
    "geometry": {"type": "LineString", "coordinates": [[-74.0, 40.0], [-75.0, 40.5]]},
    "coords": [[-74.0, 40.0], [-75.0, 40.5]],
    "cumulative_distances": [0.0, 69.0],
    "distance_miles": 69.0,
    "duration_seconds": 3600.0,
}

MOCK_STOPS = [
    {
        "name": "Test Stop",
        "address": "I-80 Exit 1",
        "city": "Testville",
        "state": "PA",
        "latitude": 40.2,
        "longitude": -74.5,
        "price_per_gallon": 3.0,
        "miles_from_start": 30.0,
        "gallons_purchased": 20.0,
        "stop_cost": 60.0,
    }
]


@_no_auth
class TestRouteViewMissingParams(TestCase):
    def test_missing_both_params(self):
        resp = self.client.get("/api/route/")
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_missing_finish_param(self):
        resp = self.client.get("/api/route/?start=New+York,+NY")
        assert resp.status_code == 400

    def test_missing_start_param(self):
        resp = self.client.get("/api/route/?finish=Los+Angeles,+CA")
        assert resp.status_code == 400


@_no_auth
class TestRouteViewBadGeocode(TestCase):
    @patch("routes.views._cached_geocode", return_value=None)
    def test_bad_start_returns_400(self, _):
        resp = self.client.get("/api/route/?start=BADLOC&finish=Los+Angeles,+CA")
        assert resp.status_code == 400
        assert "geocode" in resp.json()["error"].lower()


@_no_auth
class TestRouteViewSuccess(TestCase):
    @patch("routes.views.optimize_fuel_stops", return_value=MOCK_STOPS)
    @patch("routes.views.find_stations_near_route", return_value=[{"route_dist": 30}])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_returns_200(self, *_):
        resp = self.client.get("/api/route/?start=New+York,+NY&finish=Los+Angeles,+CA")
        assert resp.status_code == 200

    @patch("routes.views.optimize_fuel_stops", return_value=MOCK_STOPS)
    @patch("routes.views.find_stations_near_route", return_value=[{"route_dist": 30}])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_response_has_required_keys(self, *_):
        resp = self.client.get("/api/route/?start=New+York,+NY&finish=Los+Angeles,+CA")
        data = resp.json()
        for key in (
            "start",
            "finish",
            "total_distance_miles",
            "total_fuel_cost_usd",
            "fuel_stop_count",
            "fuel_stops",
            "route_geometry",
            "map_url",
        ):
            assert key in data, f"missing key: {key}"

    @patch("routes.views.optimize_fuel_stops", return_value=MOCK_STOPS)
    @patch("routes.views.find_stations_near_route", return_value=[{"route_dist": 30}])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_total_cost_sums_stops(self, *_):
        resp = self.client.get("/api/route/?start=New+York,+NY&finish=Los+Angeles,+CA")
        data = resp.json()
        expected = sum(s["stop_cost"] for s in MOCK_STOPS)
        assert data["total_fuel_cost_usd"] == round(expected, 2)

    @patch("routes.views.find_stations_near_route", return_value=[])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_no_stations_returns_404(self, *_):
        resp = self.client.get("/api/route/?start=New+York,+NY&finish=Los+Angeles,+CA")
        assert resp.status_code == 404

    @patch("routes.views._cached_route", side_effect=Exception("OSRM down"))
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_routing_error_returns_502(self, *_):
        resp = self.client.get("/api/route/?start=New+York,+NY&finish=Los+Angeles,+CA")
        assert resp.status_code == 502


@_no_auth
class TestMapViewHtml(TestCase):
    def test_missing_params_returns_html_hint(self):
        resp = self.client.get("/api/route/map/")
        assert resp.status_code == 200
        assert b"Usage" in resp.content

    @patch("routes.views.optimize_fuel_stops", return_value=MOCK_STOPS)
    @patch("routes.views.find_stations_near_route", return_value=[{"route_dist": 30}])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_returns_html(self, *_):
        resp = self.client.get("/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA")
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" in resp.content

    @patch("routes.views.optimize_fuel_stops", return_value=MOCK_STOPS)
    @patch("routes.views.find_stations_near_route", return_value=[{"route_dist": 30}])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_html_contains_leaflet(self, *_):
        resp = self.client.get("/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA")
        assert b"leaflet" in resp.content.lower()


@_no_auth
class TestMapViewFormatJson(TestCase):
    def test_missing_params_returns_json_error(self):
        resp = self.client.get("/api/route/map/?format=json")
        assert resp.status_code == 400
        assert "error" in resp.json()

    @patch("routes.views.optimize_fuel_stops", return_value=MOCK_STOPS)
    @patch("routes.views.find_stations_near_route", return_value=[{"route_dist": 30}])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_format_json_returns_json(self, *_):
        resp = self.client.get(
            "/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA&format=json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "fuel_stops" in data
        assert "route_geometry" in data

    @patch("routes.views.optimize_fuel_stops", return_value=MOCK_STOPS)
    @patch("routes.views.find_stations_near_route", return_value=[{"route_dist": 30}])
    @patch("routes.views._cached_route", return_value=MOCK_ROUTE)
    @patch("routes.views._cached_geocode", side_effect=[(40.7, -74.0), (34.0, -118.0)])
    def test_format_json_includes_map_url(self, *_):
        resp = self.client.get(
            "/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA&format=json"
        )
        data = resp.json()
        assert "map_url" in data
        assert "format=json" not in data["map_url"]
