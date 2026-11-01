"""Orchestrates one trip plan: routes -> weather -> risk -> recommendation -> heatmap."""

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.routing.geo import LatLon
from apps.routing.heatmap import Heatmap, build_heatmap, corridor_cells
from apps.routing.planner import RoutePlan, build_plans, checkpoint_cells
from apps.routing.services.routing import get_route_options
from apps.routing.services.weather import get_forecasts


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
    routes = get_route_options(origin, destination, load_lb)
    grid, step = corridor_cells(routes)
    # One forecast fetch serves both the checkpoints and the heatmap.
    forecasts = get_forecasts(
        checkpoint_cells(routes, departure, interval_miles) | set(grid)
    )
    return TripPlan(
        routes=build_plans(routes, departure, interval_miles, load_lb, forecasts),
        heatmap=build_heatmap(grid, step, forecasts, load_lb, now),
    )
