"""Synthetic routes and forecasts so planner tests never touch the network."""

from datetime import datetime, timedelta, timezone

from apps.routing import geo
from apps.routing.services.routing import Route
from apps.routing.services.weather import HourlyForecast, snap

DEPARTURE = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
FORECAST_HOURS = 96


def straight_route(
    miles: float,
    mph: float,
    lat: float = 40.0,
    start_lon: float = -100.0,
    label: str = "Test",
) -> Route:
    """An eastbound route along a parallel, driven at a constant speed."""
    end = geo.destination_point((lat, start_lon), 90, miles)
    steps = max(int(miles), 1)
    coords = [
        (lat + (end[0] - lat) * i / steps, start_lon + (end[1] - start_lon) * i / steps)
        for i in range(steps + 1)
    ]
    cum_miles = geo.cumulative_miles(coords)
    return Route(
        coords=coords,
        cum_miles=cum_miles,
        cum_seconds=[m / mph * 3600 for m in cum_miles],
        label=label,
        provider="test",
    )


def constant_forecasts(
    routes: list[Route], wind_mph: float = 5, rain: float = 0, snow: float = 0
) -> dict:
    start = int((DEPARTURE - timedelta(hours=1)).timestamp())
    forecast = HourlyForecast(
        start=start,
        wind_mph=[wind_mph] * FORECAST_HOURS,
        gust_mph=[wind_mph * 1.5] * FORECAST_HOURS,
        rain_in_hr=[rain] * FORECAST_HOURS,
        snow_in_hr=[snow] * FORECAST_HOURS,
    )
    return {snap(point): forecast for route in routes for point in route.coords}
