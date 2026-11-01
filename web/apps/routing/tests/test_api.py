from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.routing.services.routing import NoRouteFound
from apps.routing.services.weather import HourlyForecast, WeatherRateLimited
from apps.routing.tests.factories import straight_route

pytestmark = pytest.mark.django_db

URL = "/api/v1/routing/plan/"


def _payload(**overrides):
    payload = {
        "origin": {"lat": 40.0, "lon": -100.0, "label": "A"},
        "destination": {"lat": 40.0, "lon": -98.0, "label": "B"},
        "departure_time": (timezone.now() + timedelta(hours=1)).isoformat(),
        "load_weight_lb": 35_000,
        "checkpoint_interval_miles": 25,
    }
    payload.update(overrides)
    return payload


def _fake_forecasts(cells):
    start = int(timezone.now().replace(minute=0, second=0, microsecond=0).timestamp())
    forecast = HourlyForecast(
        start=start,
        wind_mph=[38] * 120,
        gust_mph=[50] * 120,
        rain_in_hr=[0] * 120,
        snow_in_hr=[0] * 120,
    )
    return dict.fromkeys(cells, forecast)


@pytest.fixture
def fake_providers():
    routes = [
        straight_route(100, 60, lat=40.0, label="via A"),
        straight_route(110, 55, lat=40.6, label="via B"),
        straight_route(120, 50, lat=41.2, label="via C"),
    ]
    with (
        patch("apps.routing.services.trip.get_route_options", return_value=routes),
        patch("apps.routing.services.trip.get_forecasts", side_effect=_fake_forecasts),
    ):
        yield routes


def test_plan_requires_authentication(api_client_unauthorized):
    assert (
        api_client_unauthorized.post(URL, _payload(), format="json").status_code == 401
    )


def test_plan_returns_three_ranked_routes_with_checkpoints_and_heatmap(
    api_client_user, fake_providers
):
    response = api_client_user.post(URL, _payload(), format="json")
    assert response.status_code == 200, response.content
    body = response.json()

    assert len(body["routes"]) == 3
    assert sorted(r["rank"] for r in body["routes"]) == [1, 2, 3]
    assert sum(r["recommended"] for r in body["routes"]) == 1
    # Uniformly High weather -> the shortest route has the fewest High miles
    assert body["recommended_route_id"] == 0
    assert "Fewest High miles (100 mi vs 110 mi" in body["recommendation_reason"]

    route = body["routes"][0]
    assert [cp["mile"] for cp in route["checkpoints"]] == [0, 25, 50, 75, 100]
    # 38 mph with a 35,000 lb load is High (Severe only above 40,000 lb)
    assert route["checkpoints"][1]["risk"]["level"] == "high"
    assert route["summary"]["miles_by_level"]["high"] == pytest.approx(100, abs=0.2)
    assert len(route["segments"]) == 4

    heatmap = body["heatmap"]
    assert heatmap["hours"] == 48
    assert len(heatmap["points"]) == len(heatmap["risk"]) > 0
    assert all(len(values) == 49 for values in heatmap["risk"])


def test_heavier_load_raises_wind_risk(api_client_user, fake_providers):
    body = api_client_user.post(
        URL, _payload(load_weight_lb=42_000), format="json"
    ).json()
    assert body["routes"][0]["checkpoints"][1]["risk"]["level"] == "severe"
    assert body["routes"][0]["checkpoints"][1]["risk"]["load_adjusted"] is True


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"load_weight_lb": -1}, "load_weight_lb"),
        ({"load_weight_lb": 90_000}, "load_weight_lb"),
        ({"checkpoint_interval_miles": 15}, "checkpoint_interval_miles"),
        ({"departure_time": "2020-01-01T00:00:00Z"}, "departure_time"),
        ({"destination": {"lat": 40.0, "lon": -100.0}}, "destination"),
    ],
)
def test_plan_validation(api_client_user, overrides, field):
    response = api_client_user.post(URL, _payload(**overrides), format="json")
    assert response.status_code == 400
    assert field in response.json()


def test_no_route_found_returns_422(api_client_user):
    with patch(
        "apps.routing.services.trip.get_route_options",
        side_effect=NoRouteFound("island"),
    ):
        response = api_client_user.post(URL, _payload(), format="json")
    assert response.status_code == 422


def test_weather_rate_limit_returns_503(api_client_user, fake_providers):
    with patch(
        "apps.routing.services.trip.get_forecasts",
        side_effect=WeatherRateLimited("quota"),
    ):
        response = api_client_user.post(URL, _payload(), format="json")
    assert response.status_code == 503
