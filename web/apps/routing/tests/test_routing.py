from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.routing.services import routing
from apps.routing.services.routing import NoRouteFound, get_route_options
from apps.routing.tests.factories import straight_route


class FakeProvider:
    name = "fake"

    def __init__(self, routes):
        self._routes = routes

    def routes(self, locations, load_lb, alternates):
        return self._routes


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_routes_that_do_not_reach_the_destination_are_rejected():
    # The engine snapped an unreachable destination onto an unrelated road far away.
    stray = straight_route(miles=300, mph=60, lat=40.0, start_lon=-100.0)
    with patch.object(routing, "_providers", return_value=[FakeProvider([stray])]):
        with pytest.raises(NoRouteFound):
            get_route_options((40.0, -100.0), (46.95, 4.8), 30_000)


def test_routes_reaching_both_points_are_kept():
    route = straight_route(miles=300, mph=60, lat=40.0, start_lon=-100.0)
    destination = route.coords[-1]
    with (
        patch.object(routing, "_providers", return_value=[FakeProvider([route])]),
        patch.object(routing, "_fill_with_detours", side_effect=lambda p, r, *a: r),
    ):
        assert get_route_options((40.0, -100.0), destination, 30_000) == [route]
