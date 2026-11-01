"""Checkpoint sampling, per-route risk summaries and the route recommendation."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from apps.routing import geo
from apps.routing.geo import LatLon
from apps.routing.risk import RiskAssessment, RiskLevel, assess
from apps.routing.services.routing import Route
from apps.routing.services.weather import HourlyForecast, WeatherSample, snap

CHECKPOINT_INTERVALS_MILES = (10, 25, 50)
# Output geometry tolerance (~100 m); plenty for drawing at any useful zoom.
DISPLAY_TOLERANCE_DEG = 0.001


@dataclass(frozen=True)
class Checkpoint:
    mile: float
    point: LatLon
    eta: datetime
    weather: WeatherSample | None
    risk: RiskAssessment | None  # None when the ETA is beyond the forecast range


@dataclass(frozen=True)
class Segment:
    """Stretch between two consecutive checkpoints, rated by the worse of its ends."""

    from_mile: float
    to_mile: float
    level: RiskLevel | None

    @property
    def miles(self) -> float:
        return self.to_mile - self.from_mile


@dataclass(frozen=True)
class RiskSummary:
    miles_by_level: dict[RiskLevel, float]
    unknown_miles: float
    average_risk: float  # distance-weighted mean of segment levels (0-4)
    max_level: RiskLevel | None

    def sort_key(self, duration_seconds: float) -> tuple:
        """Recommendation order: No Travel, Severe and High miles, average risk, time.

        No Travel miles are strictly worse than Severe ones, so they are compared
        before anything else. Values are rounded so floating-point noise cannot decide
        between otherwise equal routes.
        """
        return (
            round(self.miles_by_level[RiskLevel.NO_TRAVEL], 1),
            round(self.miles_by_level[RiskLevel.SEVERE], 1),
            round(self.miles_by_level[RiskLevel.HIGH], 1),
            round(self.average_risk, 2),
            round(duration_seconds),
        )


@dataclass
class RoutePlan:
    id: int
    route: Route
    departure: datetime
    checkpoints: list[Checkpoint]
    segments: list[Segment]
    summary: RiskSummary
    rank: int = 0
    recommended: bool = False
    reason: str = ""
    display_indices: list[int] = field(default_factory=list)

    @property
    def arrival(self) -> datetime:
        return self.departure + timedelta(seconds=self.route.duration_seconds)


def checkpoint_miles(distance_miles: float, interval_miles: float) -> list[float]:
    """Origin, every `interval_miles`, and the destination."""
    miles = list(geo.frange(0.0, distance_miles, interval_miles))
    if distance_miles - miles[-1] > 0.05:
        miles.append(distance_miles)
    else:
        miles[-1] = distance_miles
    return miles


def sample_checkpoints(
    route: Route, departure: datetime, interval_miles: float
) -> list[tuple[float, LatLon, datetime]]:
    miles = checkpoint_miles(route.distance_miles, interval_miles)
    points = geo.points_at_miles(route.coords, route.cum_miles, miles)
    return [
        (mile, point, departure + timedelta(seconds=route.seconds_at_mile(mile)))
        for mile, point in zip(miles, points)
    ]


def assess_checkpoints(
    samples: list[tuple[float, LatLon, datetime]],
    forecasts: dict[tuple[float, float], HourlyForecast],
    load_lb: float,
) -> list[Checkpoint]:
    checkpoints = []
    for mile, point, eta in samples:
        forecast = forecasts.get(snap(point))
        weather = forecast.sample(eta) if forecast else None
        risk = (
            assess(weather.wind_mph, weather.rain_in_hr, weather.snow_in_hr, load_lb)
            if weather
            else None
        )
        checkpoints.append(
            Checkpoint(mile=mile, point=point, eta=eta, weather=weather, risk=risk)
        )
    return checkpoints


def build_segments(checkpoints: list[Checkpoint]) -> list[Segment]:
    segments = []
    for start, end in zip(checkpoints, checkpoints[1:]):
        levels = [cp.risk.level for cp in (start, end) if cp.risk]
        segments.append(
            Segment(start.mile, end.mile, max(levels) if len(levels) == 2 else None)
        )
    return segments


def summarize(segments: list[Segment]) -> RiskSummary:
    miles_by_level = dict.fromkeys(RiskLevel, 0.0)
    unknown = 0.0
    weighted = 0.0
    for segment in segments:
        if segment.level is None:
            unknown += segment.miles
            continue
        miles_by_level[segment.level] += segment.miles
        weighted += segment.level * segment.miles
    known = sum(miles_by_level.values())
    rated = [s.level for s in segments if s.level is not None]
    return RiskSummary(
        miles_by_level=miles_by_level,
        unknown_miles=unknown,
        average_risk=weighted / known if known else 0.0,
        max_level=max(rated) if rated else None,
    )


_MILES = "{:.0f} mi"

# Same order as RiskSummary.sort_key: (criterion, phrase, value getter, format).
_CRITERIA = (
    (
        "No Travel miles",
        "Fewest No Travel miles",
        lambda p: p.summary.miles_by_level[RiskLevel.NO_TRAVEL],
        _MILES,
    ),
    (
        "Severe miles",
        "Fewest Severe miles",
        lambda p: p.summary.miles_by_level[RiskLevel.SEVERE],
        _MILES,
    ),
    (
        "High miles",
        "Fewest High miles",
        lambda p: p.summary.miles_by_level[RiskLevel.HIGH],
        _MILES,
    ),
    ("average risk", "Lowest average risk", lambda p: p.summary.average_risk, "{:.2f}"),
    (
        "travel time",
        "Shortest travel time",
        lambda p: p.route.duration_seconds / 3600,
        "{:.1f} h",
    ),
)


def _reason(best: RoutePlan, runner_up: RoutePlan | None) -> str:
    if runner_up is None:
        return "Only route available."
    best_key = best.summary.sort_key(best.route.duration_seconds)
    other_key = runner_up.summary.sort_key(runner_up.route.duration_seconds)
    for i, (_, phrase, value, fmt) in enumerate(_CRITERIA):
        if best_key[i] != other_key[i]:
            tied = ", ".join(c[0] for c in _CRITERIA[:i])
            prefix = f"Tied on {tied}. " if tied else ""
            return f"{prefix}{phrase} ({fmt.format(value(best))} vs {fmt.format(value(runner_up))} on the next best route)."
    return "Identical risk and travel time to the next best route."


def rank_routes(plans: list[RoutePlan]) -> list[RoutePlan]:
    """Mark ranks, the recommended route and a human-readable reason (in place)."""
    ordered = sorted(plans, key=lambda p: p.summary.sort_key(p.route.duration_seconds))
    for rank, plan in enumerate(ordered, start=1):
        plan.rank = rank
        plan.recommended = rank == 1
    if ordered:
        ordered[0].reason = _reason(
            ordered[0], ordered[1] if len(ordered) > 1 else None
        )
    return plans


def build_plans(
    routes: list[Route],
    departure: datetime,
    interval_miles: float,
    load_lb: float,
    forecasts: dict[tuple[float, float], HourlyForecast],
) -> list[RoutePlan]:
    plans = []
    for i, route in enumerate(routes):
        checkpoints = assess_checkpoints(
            sample_checkpoints(route, departure, interval_miles), forecasts, load_lb
        )
        segments = build_segments(checkpoints)
        plans.append(
            RoutePlan(
                id=i,
                route=route,
                departure=departure,
                checkpoints=checkpoints,
                segments=segments,
                summary=summarize(segments),
                display_indices=geo.simplify_indices(
                    route.coords, DISPLAY_TOLERANCE_DEG
                ),
            )
        )
    return rank_routes(plans)


def checkpoint_cells(
    routes: list[Route], departure: datetime, interval_miles: float
) -> set[tuple[float, float]]:
    return {
        snap(point)
        for route in routes
        for _, point, _ in sample_checkpoints(route, departure, interval_miles)
    }
