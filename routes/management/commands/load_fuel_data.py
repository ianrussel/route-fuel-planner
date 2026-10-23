import csv
import logging
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routes.models import FuelStation
from routes.services.geocoder import US_STATES, batch_geocode_cities

logger = logging.getLogger(__name__)

DEFAULT_CSV = Path(__file__).resolve().parents[3] / "fuel-prices-for-be-assessment.csv"


class Command(BaseCommand):
    help = (
        "Load fuel station data from CSV and geocode city locations. "
        "Safe to run multiple times; existing records are updated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            nargs="?",
            default=str(DEFAULT_CSV),
            help="Path to the fuel prices CSV file.",
        )
        parser.add_argument(
            "--no-geocode",
            action="store_true",
            help="Skip geocoding (stations will have no coordinates).",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=5,
            help="Parallel geocoding workers (default: 5).",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        do_geocode = not options["no_geocode"]
        workers = options["workers"]

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV file not found: {csv_path}")

        self.stdout.write(f"Reading {csv_path} ...")
        stations = self._parse_csv(csv_path)
        self.stdout.write(f"  {len(stations)} unique stations parsed.")

        geocode_cache = self._load_existing_geocodes()
        self.stdout.write(f"  {len(geocode_cache)} city/state pairs already geocoded.")

        if do_geocode:
            missing = [
                (city, state)
                for city, state in {(s["city"], s["state"]) for s in stations.values()}
                if (city, state) not in geocode_cache and state in US_STATES
            ]
            if missing:
                self.stdout.write(f"  Geocoding {len(missing)} new city/state pairs ...")
                new_coords = batch_geocode_cities(
                    missing,
                    max_workers=workers,
                    progress_callback=self._progress,
                )
                geocode_cache.update({k: v for k, v in new_coords.items() if v})
                geocoded_count = sum(1 for v in new_coords.values() if v)
                self.stdout.write(f"  Geocoded {geocoded_count}/{len(missing)} successfully.")
            else:
                self.stdout.write("  No new cities to geocode.")

        self.stdout.write("Saving stations to database ...")
        created, updated = self._save_stations(stations, geocode_cache)

        geocoded_total = FuelStation.objects.filter(latitude__isnull=False).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created}, updated: {updated}. "
                f"{geocoded_total}/{len(stations)} stations have coordinates."
            )
        )

    def _parse_csv(self, csv_path):
        stations = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    opis_id = int(row["OPIS Truckstop ID"].strip())
                    city = row["City"].strip()
                    state = row["State"].strip()
                    price = float(row["Retail Price"].strip())
                except (KeyError, ValueError):
                    continue

                key = (opis_id, city, state)
                if key not in stations or price < stations[key]["price"]:
                    stations[key] = {
                        "opis_id": opis_id,
                        "name": row["Truckstop Name"].strip(),
                        "address": row["Address"].strip(),
                        "city": city,
                        "state": state,
                        "price": price,
                    }
        return stations

    def _load_existing_geocodes(self):
        cache = {}
        for fs in FuelStation.objects.filter(latitude__isnull=False).values(
            "city", "state", "latitude", "longitude"
        ):
            cache[(fs["city"], fs["state"])] = (fs["latitude"], fs["longitude"])
        return cache

    def _save_stations(self, stations, geocode_cache):
        created = updated = 0
        with transaction.atomic():
            for key, data in stations.items():
                coords = geocode_cache.get((data["city"], data["state"]))
                lat = coords[0] if coords else None
                lon = coords[1] if coords else None

                _, was_created = FuelStation.objects.update_or_create(
                    opis_id=data["opis_id"],
                    city=data["city"],
                    state=data["state"],
                    defaults={
                        "name": data["name"],
                        "address": data["address"],
                        "retail_price": data["price"],
                        "latitude": lat,
                        "longitude": lon,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        return created, updated

    def _progress(self, done, total):
        if done % 200 == 0 or done == total:
            self.stdout.write(f"    {done}/{total} cities geocoded ...")
