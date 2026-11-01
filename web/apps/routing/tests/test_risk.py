import pytest

from apps.routing.risk import (
    RiskLevel,
    assess,
    loaded_wind_level,
    rain_level,
    risk_index,
    snow_level,
    wind_level,
)

L, M, H, S, N = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


@pytest.mark.parametrize(
    "mph, expected",
    [
        (0, L),
        (24.9, L),
        (25, M),
        (34.9, M),
        (35, H),
        (44.9, H),
        (45, S),
        (54.9, S),
        (55, N),
        (80, N),
    ],
)
def test_wind_thresholds(mph, expected):
    assert wind_level(mph) == expected


@pytest.mark.parametrize(
    "inches, expected",
    [
        (0, L),
        (0.09, L),
        (0.10, M),
        (0.249, M),
        (0.25, H),
        (0.49, H),
        (0.50, S),
        (1.00, S),
        (1.01, N),
    ],
)
def test_rain_thresholds(inches, expected):
    assert rain_level(inches) == expected


@pytest.mark.parametrize(
    "inches, expected",
    [
        (0, L),
        (0.49, L),
        (0.5, M),
        (0.99, M),
        (1.0, H),
        (1.99, H),
        (2.0, S),
        (3.0, S),
        (3.01, N),
    ],
)
def test_snow_thresholds(inches, expected):
    assert snow_level(inches) == expected


@pytest.mark.parametrize(
    "mph, load, expected",
    [
        (55, 0, N),  # >=55 mph is No Travel for any load
        (50, 30_000, S),  # 45-54 mph needs MORE than 30,000 lb
        (50, 30_001, N),
        (40, 40_000, H),  # 35-44 mph needs MORE than 40,000 lb
        (40, 40_001, S),
        (30, 80_000, M),  # load rules only apply from 35 mph
    ],
)
def test_load_rules(mph, load, expected):
    assert loaded_wind_level(mph, load) == expected


def test_assess_takes_worst_condition_and_reports_drivers():
    result = assess(wind_mph=40, rain_in_hr=0.3, snow_in_hr=0, load_lb=45_000)
    assert result.level == S
    assert result.wind == S and result.rain == H
    assert result.load_adjusted is True
    assert result.drivers == ["wind"]


def test_assess_low_has_no_drivers():
    assert assess(5, 0, 0, 10_000).drivers == []


@pytest.mark.parametrize(
    "wind, rain, snow, load",
    [
        (0, 0, 0, 0),
        (30, 0, 0, 0),
        (40, 0, 0, 45_000),
        (50, 0, 0, 35_000),
        (10, 0.3, 0, 0),
        (0, 1.0, 0, 0),
        (0, 0, 3.5, 0),
        (70, 0, 0, 0),
    ],
)
def test_risk_index_integer_part_matches_level(wind, rain, snow, load):
    index = risk_index(wind, rain, snow, load)
    assert int(index) == assess(wind, rain, snow, load).level
    assert 0 <= index < 5
