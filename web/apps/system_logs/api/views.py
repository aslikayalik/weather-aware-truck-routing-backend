from rest_framework import viewsets, filters, mixins
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, CharFilter, DateTimeFilter
from drf_spectacular.utils import extend_schema

from ..models import ServerErrorLog, ClientErrorLog, QueryStatSnapshot
from .serializers import ServerErrorLogSerializer, ClientErrorLogSerializer, QueryStatSnapshotSerializer


class SystemLogPagination(LimitOffsetPagination):
    default_limit = 100
    max_limit = 1000


class ServerErrorLogFilter(FilterSet):
    source = CharFilter(field_name="source", lookup_expr="iexact")
    level = CharFilter(field_name="level", lookup_expr="iexact")
    exception_type = CharFilter(field_name="exception_type", lookup_expr="icontains")
    message = CharFilter(field_name="message", lookup_expr="icontains")
    request_path = CharFilter(field_name="request_path", lookup_expr="icontains")
    task_name = CharFilter(field_name="task_name", lookup_expr="icontains")
    created_at_from = DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_to = DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = ServerErrorLog
        fields = ["source", "level", "exception_type", "message", "request_path", "task_name"]


class QueryStatSnapshotFilter(FilterSet):
    metric = CharFilter(field_name="metric", lookup_expr="iexact")
    query = CharFilter(field_name="query", lookup_expr="icontains")
    captured_at_from = DateTimeFilter(field_name="captured_at", lookup_expr="gte")
    captured_at_to = DateTimeFilter(field_name="captured_at", lookup_expr="lte")

    class Meta:
        model = QueryStatSnapshot
        fields = ["metric", "query"]


class ClientErrorLogFilter(FilterSet):
    source = CharFilter(field_name="source", lookup_expr="iexact")
    level = CharFilter(field_name="level", lookup_expr="iexact")
    message = CharFilter(field_name="message", lookup_expr="icontains")
    url = CharFilter(field_name="url", lookup_expr="icontains")
    created_at_from = DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_to = DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = ClientErrorLog
        fields = ["source", "level", "message", "url"]


@extend_schema(tags=["SystemLogs"])
class ServerErrorLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ServerErrorLog.objects.all()
    serializer_class = ServerErrorLogSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ServerErrorLogFilter
    ordering_fields = ["created_at", "level", "source"]
    pagination_class = SystemLogPagination


@extend_schema(tags=["SystemLogs"])
class ClientErrorLogViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                             mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ClientErrorLog.objects.all()
    serializer_class = ClientErrorLogSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ClientErrorLogFilter
    ordering_fields = ["created_at", "level", "source"]
    pagination_class = SystemLogPagination

    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return [IsAdminUser()]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(user=user)


@extend_schema(tags=["SystemLogs"])
class QueryStatSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = QueryStatSnapshot.objects.all()
    serializer_class = QueryStatSnapshotSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = QueryStatSnapshotFilter
    ordering_fields = ["captured_at", "calls", "total_exec_time_ms", "mean_exec_time_ms", "rows"]
    pagination_class = SystemLogPagination
