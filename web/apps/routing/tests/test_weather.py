from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.routing.services import weather
from apps.routing.services.weather import (
    OPEN_METEO_BLOCK_KEY,
    HourlyForecast,
    WeatherRateLimited,
    _parse_met,
    get_forecasts,
)

START = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)


def _step(hour: int, wind_mps: float, temp_c: float, next_1=None, next_6=None) -> dict:
    data = {"instant": {"details": {"wind_speed": wind_mps, "air_temperature": temp_c}}}
    if next_1 is not None:
        data["next_1_hours"] = {"details": {"precipitation_amount": next_1}}
    if next_6 is not None:
        data["next_6_hours"] = {"details": {"precipitation_amount": next_6}}
    time = (START + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"time": time, "data": data}


def _met(steps: list[dict]) -> dict:
    return {"properties": {"timeseries": steps}}


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_parse_met_converts_units_and_aligns_hourly_precipitation():
    forecast = _parse_met(
        _met(
            [
                _step(0, 10, 5, next_1=2.54),  # falls in the hour ending at 01:00
                _step(1, 20, 5, next_1=0),
            ]
        )
    )
    assert forecast.start == int(START.timestamp())
    assert forecast.wind_mph == [
        pytest.approx(22.4, abs=0.1),
        pytest.approx(44.7, abs=0.1),
    ]
    assert forecast.rain_in_hr == [0.0, 0.1]
    assert forecast.snow_in_hr == [0.0, 0.0]


def test_parse_met_spreads_six_hour_totals_and_interpolates_wind():
    forecast = _parse_met(
        _met(
            [
                _step(0, 0, 5, next_1=0, next_6=15.24),  # 6-hour gap follows
                _step(6, 6, 5, next_6=0),
            ]
        )
    )
    assert forecast.hours == 7
    assert forecast.rain_in_hr[1:7] == [0.1] * 6  # 15.24 mm / 6 h = 0.1 in/h
    assert forecast.wind_mph[3] == pytest.approx(3 * 2.23694, abs=0.1)


def test_parse_met_treats_freezing_precipitation_as_snow():
    forecast = _parse_met(
        _met([_step(0, 5, -3, next_1=2.54), _step(1, 5, -3, next_1=0)])
    )
    assert forecast.rain_in_hr[1] == 0.0
    assert forecast.snow_in_hr[1] == pytest.approx(1.0)  # 0.1 in water * 10


def _forecast(wind: float) -> HourlyForecast:
    return HourlyForecast(
        start=int(START.timestamp()),
        wind_mph=[wind],
        gust_mph=[wind],
        rain_in_hr=[0],
        snow_in_hr=[0],
    )


def test_rate_limited_open_meteo_falls_back_to_met_and_blocks_open_meteo():
    cells = {(40.0, -100.0), (40.2, -100.0)}
    limited = WeatherRateLimited(
        "Open-Meteo rate limit reached", retry_after_seconds=60
    )
    with (
        patch.object(weather, "_fetch_batch", side_effect=limited) as open_meteo,
        patch.object(weather, "_fetch_met", return_value=_forecast(7)) as met,
    ):
        result = get_forecasts(cells)
        assert set(result) == cells
        assert met.call_count == 2
        assert cache.get(OPEN_METEO_BLOCK_KEY)

        # While blocked, Open-Meteo is not called again.
        get_forecasts({(40.4, -100.0)})
        assert open_meteo.call_count == 1


def test_open_meteo_is_used_when_available():
    cells = {(40.0, -100.0)}
    with (
        patch.object(
            weather, "_fetch_batch", return_value={(40.0, -100.0): _forecast(5)}
        ),
        patch.object(weather, "_fetch_met") as met,
    ):
        assert get_forecasts(cells)[(40.0, -100.0)].wind_mph == [5]
    met.assert_not_called()
