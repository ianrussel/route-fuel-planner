"""Tests for routes/db_connection.py"""

from django.test import TestCase

from routes.db_connection import DatabaseManager, db
from routes.models import FuelStation


class TestDatabaseManagerHealthCheck(TestCase):
    def test_returns_ok_status(self):
        result = db.health_check()
        assert result["status"] == "ok"

    def test_returns_engine_name(self):
        result = db.health_check()
        assert "engine" in result
        assert result["engine"]  # non-empty

    def test_returns_db_name(self):
        result = db.health_check()
        assert "name" in result
        assert result["name"]  # non-empty

    def test_engine_is_short_name(self):
        # Should be "sqlite3", "postgresql", etc. — not the full dotted path
        result = db.health_check()
        assert "." not in result["engine"]


class TestDatabaseManagerStationCounts(TestCase):
    def test_empty_db_returns_zeros(self):
        result = db.get_station_counts()
        assert result == {"total": 0, "geocoded": 0}

    def test_counts_total_stations(self):
        FuelStation.objects.create(
            opis_id=1,
            name="A",
            address="",
            city="City",
            state="TX",
            retail_price=3.0,
            latitude=None,
            longitude=None,
        )
        result = db.get_station_counts()
        assert result["total"] == 1
        assert result["geocoded"] == 0

    def test_counts_geocoded_stations(self):
        FuelStation.objects.create(
            opis_id=2,
            name="B",
            address="",
            city="City",
            state="TX",
            retail_price=3.0,
            latitude=30.0,
            longitude=-97.0,
        )
        result = db.get_station_counts()
        assert result["geocoded"] == 1

    def test_counts_reflect_mix(self):
        FuelStation.objects.create(
            opis_id=3,
            name="C",
            address="",
            city="City",
            state="TX",
            retail_price=3.0,
            latitude=None,
            longitude=None,
        )
        FuelStation.objects.create(
            opis_id=4,
            name="D",
            address="",
            city="City",
            state="TX",
            retail_price=3.0,
            latitude=30.0,
            longitude=-97.0,
        )
        result = db.get_station_counts()
        assert result["total"] == 2
        assert result["geocoded"] == 1


class TestDatabaseManagerGetStationsInBbox(TestCase):
    def setUp(self):
        self.inside = FuelStation.objects.create(
            opis_id=10,
            name="Inside",
            address="",
            city="Austin",
            state="TX",
            retail_price=3.0,
            latitude=30.0,
            longitude=-97.0,
        )
        self.outside = FuelStation.objects.create(
            opis_id=11,
            name="Outside",
            address="",
            city="Boston",
            state="MA",
            retail_price=3.5,
            latitude=42.0,
            longitude=-71.0,
        )
        self.no_coords = FuelStation.objects.create(
            opis_id=12,
            name="NoCoords",
            address="",
            city="Nowhere",
            state="TX",
            retail_price=3.0,
            latitude=None,
            longitude=None,
        )

    def test_returns_station_inside_bbox(self):
        qs = db.get_stations_in_bbox(29.0, 31.0, -98.0, -96.0)
        names = list(qs.values_list("name", flat=True))
        assert "Inside" in names

    def test_excludes_station_outside_bbox(self):
        qs = db.get_stations_in_bbox(29.0, 31.0, -98.0, -96.0)
        names = list(qs.values_list("name", flat=True))
        assert "Outside" not in names

    def test_excludes_stations_without_coordinates(self):
        qs = db.get_stations_in_bbox(29.0, 31.0, -98.0, -96.0)
        names = list(qs.values_list("name", flat=True))
        assert "NoCoords" not in names

    def test_empty_bbox_returns_empty(self):
        # Tiny bbox in the middle of the ocean
        qs = db.get_stations_in_bbox(0.0, 0.1, 0.0, 0.1)
        assert qs.count() == 0

    def test_db_singleton_is_database_manager_instance(self):
        assert isinstance(db, DatabaseManager)
