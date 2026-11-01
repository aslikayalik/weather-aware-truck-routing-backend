from django.urls import path

from apps.authentication.api.v1.views import (
    MyTokenObtainPairView,
    AuthTokenRefreshView,
    AuthTokenVerifyView,
    LogoutView,
)

app_name = "auth_v1"

urlpatterns = [
    path("token/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", AuthTokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", AuthTokenVerifyView.as_view(), name="token_verify"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
