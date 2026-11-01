"""Hourly forecasts from Open-Meteo, with MET Norway as a fallback.

Every lookup is snapped to a 0.2 degree cell (~14 x 10 miles), close to the
resolution of the global models behind the forecast. Snapping lets the three routes
and the heatmap share cached forecasts, which matters because the free Open-Meteo
API allows 600 locations per minute per IP. Cells are fetched in batches of up to
100 locations.

Open-Meteo counts its quota per IP address, and hosting platforms share outbound
IPs between many customers, so the quota can be exhausted by others. When
Open-Meteo refuses a batch, those cells are fetched from MET Norway instead (one
request per cell) and Open-Meteo is skipped until its quota window resets.
"""

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache

from apps.routing.geo import LatLon
from apps.routing.services.http import default_headers

logger = logging.getLogger(__name__)

CELL_DEG = 0.2
FORECAST_DAYS = 7
BATCH_SIZE = 100
CACHE_TTL_SECONDS = 60 * 60
REQUEST_TIMEOUT_SECONDS = 30
HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
HOUR = 3600

# After a 429, skip Open-Meteo for the rest of its quota window.
OPEN_METEO_BLOCK_KEY = "wx:open-meteo:blocked"
OPEN_METEO_BLOCK_SECONDS = {"minutely": 60, "hourly": 60 * 60, "daily": 60 * 60}

# MET Norway asks clients to stay below 20 requests per second.
MET_WORKERS = 10
MET_TIMEOUT_SECONDS = 15
MPS_TO_MPH = 2.23694
MM_PER_INCH = 25.4
# MET Norway reports precipitation as liquid water and has no separate snowfall
# field; at or below freezing it is treated as snow at a 10:1 snow-to-water ratio.
SNOW_MAX_TEMP_C = 0.5
SNOW_TO_LIQUID_RATIO = 10

Cell = tuple[float, float]


class WeatherError(Exception):
    pass


class WeatherRateLimited(WeatherError):
    """The provider's per-minute/hour location quota is exhausted."""

    def __init__(self, message: str, retry_after_seconds: int = 60):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def snap(point: LatLon) -> Cell:
    lat, lon = point
    return round(round(lat / CELL_DEG) * CELL_DEG, 1), round(
        round(lon / CELL_DEG) * CELL_DEG, 1
    )


@dataclass(frozen=True)
class WeatherSample:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float


@dataclass(frozen=True)
class HourlyForecast:
    """Hourly series starting at `start` (unix seconds, on the hour, UTC)."""

    start: int
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in_hr: list[float]  # rain + showers accumulated over the preceding hour
    snow_in_hr: list[float]  # snowfall accumulated over the preceding hour

    @property
    def hours(self) -> int:
        return len(self.wind_mph)

    def sample(self, at: datetime) -> WeatherSample | None:
        """Conditions at `at`, or None when it falls outside the forecast range.

        Wind is instantaneous, so the nearest hour is used. Precipitation values are
        totals for the hour *ending* at each timestamp, so the hour that contains `at`
        is the next timestamp at or after it.
        """
        offset = (at.timestamp() - self.start) / HOUR
        wind_i = round(offset)
        precip_i = math.ceil(offset)
        if wind_i < 0 or precip_i >= self.hours:
            return None
        return WeatherSample(
            wind_mph=self.wind_mph[wind_i],
            gust_mph=self.gust_mph[wind_i],
            rain_in_hr=self.rain_in_hr[max(precip_i, 0)],
            snow_in_hr=self.snow_in_hr[max(precip_i, 0)],
        )

    def index_of(self, at: datetime) -> int:
        return round((at.timestamp() - self.start) / HOUR)


def _values(hourly: dict, name: str) -> list[float]:
    return [v if v is not None else 0.0 for v in hourly[name]]


def _parse_location(item: dict) -> HourlyForecast:
    hourly = item["hourly"]
    units = item.get("hourly_units", {})
    # With precipitation_unit=inch Open-Meteo reports snowfall in inches; guard anyway.
    snow_factor = 1 / 2.54 if units.get("snowfall") == "cm" else 1.0
    rain = _values(hourly, "rain")
    showers = _values(hourly, "showers")
    return HourlyForecast(
        start=int(hourly["time"][0]),
        wind_mph=_values(hourly, "wind_speed_10m"),
        gust_mph=_values(hourly, "wind_gusts_10m"),
        rain_in_hr=[round(r + s, 3) for r, s in zip(rain, showers)],
        snow_in_hr=[round(v * snow_factor, 3) for v in _values(hourly, "snowfall")],
    )


def _fetch_batch(cells: list[Cell]) -> dict[Cell, HourlyForecast]:
    params = {
        "latitude": ",".join(f"{lat:.1f}" for lat, _ in cells),
        "longitude": ",".join(f"{lon:.1f}" for _, lon in cells),
        "hourly": ",".join(HOURLY_VARIABLES),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timeformat": "unixtime",
        "timezone": "GMT",
        "forecast_days": FORECAST_DAYS,
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    try:
        response = requests.get(
            f"{settings.OPEN_METEO_URL.rstrip('/')}/v1/forecast",
            params=params,
            headers=default_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 429:
            raise _open_meteo_rate_limited(response)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WeatherError(f"Open-Meteo request failed: {exc}") from exc
    items = data if isinstance(data, list) else [data]
    if len(items) != len(cells):
        raise WeatherError(
            f"Open-Meteo returned {len(items)} locations for {len(cells)} requested"
        )
    return {cell: _parse_location(item) for cell, item in zip(cells, items)}


def _open_meteo_rate_limited(response: requests.Response) -> WeatherRateLimited:
    """Build the exception from Open-Meteo's 429 body, which names the exhausted quota."""
    try:
        reason = response.json().get("reason", "")
    except ValueError:
        reason = ""
    window = next(
        (w for w in OPEN_METEO_BLOCK_SECONDS if w in reason.lower()), "minutely"
    )
    return WeatherRateLimited(
        f"Open-Meteo rate limit reached: {reason or 'no reason given'}",
        retry_after_seconds=OPEN_METEO_BLOCK_SECONDS[window],
    )


# --------------------------------------------------------------------- MET Norway


def _interpolate_gaps(values: list[float | None]) -> list[float]:
    """Fill None entries linearly between known values (and flat at the ends)."""
    known = [i for i, v in enumerate(values) if v is not None]
    if not known:
        return [0.0] * len(values)
    filled = list(values)
    for i in range(known[0]):
        filled[i] = values[known[0]]
    for a, b in zip(known, known[1:]):
        for i in range(a + 1, b):
            filled[i] = values[a] + (values[b] - values[a]) * (i - a) / (b - a)
    for i in range(known[-1] + 1, len(values)):
        filled[i] = values[known[-1]]
    return filled


def _parse_met(data: dict) -> HourlyForecast:
    """Convert a MET Norway locationforecast into the hourly Open-Meteo layout.

    MET Norway gives hourly steps for about 2.5 days and 6-hourly steps after that.
    Instant values (wind, temperature) are interpolated between steps. Precipitation
    is given for the period *after* each step, so it is shifted to the hours that end
    within that period and spread evenly over 6-hour periods.
    """
    steps = [
        (
            int(datetime.fromisoformat(s["time"].replace("Z", "+00:00")).timestamp()),
            s["data"],
        )
        for s in data["properties"]["timeseries"]
    ]
    start = steps[0][0]
    hours = (steps[-1][0] - start) // HOUR + 1
    wind: list[float | None] = [None] * hours
    temp: list[float | None] = [None] * hours
    precip_mm = [0.0] * hours  # total for the hour ending at each index

    for n, (ts, step) in enumerate(steps):
        i = (ts - start) // HOUR
        details = step["instant"]["details"]
        wind[i] = details.get("wind_speed", 0.0) * MPS_TO_MPH
        temp[i] = details.get("air_temperature")
        gap = (steps[n + 1][0] - ts) // HOUR if n + 1 < len(steps) else 1
        if gap == 1 and "next_1_hours" in step:
            amounts = [step["next_1_hours"]["details"].get("precipitation_amount", 0.0)]
        elif "next_6_hours" in step:
            total = step["next_6_hours"]["details"].get("precipitation_amount", 0.0)
            amounts = [total / 6] * min(gap, 6)
        elif "next_1_hours" in step:
            amounts = [step["next_1_hours"]["details"].get("precipitation_amount", 0.0)]
        else:
            amounts = []
        for k, amount in enumerate(amounts, start=1):
            if i + k < hours:
                precip_mm[i + k] = amount

    wind_mph = _interpolate_gaps(wind)
    temp_c = _interpolate_gaps(temp)
    rain, snow = [], []
    for mm, celsius in zip(precip_mm, temp_c):
        inches = mm / MM_PER_INCH
        is_snow = celsius <= SNOW_MAX_TEMP_C
        rain.append(0.0 if is_snow else round(inches, 3))
        snow.append(round(inches * SNOW_TO_LIQUID_RATIO, 3) if is_snow else 0.0)
    return HourlyForecast(
        start=start,
        wind_mph=[round(w, 1) for w in wind_mph],
        gust_mph=[round(w, 1) for w in wind_mph],  # no gust data in the compact product
        rain_in_hr=rain,
        snow_in_hr=snow,
    )


def _fetch_met(cell: Cell) -> HourlyForecast:
    url = f"{settings.MET_NORWAY_URL.rstrip('/')}/compact"
    params = {"lat": f"{cell[0]:.1f}", "lon": f"{cell[1]:.1f}"}
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                params=params,
                headers=default_headers(),
                timeout=MET_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise WeatherError(f"MET Norway request failed: {exc}") from exc
        if response.status_code == 429 and attempt == 0:
            time.sleep(1)
            continue
        if response.status_code == 429:
            raise WeatherRateLimited("MET Norway rate limit reached")
        try:
            response.raise_for_status()
            return _parse_met(response.json())
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            raise WeatherError(f"MET Norway response unusable: {exc}") from exc
    raise WeatherError(
        "MET Norway request failed"
    )  # unreachable; keeps type checkers happy


# ------------------------------------------------------------------- orchestration


def _cache_key(cell: Cell) -> str:
    return f"wx:v1:{cell[0]:.1f}:{cell[1]:.1f}"


def _try_open_meteo(batch: list[Cell]) -> dict[Cell, HourlyForecast] | WeatherError:
    try:
        return _fetch_batch(batch)
    except WeatherError as exc:
        return exc


def _fetch(cells: list[Cell]) -> dict[Cell, HourlyForecast]:
    fetched: dict[Cell, HourlyForecast] = {}
    fallback: list[Cell] = cells
    if not cache.get(OPEN_METEO_BLOCK_KEY):
        batches = [cells[i : i + BATCH_SIZE] for i in range(0, len(cells), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(_try_open_meteo, batches))
        fallback = []
        for batch, outcome in zip(batches, outcomes):
            if isinstance(outcome, WeatherError):
                logger.warning(
                    "Open-Meteo failed for %d cells: %s", len(batch), outcome
                )
                if isinstance(outcome, WeatherRateLimited):
                    cache.set(OPEN_METEO_BLOCK_KEY, True, outcome.retry_after_seconds)
                fallback.extend(batch)
            else:
                fetched.update(outcome)
    if fallback:
        logger.info("Fetching %d cells from MET Norway", len(fallback))
        with ThreadPoolExecutor(max_workers=MET_WORKERS) as pool:
            fetched.update(zip(fallback, pool.map(_fetch_met, fallback)))
    return fetched


def get_forecasts(cells: set[Cell]) -> dict[Cell, HourlyForecast]:
    """Forecasts for the given snapped cells, served from cache where possible."""
    keys = {_cache_key(cell): cell for cell in cells}
    cached = cache.get_many(list(keys))
    result: dict[Cell, HourlyForecast] = {
        keys[key]: forecast for key, forecast in cached.items()
    }

    missing = sorted(cells - result.keys())
    if missing:
        fetched = _fetch(missing)
        cache.set_many(
            {_cache_key(cell): forecast for cell, forecast in fetched.items()},
            CACHE_TTL_SECONDS,
        )
        result.update(fetched)
    return result
