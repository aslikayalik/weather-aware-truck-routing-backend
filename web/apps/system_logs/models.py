from django.conf import settings
from django.db import models


class ServerErrorLog(models.Model):
    SOURCE_CHOICES = [
        ("http", "HTTP Request"),
        ("celery", "Celery Task"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="http")
    level = models.CharField(max_length=16, default="ERROR")
    logger_name = models.CharField(max_length=255, blank=True)
    exception_type = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    traceback = models.TextField(blank=True)
    request_method = models.CharField(max_length=16, null=True, blank=True)
    request_path = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    status_code = models.IntegerField(null=True, blank=True)
    task_name = models.CharField(max_length=255, null=True, blank=True)
    task_id = models.CharField(max_length=64, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="server_error_logs")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.source}] {self.exception_type or self.level}: {self.message[:80]}"


class ClientErrorLog(models.Model):
    SOURCE_CHOICES = [
        ("error_boundary", "React Error Boundary"),
        ("rtk_query", "RTK Query"),
        ("window_onerror", "window.onerror"),
        ("unhandled_rejection", "Unhandled Rejection"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    level = models.CharField(max_length=16, default="error")
    message = models.TextField()
    stack = models.TextField(blank=True)
    component_stack = models.TextField(blank=True)
    url = models.CharField(max_length=1024, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    app_version = models.CharField(max_length=64, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="client_error_logs")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.source}] {self.message[:80]}"


class QueryStatSnapshot(models.Model):
    METRIC_CHOICES = [
        ("total_time", "Most expensive (total time)"),
        ("calls", "Most frequent"),
    ]

    captured_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metric = models.CharField(max_length=16, choices=METRIC_CHOICES, db_index=True)
    query = models.TextField()
    calls = models.BigIntegerField()
    total_exec_time_ms = models.FloatField()
    mean_exec_time_ms = models.FloatField()
    rows = models.BigIntegerField()

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"[{self.metric}] calls={self.calls} total_ms={self.total_exec_time_ms}: {self.query[:80]}"
