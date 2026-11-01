from rest_framework.routers import DefaultRouter
from .views import UserRoleViewSet

router = DefaultRouter()
router.register(r'user-roles', UserRoleViewSet, basename='userrole')

urlpatterns = router.urls
