from django.urls import include, path
from rest_framework import routers

from apps.user_group.api.v1 import views

app_name = "team_v1"

router = routers.DefaultRouter()

router.register(r"user-group", views.TeamViewSet)
router.register(
    r"user-group/(?P<id>[^/.]+)/user", views.TeamUserViewSet, basename="team-user"
)
urlpatterns = [
    path("", include(router.urls)),
]
