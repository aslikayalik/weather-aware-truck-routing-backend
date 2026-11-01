from django.urls import path, include

urlpatterns = [
    path("auth/", include("apps.authentication.api.v1.urls")),
    path("user/", include("apps.users.api.v1.urls")),
    path("team/", include("apps.user_group.api.v1.urls")),
    path("user-roles/", include("apps.user_roles.api.urls")),
    path("common/", include("apps.common.api.v1.urls")),
    path("system-logs/", include("apps.system_logs.api.urls")),
    path("routing/", include("apps.routing.api.v1.urls")),
    # Register domain app URLs here
]
