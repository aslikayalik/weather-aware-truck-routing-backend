"""Hourly forecasts from Open-Meteo.

Every lookup is snapped to a 0.2 degree cell (~14 x 10 miles), close to the
resolution of the global models behind the forecast. Snapping lets the three routes
and the heatmap share cached forecasts, which matters because the free API allows
600 locations per minute. Cells are fetched in batches of up to 100 locations.
"""

import logging
import math
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

Cell = tuple[float, float]


class WeatherError(Exception):
    pass


class WeatherRateLimited(WeatherError):
    """The provider's per-minute/hour location quota is exhausted."""


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
            raise WeatherRateLimited("Open-Meteo rate limit reached")
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


def _cache_key(cell: Cell) -> str:
    return f"wx:v1:{cell[0]:.1f}:{cell[1]:.1f}"


def get_forecasts(cells: set[Cell]) -> dict[Cell, HourlyForecast]:
    """Forecasts for the given snapped cells, served from cache where possible."""
    keys = {_cache_key(cell): cell for cell in cells}
    cached = cache.get_many(list(keys))
    result: dict[Cell, HourlyForecast] = {
        keys[key]: forecast for key, forecast in cached.items()
    }

    missing = sorted(cells - result.keys())
    if missing:
        batches = [
            missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            fetched: dict[Cell, HourlyForecast] = {}
            for batch_result in pool.map(_fetch_batch, batches):
                fetched.update(batch_result)
        cache.set_many(
            {_cache_key(cell): forecast for cell, forecast in fetched.items()},
            CACHE_TTL_SECONDS,
        )
        result.update(fetched)
    return result
