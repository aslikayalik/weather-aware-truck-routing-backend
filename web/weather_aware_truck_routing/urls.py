"""
URL configuration for weather_aware_truck_routing project.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from weather_aware_truck_routing import api_v1_urls
from apps.common.views import health_check

urlpatterns = [
    path("api/v1/health/", health_check, name="health_check"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/v1/", include(api_v1_urls)),
    path("captcha/", include("captcha.urls")),
    path("", include("django_prometheus.urls")),
    # Serve local avatars (development; in production nginx handles this via an alias)
    re_path(r"^profile_images/(?P<path>.*)$", serve, {"document_root": settings.AVATAR_LOCAL_ROOT}),
]
