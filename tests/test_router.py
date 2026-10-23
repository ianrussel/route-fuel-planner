"""Tests for routes/services/router.py"""

from unittest.mock import MagicMock, patch

import pytest

from routes.services.router import _build_cumulative, _sample_route, get_route, haversine


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine(40.0, -74.0, 40.0, -74.0) == 0.0

    def test_known_distance_ny_to_la(self):
        # Straight-line great-circle NY -> LA is ~2446 miles
        dist = haversine(40.713, -74.007, 34.052, -118.243)
        assert 2400 < dist < 2500

    def test_symmetry(self):
        a = haversine(40.0, -74.0, 34.0, -118.0)
        b = haversine(34.0, -118.0, 40.0, -74.0)
        assert abs(a - b) < 0.001

    def test_short_distance(self):
        # ~69 miles per degree of latitude
        dist = haversine(40.0, -74.0, 41.0, -74.0)
        assert 68 < dist < 70

    def test_returns_positive(self):
        assert haversine(0.0, 0.0, 1.0, 1.0) > 0


class TestBuildCumulative:
    def test_single_coord_returns_zero(self):
        result = _build_cumulative([[-74.0, 40.0]])
        assert result == [0.0]

    def test_first_element_always_zero(self):
        coords = [[-74.0, 40.0], [-75.0, 40.0], [-76.0, 40.0]]
        result = _build_cumulative(coords)
        assert result[0] == 0.0

    def test_length_matches_coords(self):
        coords = [[-74.0, 40.0], [-75.0, 40.0], [-76.0, 40.0]]
        result = _build_cumulative(coords)
        assert len(result) == len(coords)

    def test_monotonically_increasing(self):
        coords = [[-74.0, 40.0], [-75.0, 40.0], [-76.0, 40.0]]
        result = _build_cumulative(coords)
        assert all(result[i] < result[i + 1] for i in range(len(result) - 1))

    def test_two_points_distance(self):
        # Two points 1 degree of longitude apart at equator (~69 miles)
        coords = [[0.0, 0.0], [1.0, 0.0]]
        result = _build_cumulative(coords)
        assert len(result) == 2
        assert result[0] == 0.0
        assert 68 < result[1] < 70


class TestSampleRoute:
    def test_under_limit_returns_unchanged(self):
        coords = [[i * 0.01, 40.0] for i in range(10)]
        cumulative = list(range(10))
        sc, sd = _sample_route(coords, cumulative, max_points=100)
        assert sc == coords
        assert sd == cumulative

    def test_over_limit_reduces_count(self):
        coords = [[i * 0.001, 40.0] for i in range(2000)]
        cumulative = list(range(2000))
        sc, sd = _sample_route(coords, cumulative, max_points=100)
        assert len(sc) <= 110  # allows for fence-post

    def test_first_and_last_preserved(self):
        coords = [[i * 0.001, 40.0] for i in range(2000)]
        cumulative = list(range(2000))
        sc, sd = _sample_route(coords, cumulative, max_points=100)
        assert sc[0] == coords[0]
        assert sc[-1] == coords[-1]

    def test_lengths_match(self):
        coords = [[i * 0.001, 40.0] for i in range(2000)]
        cumulative = list(range(2000))
        sc, sd = _sample_route(coords, cumulative, max_points=100)
        assert len(sc) == len(sd)

    def test_exact_limit_returns_unchanged(self):
        coords = [[i * 0.01, 40.0] for i in range(1000)]
        cumulative = list(range(1000))
        sc, sd = _sample_route(coords, cumulative, max_points=1000)
        assert sc == coords


class TestGetRoute:
    def _osrm_response(self, distance_m=1000.0, duration_s=60.0):
        return {
            "code": "Ok",
            "routes": [
                {
                    "distance": distance_m,
                    "duration": duration_s,
                    "geometry": {
                        "coordinates": [
                            [-74.0, 40.0],
                            [-75.0, 40.5],
                            [-76.0, 41.0],
                        ]
                    },
                }
            ],
        }

    @patch("routes.services.router.requests.get")
    def test_returns_expected_keys(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self._osrm_response())
        result = get_route(40.0, -74.0, 41.0, -76.0)
        assert set(result.keys()) == {
            "geometry",
            "coords",
            "cumulative_distances",
            "distance_miles",
            "duration_seconds",
        }

    @patch("routes.services.router.requests.get")
    def test_distance_conversion(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: self._osrm_response(distance_m=1609.344)
        )
        result = get_route(40.0, -74.0, 41.0, -76.0)
        assert abs(result["distance_miles"] - 1.0) < 0.001

    @patch("routes.services.router.requests.get")
    def test_geometry_is_linestring(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self._osrm_response())
        result = get_route(40.0, -74.0, 41.0, -76.0)
        assert result["geometry"]["type"] == "LineString"

    @patch("routes.services.router.requests.get")
    def test_osrm_error_code_raises(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"code": "InvalidQuery", "routes": []},
        )
        with pytest.raises(ValueError, match="OSRM error"):
            get_route(40.0, -74.0, 41.0, -76.0)

    @patch("routes.services.router.requests.get")
    def test_http_error_raises(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        mock_get.return_value.raise_for_status.side_effect = Exception("HTTP 500")
        with pytest.raises(Exception):
            get_route(40.0, -74.0, 41.0, -76.0)

    @patch("routes.services.router.requests.get")
    def test_cumulative_distances_start_at_zero(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: self._osrm_response())
        result = get_route(40.0, -74.0, 41.0, -76.0)
        assert result["cumulative_distances"][0] == 0.0
