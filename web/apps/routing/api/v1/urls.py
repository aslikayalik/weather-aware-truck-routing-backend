from django.urls import path

from apps.routing.api.v1.views import GeocodeView, TripPlanView

app_name = "routing_v1"

urlpatterns = [
    path("plan/", TripPlanView.as_view(), name="trip-plan"),
    path("geocode/", GeocodeView.as_view(), name="geocode"),
]
