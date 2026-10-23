"""Tests for routes/services/geocoder.py"""

from unittest.mock import MagicMock, patch

from routes.services.geocoder import (
    _arcgis_geocode,
    _nominatim_geocode,
    batch_geocode_cities,
    geocode_city_state,
    geocode_location,
)


def _arcgis_response(lat, lon):
    return {"candidates": [{"location": {"x": lon, "y": lat}}]}


def _nominatim_response(lat, lon):
    return [{"lat": str(lat), "lon": str(lon)}]


class TestArcgisGeocode:
    @patch("routes.services.geocoder._requests.get")
    def test_returns_lat_lon_tuple(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: _arcgis_response(40.7, -74.0))
        result = _arcgis_geocode("New York, NY, USA")
        assert result == (40.7, -74.0)

    @patch("routes.services.geocoder._requests.get")
    def test_empty_candidates_returns_none(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {"candidates": []})
        result = _arcgis_geocode("Nowhere XYZ")
        assert result is None

    @patch("routes.services.geocoder._requests.get")
    def test_request_exception_returns_none(self, mock_get):
        mock_get.side_effect = Exception("network error")
        result = _arcgis_geocode("New York, NY, USA")
        assert result is None


class TestNominatimGeocode:
    @patch("routes.services.geocoder._requests.get")
    def test_returns_lat_lon_tuple(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: _nominatim_response(40.7, -74.0))
        result = _nominatim_geocode("New York, NY")
        assert result == (40.7, -74.0)

    @patch("routes.services.geocoder._requests.get")
    def test_empty_response_returns_none(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: [])
        result = _nominatim_geocode("Nowhere XYZ")
        assert result is None

    @patch("routes.services.geocoder._requests.get")
    def test_exception_returns_none(self, mock_get):
        mock_get.side_effect = Exception("timeout")
        result = _nominatim_geocode("New York, NY")
        assert result is None


class TestGeocodeLocation:
    @patch("routes.services.geocoder._arcgis_geocode")
    def test_returns_arcgis_result_when_available(self, mock_arcgis):
        mock_arcgis.return_value = (40.7, -74.0)
        # Clear lru_cache before each test
        geocode_location.cache_clear()
        result = geocode_location("New York NY unique_1")
        assert result == (40.7, -74.0)

    @patch("routes.services.geocoder._nominatim_geocode")
    @patch("routes.services.geocoder._arcgis_geocode")
    def test_falls_back_to_nominatim_when_arcgis_fails(self, mock_arcgis, mock_nominatim):
        mock_arcgis.return_value = None
        mock_nominatim.return_value = (40.7, -74.0)
        geocode_location.cache_clear()
        result = geocode_location("New York NY unique_2")
        assert result == (40.7, -74.0)
        mock_nominatim.assert_called_once()

    @patch("routes.services.geocoder._nominatim_geocode")
    @patch("routes.services.geocoder._arcgis_geocode")
    def test_returns_none_when_both_fail(self, mock_arcgis, mock_nominatim):
        mock_arcgis.return_value = None
        mock_nominatim.return_value = None
        geocode_location.cache_clear()
        result = geocode_location("Nonexistent Place unique_3")
        assert result is None


class TestGeocodeCityState:
    @patch("routes.services.geocoder._arcgis_geocode")
    def test_valid_us_state_calls_arcgis(self, mock_arcgis):
        mock_arcgis.return_value = (40.7, -74.0)
        result = geocode_city_state("New York", "NY")
        assert result == (40.7, -74.0)
        mock_arcgis.assert_called_once_with("New York, NY, USA")

    @patch("routes.services.geocoder._arcgis_geocode")
    def test_canadian_province_returns_none(self, mock_arcgis):
        result = geocode_city_state("Toronto", "ON")
        assert result is None
        mock_arcgis.assert_not_called()

    @patch("routes.services.geocoder._arcgis_geocode")
    def test_invalid_state_code_returns_none(self, mock_arcgis):
        result = geocode_city_state("SomeCity", "XX")
        assert result is None
        mock_arcgis.assert_not_called()


class TestBatchGeocodeCities:
    @patch("routes.services.geocoder.geocode_city_state")
    def test_returns_dict_for_all_pairs(self, mock_geocode):
        mock_geocode.return_value = (40.0, -74.0)
        pairs = [("New York", "NY"), ("Chicago", "IL")]
        result = batch_geocode_cities(pairs, max_workers=2)
        assert set(result.keys()) == {("New York", "NY"), ("Chicago", "IL")}

    @patch("routes.services.geocoder.geocode_city_state")
    def test_failed_geocode_stored_as_none(self, mock_geocode):
        mock_geocode.return_value = None
        pairs = [("Nowhere", "XX")]
        result = batch_geocode_cities(pairs, max_workers=1)
        assert result[("Nowhere", "XX")] is None

    @patch("routes.services.geocoder.geocode_city_state")
    def test_progress_callback_called(self, mock_geocode):
        mock_geocode.return_value = (40.0, -74.0)
        calls = []
        batch_geocode_cities(
            [("New York", "NY")],
            max_workers=1,
            progress_callback=lambda done, total: calls.append((done, total)),
        )
        assert len(calls) == 1
        assert calls[0] == (1, 1)

    @patch("routes.services.geocoder.geocode_city_state")
    def test_empty_input_returns_empty_dict(self, mock_geocode):
        result = batch_geocode_cities([], max_workers=1)
        assert result == {}
