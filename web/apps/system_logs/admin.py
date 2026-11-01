from django.contrib import admin

from .models import ServerErrorLog, ClientErrorLog, QueryStatSnapshot


@admin.register(ServerErrorLog)
class ServerErrorLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "source", "level", "exception_type", "request_path", "task_name", "user"]
    list_filter = ["source", "level"]
    search_fields = ["message", "traceback", "request_path", "task_name"]
    readonly_fields = [f.name for f in ServerErrorLog._meta.fields]


@admin.register(ClientErrorLog)
class ClientErrorLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "source", "level", "message", "url", "user"]
    list_filter = ["source", "level"]
    search_fields = ["message", "stack", "url"]
    readonly_fields = [f.name for f in ClientErrorLog._meta.fields]


@admin.register(QueryStatSnapshot)
class QueryStatSnapshotAdmin(admin.ModelAdmin):
    list_display = ["captured_at", "metric", "calls", "total_exec_time_ms", "mean_exec_time_ms", "rows"]
    list_filter = ["metric"]
    search_fields = ["query"]
    readonly_fields = [f.name for f in QueryStatSnapshot._meta.fields]
