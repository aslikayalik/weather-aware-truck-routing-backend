from rest_framework.routers import DefaultRouter

from .views import ServerErrorLogViewSet, ClientErrorLogViewSet, QueryStatSnapshotViewSet

router = DefaultRouter()
router.register(r"server", ServerErrorLogViewSet, basename="server-log")
router.register(r"client", ClientErrorLogViewSet, basename="client-log")
router.register(r"query-stats", QueryStatSnapshotViewSet, basename="query-stats-log")

urlpatterns = router.urls
