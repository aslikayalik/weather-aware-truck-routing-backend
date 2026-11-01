"""Weather heatmap over the trip corridor for the next 0-48 hours.

The corridor is every grid cell within CORRIDOR_MILES of any route. The grid is
aligned to the weather cache cells and coarsened until it fits MAX_POINTS, so a
1,000-mile trip and a 100-mile trip both produce a similar number of points. All
hours are returned at once so the client-side slider never waits on the network.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from apps.routing import geo
from apps.routing.risk import risk_index
from apps.routing.services.routing import Route
from apps.routing.services.weather import CELL_DEG, HOUR, Cell, HourlyForecast

HEATMAP_HOURS = 48
CORRIDOR_MILES = 40.0
MAX_POINTS = 150
SAMPLE_EVERY_MILES = 5.0


@dataclass(frozen=True)
class Heatmap:
    start: datetime
    step_degrees: float
    cells: list[Cell]
    # One list per cell, one value per hour (HEATMAP_HOURS + 1 values)
    risk: list[list[float]]
    wind_mph: list[list[float]]
    rain_in_hr: list[list[float]]
    snow_in_hr: list[list[float]]


def _cells_within(samples: list[geo.LatLon], step: float) -> set[Cell]:
    lat_radius = CORRIDOR_MILES / geo.MILES_PER_DEG_LAT
    cells: set[Cell] = set()
    for lat, lon in samples:
        lon_radius = lat_radius / max(math.cos(math.radians(lat)), 0.1)
        for i in range(
            math.ceil((lat - lat_radius) / step),
            math.floor((lat + lat_radius) / step) + 1,
        ):
            for j in range(
                math.ceil((lon - lon_radius) / step),
                math.floor((lon + lon_radius) / step) + 1,
            ):
                cell = (round(i * step, 1), round(j * step, 1))
                if (
                    cell not in cells
                    and geo.haversine_miles((lat, lon), cell) <= CORRIDOR_MILES
                ):
                    cells.add(cell)
    return cells


def corridor_cells(routes: list[Route]) -> tuple[list[Cell], float]:
    """Grid cells covering the corridor and the grid spacing in degrees."""
    samples = [
        point
        for route in routes
        for point in geo.points_at_miles(
            route.coords,
            route.cum_miles,
            list(geo.frange(0.0, route.distance_miles, SAMPLE_EVERY_MILES)),
        )
    ]
    # Spacing is a multiple of the weather cell size, so every point is a cache cell.
    multiple = 1
    while True:
        step = round(CELL_DEG * multiple, 1)
        cells = _cells_within(samples, step)
        if len(cells) <= MAX_POINTS:
            return sorted(cells), step
        # Point count scales with 1 / step^2; jump close to the target in one go.
        multiple = max(
            multiple + 1, math.ceil(multiple * math.sqrt(len(cells) / MAX_POINTS))
        )


def current_hour(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def build_heatmap(
    cells: list[Cell],
    step: float,
    forecasts: dict[Cell, HourlyForecast],
    load_lb: float,
    now: datetime,
) -> Heatmap:
    start = current_hour(now)
    risk, wind, rain, snow = [], [], [], []
    for cell in cells:
        forecast = forecasts[cell]
        first = int((start.timestamp() - forecast.start) // HOUR)
        indices = [
            min(max(first + h, 0), forecast.hours - 1) for h in range(HEATMAP_HOURS + 1)
        ]
        cell_wind = [forecast.wind_mph[i] for i in indices]
        cell_rain = [forecast.rain_in_hr[i] for i in indices]
        cell_snow = [forecast.snow_in_hr[i] for i in indices]
        risk.append(
            [
                round(risk_index(w, r, s, load_lb), 2)
                for w, r, s in zip(cell_wind, cell_rain, cell_snow)
            ]
        )
        wind.append([round(w, 1) for w in cell_wind])
        rain.append([round(r, 3) for r in cell_rain])
        snow.append([round(s, 3) for s in cell_snow])
    return Heatmap(
        start=start,
        step_degrees=step,
        cells=cells,
        risk=risk,
        wind_mph=wind,
        rain_in_hr=rain,
        snow_in_hr=snow,
    )
