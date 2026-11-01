from bisect import bisect_left, bisect_right
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.routing import geo
from apps.routing.planner import (
    CHECKPOINT_INTERVALS_MILES,
    Checkpoint,
    RoutePlan,
    Segment,
)
from apps.routing.risk import RiskLevel
from apps.routing.services.trip import TripPlan

MAX_LOAD_LB = 80_000
# Departure must leave the full trip inside Open-Meteo's 7-day forecast.
MAX_DEPARTURE_AHEAD = timedelta(days=4)
DEPARTURE_GRACE = timedelta(minutes=30)
COORD_DECIMALS = 5


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(required=False, allow_blank=True, max_length=255)


class TripPlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_time = serializers.DateTimeField()
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    checkpoint_interval_miles = serializers.ChoiceField(
        choices=CHECKPOINT_INTERVALS_MILES, default=25
    )

    def validate_departure_time(self, value):
        now = timezone.now()
        if value < now - DEPARTURE_GRACE:
            raise serializers.ValidationError("Departure time cannot be in the past.")
        if value > now + MAX_DEPARTURE_AHEAD:
            raise serializers.ValidationError(
                f"Departure must be within the next {MAX_DEPARTURE_AHEAD.days} days (forecast range)."
            )
        return value

    def validate(self, attrs):
        origin = (attrs["origin"]["lat"], attrs["origin"]["lon"])
        destination = (attrs["destination"]["lat"], attrs["destination"]["lon"])
        if geo.haversine_miles(origin, destination) < 1:
            raise serializers.ValidationError(
                {"destination": "Origin and destination must be at least 1 mile apart."}
            )
        return attrs


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200)


def _coord(point: geo.LatLon) -> list[float]:
    return [round(point[0], COORD_DECIMALS), round(point[1], COORD_DECIMALS)]


def _level_key(level: RiskLevel | None) -> str | None:
    return level.key if level is not None else None


def _segment_path(plan: RoutePlan, segment: Segment) -> list[list[float]]:
    """Display geometry between two miles, with interpolated end points."""
    route = plan.route
    display_miles = [route.cum_miles[i] for i in plan.display_indices]
    inner = plan.display_indices[
        bisect_right(display_miles, segment.from_mile) : bisect_left(
            display_miles, segment.to_mile
        )
    ]
    start, end = geo.points_at_miles(
        route.coords, route.cum_miles, [segment.from_mile, segment.to_mile]
    )
    return [_coord(start), *(_coord(route.coords[i]) for i in inner), _coord(end)]


def _checkpoint(cp: Checkpoint) -> dict:
    weather = cp.weather
    risk = cp.risk
    return {
        "mile": round(cp.mile, 1),
        "lat": round(cp.point[0], COORD_DECIMALS),
        "lon": round(cp.point[1], COORD_DECIMALS),
        "eta": cp.eta.isoformat(),
        "weather": (
            None
            if weather is None
            else {
                "wind_mph": round(weather.wind_mph, 1),
                "gust_mph": round(weather.gust_mph, 1),
                "rain_in_hr": round(weather.rain_in_hr, 3),
                "snow_in_hr": round(weather.snow_in_hr, 3),
            }
        ),
        "risk": (
            None
            if risk is None
            else {
                "level": risk.level.key,
                "wind": risk.wind.key,
                "rain": risk.rain.key,
                "snow": risk.snow.key,
                "drivers": risk.drivers,
                "load_adjusted": risk.load_adjusted,
            }
        ),
    }


def _route(plan: RoutePlan) -> dict:
    summary = plan.summary
    return {
        "id": plan.id,
        "label": plan.route.label,
        "provider": plan.route.provider,
        "rank": plan.rank,
        "recommended": plan.recommended,
        "distance_miles": round(plan.route.distance_miles, 1),
        "duration_seconds": round(plan.route.duration_seconds),
        "departure_time": plan.departure.isoformat(),
        "arrival_time": plan.arrival.isoformat(),
        "path": [_coord(plan.route.coords[i]) for i in plan.display_indices],
        "segments": [
            {
                "from_mile": round(s.from_mile, 1),
                "to_mile": round(s.to_mile, 1),
                "level": _level_key(s.level),
                "path": _segment_path(plan, s),
            }
            for s in plan.segments
        ],
        "checkpoints": [_checkpoint(cp) for cp in plan.checkpoints],
        "summary": {
            "miles_by_level": {
                level.key: round(miles, 1)
                for level, miles in summary.miles_by_level.items()
            },
            "unknown_miles": round(summary.unknown_miles, 1),
            "average_risk": round(summary.average_risk, 2),
            "max_level": _level_key(summary.max_level),
        },
    }


def trip_plan_to_dict(trip: TripPlan, request_data: dict) -> dict:
    heatmap = trip.heatmap
    recommended = trip.recommended
    return {
        "origin": request_data["origin"],
        "destination": request_data["destination"],
        "departure_time": request_data["departure_time"].isoformat(),
        "load_weight_lb": request_data["load_weight_lb"],
        "checkpoint_interval_miles": request_data["checkpoint_interval_miles"],
        "recommended_route_id": recommended.id,
        "recommendation_reason": recommended.reason,
        "routes": [_route(plan) for plan in trip.routes],
        "heatmap": {
            "start": heatmap.start.isoformat(),
            "step_hours": 1,
            "hours": len(heatmap.risk[0]) - 1 if heatmap.risk else 0,
            "cell_size_degrees": heatmap.step_degrees,
            "points": [list(cell) for cell in heatmap.cells],
            "risk": heatmap.risk,
            "wind_mph": heatmap.wind_mph,
            "rain_in_hr": heatmap.rain_in_hr,
            "snow_in_hr": heatmap.snow_in_hr,
        },
    }
