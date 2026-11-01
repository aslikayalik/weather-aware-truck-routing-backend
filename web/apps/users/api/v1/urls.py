from django.urls import include, path
from rest_framework import routers

from apps.users.api.v1 import views
from apps.users.api.v1.views import PasswordChangeView, AvatarUpdateView

app_name = "user_v1"

router = routers.DefaultRouter()
router.register(r"admin", views.UserViewSet, basename="user")
router.register(r"me", views.MeViewSet, basename="me")

urlpatterns = [
    path("me/change-avatar/", AvatarUpdateView.as_view(), name="change-avatar"),
    path("me/change-password/", PasswordChangeView.as_view(), name="change-password"),
    path("", include(router.urls)),
]
