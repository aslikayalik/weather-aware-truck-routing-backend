"""Weather risk model: per-condition thresholds and load-weight rules.

Thresholds (lower bound inclusive, upper bound exclusive unless noted):

    Condition  Low        Moderate    High        Severe      No Travel
    Wind       <25 mph    25-34       35-44       45-54       >=55 mph
    Rain       <0.10 in/h 0.10-0.25   0.25-0.50   0.50-1.00   >1.00
    Snow       <0.5 in/h  0.5-1.0     1.0-2.0     2.0-3.0     >3.0

Load rules (wind only):
    >=55 mph                  -> No Travel for any load
    45-54 mph and >30,000 lb  -> No Travel
    35-44 mph and >40,000 lb  -> Severe

The rain/snow "No Travel" bounds are strict (">1.00"), so exactly 1.00 in/h is Severe.
"""

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def key(self) -> str:
        return self.name.lower()


WIND_MODERATE, WIND_HIGH, WIND_SEVERE, WIND_NO_TRAVEL = 25.0, 35.0, 45.0, 55.0
RAIN_MODERATE, RAIN_HIGH, RAIN_SEVERE, RAIN_NO_TRAVEL = 0.10, 0.25, 0.50, 1.00
SNOW_MODERATE, SNOW_HIGH, SNOW_SEVERE, SNOW_NO_TRAVEL = 0.5, 1.0, 2.0, 3.0

HEAVY_LOAD_NO_TRAVEL_LB = 30_000
HEAVY_LOAD_SEVERE_LB = 40_000


def _bucket(value: float, moderate: float, high: float, severe: float) -> RiskLevel:
    if value >= severe:
        return RiskLevel.SEVERE
    if value >= high:
        return RiskLevel.HIGH
    if value >= moderate:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def wind_level(mph: float) -> RiskLevel:
    if mph >= WIND_NO_TRAVEL:
        return RiskLevel.NO_TRAVEL
    return _bucket(mph, WIND_MODERATE, WIND_HIGH, WIND_SEVERE)


def rain_level(in_per_hr: float) -> RiskLevel:
    if in_per_hr > RAIN_NO_TRAVEL:
        return RiskLevel.NO_TRAVEL
    return _bucket(in_per_hr, RAIN_MODERATE, RAIN_HIGH, RAIN_SEVERE)


def snow_level(in_per_hr: float) -> RiskLevel:
    if in_per_hr > SNOW_NO_TRAVEL:
        return RiskLevel.NO_TRAVEL
    return _bucket(in_per_hr, SNOW_MODERATE, SNOW_HIGH, SNOW_SEVERE)


def loaded_wind_level(mph: float, load_lb: float) -> RiskLevel:
    """Wind level after applying the load-weight rules."""
    level = wind_level(mph)
    if level == RiskLevel.SEVERE and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return RiskLevel.NO_TRAVEL
    if level == RiskLevel.HIGH and load_lb > HEAVY_LOAD_SEVERE_LB:
        return RiskLevel.SEVERE
    return level


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    # True when the load rules raised the wind level above its weather-only value
    load_adjusted: bool

    @property
    def drivers(self) -> list[str]:
        """Conditions responsible for the overall level (empty when Low)."""
        if self.level == RiskLevel.LOW:
            return []
        return [
            name
            for name in ("wind", "rain", "snow")
            if getattr(self, name) == self.level
        ]


def assess(
    wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float
) -> RiskAssessment:
    wind = loaded_wind_level(wind_mph, load_lb)
    rain = rain_level(rain_in_hr)
    snow = snow_level(snow_in_hr)
    return RiskAssessment(
        level=max(wind, rain, snow),
        wind=wind,
        rain=rain,
        snow=snow,
        load_adjusted=wind != wind_level(wind_mph),
    )


# Piecewise-linear scales that map a raw value onto the 0-4 risk axis, with each
# threshold landing exactly on its level. Used for the continuous heatmap shading.
_WIND_SCALE = (
    (0.0, 0.0),
    (WIND_MODERATE, 1.0),
    (WIND_HIGH, 2.0),
    (WIND_SEVERE, 3.0),
    (WIND_NO_TRAVEL, 4.0),
)
_RAIN_SCALE = (
    (0.0, 0.0),
    (RAIN_MODERATE, 1.0),
    (RAIN_HIGH, 2.0),
    (RAIN_SEVERE, 3.0),
    (RAIN_NO_TRAVEL, 4.0),
)
_SNOW_SCALE = (
    (0.0, 0.0),
    (SNOW_MODERATE, 1.0),
    (SNOW_HIGH, 2.0),
    (SNOW_SEVERE, 3.0),
    (SNOW_NO_TRAVEL, 4.0),
)


def _scale(value: float, points: tuple[tuple[float, float], ...]) -> float:
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return points[-1][1]


def risk_index(
    wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float
) -> float:
    """Continuous 0-4 risk score whose integer part always equals the discrete level."""
    level = assess(wind_mph, rain_in_hr, snow_in_hr, load_lb).level
    continuous = max(
        _scale(wind_mph, _WIND_SCALE),
        _scale(rain_in_hr, _RAIN_SCALE),
        _scale(snow_in_hr, _SNOW_SCALE),
    )
    return min(max(continuous, float(level)), level + 0.99)
