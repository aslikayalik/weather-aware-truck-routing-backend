# Weather-Aware Truck Routing — Backend

REST API that helps truck drivers choose the safest route. For a trip it returns three truck
routes, checks the weather each route will meet **at the time the truck reaches each
checkpoint**, rates the risk for the given load weight, and recommends the route that best
balances weather risk and travel time.

The web client lives in the companion `weather-aware-truck-routing-ui` repository.

## Features

- **Three truck route options** per trip. Routing uses a truck profile that takes the vehicle's weight into account.
- **Weather at the truck's ETA.** Checkpoints are placed every 10, 25 or 50 miles. Each one gets the forecast for the hour the truck is expected to arrive there.
- **Load-aware risk rating.** Wind, rain and snow are rated Low → No Travel, and heavy loads raise the wind risk.
- **Explained recommendation.** The response states which criterion decided between the routes.
- **Corridor heatmap.** A weather grid around the routes with hourly values for the next 48 hours.
- **Place search** for the origin and destination inputs.
- JWT authentication with a single active session per user, user and role management, and server/client error logging.

## Tech stack

- Python 3.12, Django 6, Django REST Framework, drf-spectacular (OpenAPI)
- PostgreSQL 17, Redis 7 (cache, sessions, Celery broker), Celery + Flower
- External services, all public with no API key required:
  - [Valhalla](https://valhalla1.openstreetmap.de): truck routing
  - [OSRM](https://project-osrm.org): fallback routing
  - [Open-Meteo](https://open-meteo.com): hourly forecasts
  - [Photon](https://photon.komoot.io): geocoding

## Getting started

### Prerequisites

- Docker and Docker Compose
- Python 3.12, only for running the tests or the server outside Docker

### Run with Docker

Set the database credentials, `REDIS_PASSWORD`, `SECRET_KEY` and `ADMIN_EMAIL` / `ADMIN_PASSWORD`
in `.env`, then start the stack:

```sh
docker compose up -d --build
```

On first start, the one-shot `migrate` service applies migrations and creates a superuser from
`ADMIN_EMAIL` / `ADMIN_PASSWORD`. The other services start once it has finished.

| Service | URL |
|---|---|
| API | `http://localhost:8000/api/v1/` |
| Swagger UI | `http://localhost:8000/api/schema/swagger-ui/` |
| Nginx (UI + API) | `http://localhost:${NGINX_PORT:-8080}` |
| PostgreSQL | `localhost:5450` |

### Production

`docker-compose.prod.yml` runs Django under gunicorn and closes the backend and PostgreSQL ports.
It publishes nginx on `127.0.0.1:8080` only, for a host-level reverse proxy such as Caddy that
terminates HTTPS. Build the web client into `web/static` first; nginx serves it from there.

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

In `.env`, set `DEBUG=false`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to your domain,
`HTTPS_PROXY_HEADER=true` and `FORWARDED_PROTO=https`.

### Deploy to Render

`render.yaml` is a Render Blueprint that creates the API (Docker), PostgreSQL, a Key Value
(Redis) instance and the web client as a static site. In the Render dashboard choose
**New → Blueprint**, select this repository, and enter `ADMIN_EMAIL` / `ADMIN_PASSWORD` when
prompted. The static site proxies `/api` and `/captcha` to the API, so both share one origin.

### Run locally

```sh
cd web
python -m venv ../venv && ../venv/Scripts/activate   # macOS/Linux: source ../venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py initial_data
python manage.py runserver
```

## Configuration

Besides the database, Redis and admin settings in `.env`, the following variables are optional:

| Variable | Default | Description |
|---|---|---|
| `VALHALLA_URL` | `https://valhalla1.openstreetmap.de` | Valhalla instance. A self-hosted instance removes the public server's ~1,500 km limit. |
| `OSRM_URL` | `https://router.project-osrm.org` | Fallback router for long trips. |
| `OPEN_METEO_URL` | `https://api.open-meteo.com` | Use `https://customer-api.open-meteo.com` with a paid plan. |
| `OPEN_METEO_API_KEY` | *(empty)* | Open-Meteo API key for paid plans. |
| `PHOTON_URL` | `https://photon.komoot.io` | Geocoder. |
| `HTTP_USER_AGENT` | `weather-aware-truck-routing/1.0` | Sent to external services, which reject anonymous clients. |
| `TRIP_PLAN_THROTTLE_RATE` | `20/min` | Per-user rate limit for trip planning. |
| `GEOCODE_THROTTLE_RATE` | `60/min` | Per-user rate limit for place search. |

## API

All endpoints require a JWT from `POST /api/v1/auth/token/`. The full schema is available in Swagger UI.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/routing/plan/` | Plan a trip. |
| `GET` | `/api/v1/routing/geocode/?q=Denver` | Search places. |

### Plan a trip

```json
POST /api/v1/routing/plan/
{
  "origin": { "lat": 39.7392, "lon": -104.9903, "label": "Denver, CO" },
  "destination": { "lat": 40.7608, "lon": -111.8910, "label": "Salt Lake City, UT" },
  "departure_time": "2026-11-02T08:00:00-07:00",
  "load_weight_lb": 42000,
  "checkpoint_interval_miles": 25
}
```

| Field | Rules |
|---|---|
| `departure_time` | ISO 8601, from 30 minutes ago up to 4 days ahead, so the whole trip stays within the 7-day forecast |
| `load_weight_lb` | 0 – 80,000 |
| `checkpoint_interval_miles` | 10, 25 or 50 (default 25) |
| `origin`, `destination` | At least 1 mile apart |

The response contains:
- **For each route:**
  - rank, label, distance, duration and arrival time
  - simplified geometry, plus segments coloured by risk
  - every checkpoint with its ETA, weather and per-condition risk level; `load_adjusted` marks a level raised by the load rules
  - a risk summary
- `recommended_route_id` and `recommendation_reason`
- the corridor heatmap

Responses are gzip-compressed and are typically 30–100 KB.

| Status | Meaning |
|---|---|
| `400` | Invalid input |
| `422` | No truck route exists between the points |
| `502` | A routing or weather provider is unavailable |
| `503` | The weather provider's rate limit was reached; retry shortly |

## How it works

The planning pipeline is in `apps/routing/services/trip.py`.

### 1. Routes

`services/routing.py`
- Valhalla's `truck` costing is the primary router. The truck's gross weight (load + 35,000 lb
  tare, capped at 80,000 lb) is passed so weight-restricted roads are avoided.
- The public Valhalla server rejects trips longer than about 1,500 km. Those trips fall back to
  OSRM. OSRM only has a car profile, so every segment is slowed to at most 65 mph.
- When a router returns fewer than three alternatives, the rest are generated by routing through
  a via point offset 15–30 % of the trip length to either side of the fastest route's midpoint.
  A generated route is kept only if it overlaps every existing route by less than 85 % and is
  at most 1.6× slower than the fastest.
- Every route vertex carries a cumulative distance and time. Times come from the router's own
  maneuver and segment durations, so ETAs reflect real road speeds instead of an average speed.

### 2. Checkpoints and weather

`planner.py`, `services/weather.py`
- Checkpoints sit at the origin, every 10 / 25 / 50 miles, and at the destination. Each ETA is
  the departure time plus the interpolated route time at that mile.
- Forecasts are hourly Open-Meteo data in mph and inches:

  | Condition | Open-Meteo field |
  |---|---|
  | Wind | `wind_speed_10m` |
  | Rain | `rain + showers` |
  | Snow | `snowfall` |

- Wind is instantaneous, so the hour nearest the ETA is used. Precipitation is an hourly total
  reported at the end of its hour, so the hour that *contains* the ETA is used.
- Lookups are snapped to 0.2° cells, cached in Redis for an hour, and fetched in batches of
  100 locations. This lets the routes and the heatmap share forecasts.

### 3. Risk model

`risk.py`

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load-weight rules for wind:

| Wind | Load | Result |
|---|---|---|
| ≥ 55 mph | any | No Travel |
| 45–54 mph | > 30,000 lb | No Travel |
| 35–44 mph | > 40,000 lb | Severe |

A checkpoint takes the worst of its three conditions after the load rules are applied. Lower
bounds are inclusive; the No Travel bounds for rain and snow are strict, so exactly 1.00 in/hr
of rain or 3.0 in/hr of snow is Severe.

### 4. Recommendation

`planner.py`
- The stretch between two consecutive checkpoints takes the worse of its two ends, which is the
  conservative choice. From these stretches, each route gets its miles per risk level and a
  distance-weighted average risk, from Low = 0 to No Travel = 4.
- Routes are then ranked by:
  1. fewest No Travel miles
  2. fewest Severe miles
  3. fewest High miles
  4. lowest average risk
  5. shortest travel time
- Values are rounded before comparing, so floating-point noise cannot decide between routes.
- The response names the deciding criterion, for example: *"Tied on No Travel miles. Fewest
  Severe miles (0 mi vs 42 mi on the next best route)."*

### 5. Heatmap

`heatmap.py`
- The corridor is every grid cell within 40 miles of any route. The grid is coarsened until it has
  at most 200 points, so short and coast-to-coast trips cost about the same.
- Each point carries 49 hourly values (now + 0…48 h) for wind, rain, snow and a continuous 0–4
  risk index whose integer part always equals the discrete risk level.
- All hours are returned in one response, so a client can scrub through time without further requests.

## Testing

```sh
cd web
pytest --ds=weather_aware_truck_routing.test_settings
```

The test settings use SQLite and an in-memory cache. External services are mocked, so the suite runs offline in about a second.

| File | Covers |
|---|---|
| `apps/routing/tests/test_risk.py` | Every threshold boundary, the load rules, and the consistency of the heatmap index with the discrete levels |
| `apps/routing/tests/test_planner.py` | Checkpoint placement and ETAs, forecast hour selection, segment and summary maths, recommendation order (including load weight changing the outcome), trips beyond the forecast range |
| `apps/routing/tests/test_api.py` | The plan endpoint end to end with mocked providers, validation and error responses |

## Project structure

```
web/
  apps/
    routing/              trip planning (no database models; computed per request)
      risk.py             risk thresholds, load rules, continuous risk index
      geo.py              distances, polyline decoding, interpolation, simplification
      planner.py          checkpoints, segments, summaries, recommendation
      heatmap.py          corridor grid and 0–48 h values
      services/           routing, weather and geocoding clients; trip orchestration
      api/v1/             request validation, response serialization, views
    authentication/       JWT login, single active session, brute-force lockout
    users/ user_roles/    users, profiles, ranked roles
    user_group/           user groups
    common/               health check, captcha, user settings
    system_logs/          server/client error logs, query statistics
  weather_aware_truck_routing/   settings, URLs, Celery
config/                   nginx and Redis configuration
docker-compose.yml
```

## Known limitations

- **Public service quotas.** The free Open-Meteo API allows 600 locations per minute and 5,000 per
  hour, which is roughly 10–20 new long trips per hour; repeated trips are served from cache.
  Production deployments should use a self-hosted Valhalla and a paid Open-Meteo plan, both
  configurable through environment variables.
- **Drive time only.** ETAs do not include Hours-of-Service breaks or live traffic.
- **Sustained wind.** Risk is based on sustained wind speed. Gusts are returned for information only.
- **OSRM fallback.** Long trips routed by OSRM use the car network with capped speeds and do not
  consider weight restrictions.

## Roadmap

- Hours-of-Service rest stops in the ETA model, so multi-day trips sample the weather the truck will actually meet
- Live traffic in travel times
- Gust-aware wind risk for high-profile empty trailers
