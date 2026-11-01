from rest_framework import serializers

from ..models import ServerErrorLog, ClientErrorLog, QueryStatSnapshot


class ServerErrorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerErrorLog
        fields = [
            "id", "created_at", "source", "level", "logger_name", "exception_type",
            "message", "traceback", "request_method", "request_path", "status_code",
            "task_name", "task_id", "user", "extra",
        ]
        read_only_fields = fields


class ClientErrorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientErrorLog
        fields = [
            "id", "created_at", "source", "level", "message", "stack", "component_stack",
            "url", "user_agent", "app_version", "user", "extra",
        ]
        read_only_fields = ["id", "created_at", "user"]


class QueryStatSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueryStatSnapshot
        fields = [
            "id", "captured_at", "metric", "query", "calls",
            "total_exec_time_ms", "mean_exec_time_ms", "rows",
        ]
        read_only_fields = fields
