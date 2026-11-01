import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.routing.api.v1.serializers import (
    GeocodeQuerySerializer,
    TripPlanRequestSerializer,
    trip_plan_to_dict,
)
from apps.routing.services.geocoding import GeocodingError, search_places
from apps.routing.services.routing import NoRouteFound, RoutingError
from apps.routing.services.trip import plan_trip
from apps.routing.services.weather import WeatherError, WeatherRateLimited

logger = logging.getLogger(__name__)


class TripPlanView(APIView):
    """Plans three truck routes and rates their weather risk at each checkpoint's ETA."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "trip_plan"

    @extend_schema(
        tags=["routing"],
        request=TripPlanRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request):
        serializer = TripPlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            trip = plan_trip(
                origin=(data["origin"]["lat"], data["origin"]["lon"]),
                destination=(data["destination"]["lat"], data["destination"]["lon"]),
                departure=data["departure_time"],
                load_lb=data["load_weight_lb"],
                interval_miles=data["checkpoint_interval_miles"],
            )
        except WeatherRateLimited:
            return Response(
                {
                    "detail": "Weather provider rate limit reached. Please try again in a minute."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except NoRouteFound as exc:
            logger.info("No route found: %s", exc)
            return Response(
                {
                    "detail": "No drivable route was found between these places. "
                    "Check that both can be reached by road from each other "
                    "(for example, that they are on the same continent)."
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except (RoutingError, WeatherError) as exc:
            logger.warning("Trip planning failed: %s", exc)
            return Response(
                {
                    "detail": "Routing or weather service is unavailable. Please try again."
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(trip_plan_to_dict(trip, data))


class GeocodeView(APIView):
    """Place search for the origin / destination inputs."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    @extend_schema(
        tags=["routing"],
        parameters=[GeocodeQuerySerializer],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        serializer = GeocodeQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            results = search_places(serializer.validated_data["q"])
        except GeocodingError as exc:
            logger.warning("%s", exc)
            return Response(
                {"detail": "Place search is unavailable. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(results)
