"""Orchestrates one trip plan: routes -> weather -> risk -> recommendation -> heatmap."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.routing.geo import LatLon
from apps.routing.heatmap import Heatmap, build_heatmap, corridor_cells
from apps.routing.planner import RoutePlan, build_plans, checkpoint_cells
from apps.routing.services.routing import get_route_options
from apps.routing.services.weather import get_forecasts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TripPlan:
    routes: list[RoutePlan]
    heatmap: Heatmap

    @property
    def recommended(self) -> RoutePlan:
        return next(plan for plan in self.routes if plan.recommended)


def plan_trip(
    origin: LatLon,
    destination: LatLon,
    departure: datetime,
    load_lb: float,
    interval_miles: float,
    now: datetime | None = None,
) -> TripPlan:
    now = now or timezone.now()
    started = time.monotonic()
    routes = get_route_options(origin, destination, load_lb)
    routed = time.monotonic()
    grid, step = corridor_cells(routes)
    # One forecast fetch serves both the checkpoints and the heatmap.
    cells = checkpoint_cells(routes, departure, interval_miles) | set(grid)
    forecasts = get_forecasts(cells)
    fetched = time.monotonic()
    trip = TripPlan(
        routes=build_plans(routes, departure, interval_miles, load_lb, forecasts),
        heatmap=build_heatmap(grid, step, forecasts, load_lb, now),
    )
    logger.info(
        "Trip planned in %.1fs (routing %.1fs, weather %.1fs for %d cells, %d routes)",
        time.monotonic() - started,
        routed - started,
        fetched - routed,
        len(cells),
        len(routes),
    )
    return trip
