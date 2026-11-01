from django.urls import include, path
from rest_framework import routers

from apps.common.api.v1 import views
from .views import CaptchaGenerateView, CaptchaValidateView

app_name = "common_v1"

router = routers.DefaultRouter()
router.register(
    r"search-sharing-object",
    views.SharingObjectSearchViewSet,
    basename="common-search-sharing",
)
router.register(
    r"list-sharing-object",
    views.SharingObjectListViewSet,
    basename="common-list-sharing",
)
router.register(
    r'user-settings',
    views.UserSettingsViewSet,
    basename='user-settings'
)

urlpatterns = [
    path("", include(router.urls)),
    path('captcha/generate/', CaptchaGenerateView.as_view(), name='captcha-generate'),
    path('captcha/validate/', CaptchaValidateView.as_view(), name='captcha-validate'),
]
