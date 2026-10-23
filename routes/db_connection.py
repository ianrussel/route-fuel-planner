import logging

from django.db import connection

from .models import FuelStation

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Central database access layer for the routes app.

    All queries against FuelStation go through this class so the underlying
    engine (SQLite, Postgres, MySQL, ...) can be swapped via DATABASE_URL
    without touching any other part of the codebase.
    """

    def health_check(self) -> dict:
        """Verify the connection is alive and return engine info."""
        cfg = connection.settings_dict
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {
            "status": "ok",
            "engine": cfg["ENGINE"].rsplit(".", 1)[-1],
            "name": str(cfg["NAME"]),
        }

    def get_station_counts(self) -> dict:
        """Return total and geocoded station counts."""
        total = FuelStation.objects.count()
        geocoded = FuelStation.objects.filter(latitude__isnull=False).count()
        return {"total": total, "geocoded": geocoded}

    def get_stations_in_bbox(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
    ):
        """
        Return geocoded stations within a lat/lon bounding box.
        Used as the first-pass filter before the precise proximity check.
        """
        return FuelStation.objects.filter(
            latitude__isnull=False,
            latitude__gte=lat_min,
            latitude__lte=lat_max,
            longitude__gte=lon_min,
            longitude__lte=lon_max,
        )


db = DatabaseManager()
