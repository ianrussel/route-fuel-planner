# Fuel Route Planner API

A Django REST API that calculates the optimal fuel stop plan for a US driving route.
The vehicle has a 500-mile tank range and gets 10 mpg. Fuel prices come from the
bundled CSV dataset. Routing uses the free OSRM demo server; geocoding uses ArcGIS
free endpoint. No API keys required.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py load_fuel_data          # loads and geocodes stations from CSV
python manage.py runserver
```

## Environment Variables
copy `.env.example` to `.env` and edit as needed. The defaults are fine for local development.

### Database
change `DATABASE_URL` to point to your database. The default is a local SQLite file.

### Geocoding
geocoding uses the free ArcGIS endpoint, which has a limit of 1000 requests per day. You can set `GEOCODE_URL` to a different geocoding service if you want.

### API Authentication
Set `API_KEY` in `.env` to protect the API. Every request must then include the header `X-Api-Key: <key>`.

Leave `API_KEY` blank (the default) to disable auth during local development.

## Endpoints

### GET /api/route/

Returns the optimal fuel stop plan as JSON.

**Query parameters**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `start`   | yes      | Starting location (city, state or full address) |
| `finish`  | yes      | Destination location |

**Example**

```bash
# Without auth (API_KEY not set)
curl "http://localhost:8000/api/route/?start=New+York,+NY&finish=Los+Angeles,+CA"

# With auth (API_KEY=mysecret in .env)
curl -H "X-Api-Key: mysecret" \
  "http://localhost:8000/api/route/?start=New+York,+NY&finish=Los+Angeles,+CA"
```

**Response**

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA",
  "start_coords": {"lat": 40.713, "lon": -74.007},
  "finish_coords": {"lat": 34.052, "lon": -118.243},
  "total_distance_miles": 2793.7,
  "total_duration_hours": 49.8,
  "total_fuel_cost_usd": 769.57,
  "total_gallons_purchased": 251.8,
  "fuel_stop_count": 8,
  "note": "Vehicle starts with a full 500-mile tank (not counted in cost). Cost covers only fuel purchased at stops along the route.",
  "route_geometry": {
    "type": "LineString",
    "coordinates": [[-74.007, 40.713], ["...up to ~1000 points"]]
  },
  "fuel_stops": [
    {
      "name": "SHEETZ #639",
      "address": "I-80 EXIT 223",
      "city": "Youngstown",
      "state": "OH",
      "latitude": 41.099,
      "longitude": -80.649,
      "price_per_gallon": 3.059,
      "miles_from_start": 389.4,
      "gallons_purchased": 36.01,
      "stop_cost": 110.16
    }
  ],
  "map_url": "http://localhost:8000/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA"
}
```

More curl examples (add `-H "X-Api-Key: <key>"` to each when `API_KEY` is set):

```bash
# Chicago to Houston
curl "http://localhost:8000/api/route/?start=Chicago,+IL&finish=Houston,+TX"

# Short route (under 500 miles -- no stops needed, cost is $0)
curl "http://localhost:8000/api/route/?start=Atlanta,+GA&finish=Nashville,+TN"

# Full addresses
curl "http://localhost:8000/api/route/?start=350+5th+Ave+New+York+NY&finish=1600+Pennsylvania+Ave+Washington+DC"
```

---

### GET /api/route/map/

Returns an interactive Leaflet map (HTML) showing the route polyline and fuel stop markers.

```bash
# Open in browser (no auth)
curl "http://localhost:8000/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA"

# With auth
curl -H "X-Api-Key: <key>" \
  "http://localhost:8000/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA"
```

Add `&format=json` to get the same JSON payload as `/api/route/` from this endpoint:

```bash
curl -H "X-Api-Key: <key>" \
  "http://localhost:8000/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA&format=json"
```

## Notes

- The vehicle is assumed to start with a full 500-mile tank. That initial fuel is not
  charged; only fuel purchased at stops is counted in `total_fuel_cost_usd`.
- Routes shorter than 500 miles return 0 stops and $0 cost.
- Results are cached in-process; repeated calls with the same start/finish are instant.
- The optimizer uses a greedy look-ahead strategy: it fills up at cheap stations and
  defers buying at expensive ones, stopping only when the fill justifies the detour.
# route-fuel-planner
# route-fuel-planner
