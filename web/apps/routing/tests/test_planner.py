from datetime import timedelta

import pytest

from apps.routing import geo
from apps.routing.planner import (
    Checkpoint,
    build_plans,
    build_segments,
    checkpoint_miles,
    sample_checkpoints,
    summarize,
)
from apps.routing.risk import RiskAssessment, RiskLevel
from apps.routing.services.routing import Route
from apps.routing.services.weather import HourlyForecast, snap
from apps.routing.tests.factories import DEPARTURE, constant_forecasts, straight_route


def test_checkpoint_miles_include_origin_and_destination():
    assert checkpoint_miles(55, 25) == [0, 25, 50, 55]
    assert checkpoint_miles(50, 25) == [0, 25, 50]
    assert checkpoint_miles(50.02, 25) == [0, 25, 50.02]


def test_checkpoint_eta_follows_route_timing():
    route = straight_route(miles=100, mph=50)
    samples = sample_checkpoints(route, DEPARTURE, 25)
    assert [round(mile) for mile, _, _ in samples] == [0, 25, 50, 75, 100]
    # 50 mph: each 25-mile checkpoint is reached 30 minutes after the previous one
    etas = [eta for _, _, eta in samples]
    assert [round((eta - DEPARTURE).total_seconds() / 60) for eta in etas] == [
        0,
        30,
        60,
        90,
        120,
    ]


def test_forecast_sample_uses_hour_containing_eta_for_precipitation():
    start = int(DEPARTURE.timestamp())
    forecast = HourlyForecast(
        start=start,
        wind_mph=[10, 20, 30],
        gust_mph=[15, 25, 35],
        rain_in_hr=[0.0, 0.2, 0.4],  # totals for the hour ending at each timestamp
        snow_in_hr=[0, 0, 0],
    )
    sample = forecast.sample(DEPARTURE + timedelta(minutes=40))
    assert sample.wind_mph == 20  # nearest hour
    assert sample.rain_in_hr == 0.2  # hour 0:00-1:00 is reported at 1:00
    assert forecast.sample(DEPARTURE + timedelta(hours=3)) is None


def _checkpoint_levels(levels):
    return [
        Checkpoint(
            mile=i * 10.0,
            point=(0.0, 0.0),
            eta=DEPARTURE,
            weather=None,
            risk=(
                None
                if level is None
                else RiskAssessment(level, level, RiskLevel.LOW, RiskLevel.LOW, False)
            ),
        )
        for i, level in enumerate(levels)
    ]


def test_segments_take_the_worse_end_and_summary_weights_by_distance():
    checkpoints = _checkpoint_levels(
        [RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.LOW, RiskLevel.LOW, None]
    )
    segments = build_segments(checkpoints)
    assert [s.level for s in segments] == [
        RiskLevel.HIGH,
        RiskLevel.HIGH,
        RiskLevel.LOW,
        None,
    ]

    summary = summarize(segments)
    assert summary.miles_by_level[RiskLevel.HIGH] == pytest.approx(20)
    assert summary.miles_by_level[RiskLevel.LOW] == pytest.approx(10)
    assert summary.unknown_miles == pytest.approx(10)
    assert summary.average_risk == pytest.approx((2 * 20) / 30)
    assert summary.max_level == RiskLevel.HIGH


def _windy_forecasts(routes: list[Route], windy_route: Route, wind_mph: float) -> dict:
    """Calm everywhere except the cells along `windy_route` (that no other route touches)."""
    forecasts = constant_forecasts(routes, wind_mph=5)
    other_cells = {snap(p) for r in routes if r is not windy_route for p in r.coords}
    windy = constant_forecasts([windy_route], wind_mph=wind_mph)
    forecasts.update({cell: f for cell, f in windy.items() if cell not in other_cells})
    return forecasts


def test_recommendation_prefers_fewer_severe_miles_over_speed():
    fast_but_windy = straight_route(miles=100, mph=60, lat=40.0)
    slow_but_calm = straight_route(miles=110, mph=50, lat=41.0)
    routes = [fast_but_windy, slow_but_calm]
    plans = build_plans(
        routes,
        DEPARTURE,
        10,
        load_lb=20_000,
        forecasts=_windy_forecasts(routes, fast_but_windy, 48),
    )

    windy_plan, calm_plan = plans
    assert windy_plan.summary.miles_by_level[RiskLevel.SEVERE] > 0
    assert calm_plan.recommended and calm_plan.rank == 1
    assert calm_plan.reason.startswith("Tied on No Travel miles. Fewest Severe miles")


def test_load_weight_can_change_the_recommendation():
    windy = straight_route(miles=100, mph=60, lat=40.0)
    calm = straight_route(miles=110, mph=50, lat=41.0)
    routes = [windy, calm]
    forecasts = _windy_forecasts(
        routes, windy, 40
    )  # High for light loads, Severe above 40,000 lb

    light = build_plans(routes, DEPARTURE, 10, load_lb=20_000, forecasts=forecasts)
    heavy = build_plans(routes, DEPARTURE, 10, load_lb=45_000, forecasts=forecasts)
    assert light[0].summary.miles_by_level[RiskLevel.HIGH] > 0
    assert heavy[0].summary.miles_by_level[RiskLevel.SEVERE] > 0
    assert heavy[1].recommended


def test_equal_risk_falls_back_to_travel_time():
    slow = straight_route(miles=100, mph=50, lat=40.0)
    fast = straight_route(miles=100, mph=60, lat=41.0)
    plans = build_plans(
        [slow, fast],
        DEPARTURE,
        25,
        10_000,
        constant_forecasts([slow, fast], wind_mph=5),
    )
    assert plans[1].recommended
    assert "Shortest travel time" in plans[1].reason


def test_route_beyond_forecast_range_reports_unknown_miles():
    route = straight_route(miles=100, mph=50)
    start = int(DEPARTURE.timestamp())
    short = HourlyForecast(
        start=start, wind_mph=[5], gust_mph=[5], rain_in_hr=[0], snow_in_hr=[0]
    )
    forecasts = {
        snap(p): short
        for p in geo.points_at_miles(route.coords, route.cum_miles, list(range(0, 101)))
    }
    (plan,) = build_plans([route], DEPARTURE, 25, 10_000, forecasts)
    assert plan.summary.unknown_miles > 0
    assert plan.checkpoints[-1].risk is None
