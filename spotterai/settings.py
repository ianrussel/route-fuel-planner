import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-fuel-route-planner-change-in-production")

DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "drf_spectacular",
    "routes",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "spotterai.urls"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "0")),
    )
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "TIMEOUT": 3600,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Routing
OSRM_BASE_URL = os.environ.get(
    "OSRM_BASE_URL",
    "http://router.project-osrm.org/route/v1/driving",
)
ROUTING_TIMEOUT = int(os.environ.get("ROUTING_TIMEOUT", "30"))

# Geocoding
ARCGIS_GEOCODE_URL = os.environ.get(
    "ARCGIS_GEOCODE_URL",
    "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
)
NOMINATIM_URL = os.environ.get(
    "NOMINATIM_URL",
    "https://nominatim.openstreetmap.org/search",
)

# API authentication
API_KEY = os.environ.get("API_KEY", "")

# Vehicle specs
VEHICLE_MPG = float(os.environ.get("VEHICLE_MPG", "10.0"))
VEHICLE_TANK_RANGE_MILES = float(os.environ.get("VEHICLE_TANK_RANGE_MILES", "500.0"))
VEHICLE_MIN_FILL_GALLONS = float(os.environ.get("VEHICLE_MIN_FILL_GALLONS", "10.0"))

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "routes.authentication.ApiKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Fuel Route Planner API",
    "DESCRIPTION": (
        "Given a start and finish location in the US, returns the optimal fuel stop plan "
        "for a truck with a 500-mile tank range and 10 mpg fuel economy. "
        "Fuel prices come from a bundled CSV dataset. Routing uses the free OSRM demo server.\n\n"
        "**Authentication:** Set `API_KEY` in `.env` and pass `X-Api-Key: <key>` on every request. "
        "Leave `API_KEY` blank to disable auth (local dev default)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "routes": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
