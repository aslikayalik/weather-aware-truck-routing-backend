import os
from celery import Celery
from celery.signals import task_failure

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weather_aware_truck_routing.settings')

app = Celery('weather_aware_truck_routing')

# Load config from Django settings (CELERY_ prefix)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all Django apps
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, einfo=None, **kwargs):
    # With worker_hijack_root_logger enabled, DBLogHandler may be dropped in the worker
    # process, so task errors are written directly through the ORM.
    try:
        from weather_aware_truck_routing.log_throttle import should_write

        task_name = getattr(sender, "name", str(sender))
        exception_type = type(exception).__name__ if exception else ""
        message = str(exception) if exception else ""
        if not should_write("celery", task_name, exception_type, message[:200]):
            return

        from apps.system_logs.models import ServerErrorLog
        ServerErrorLog.objects.create(
            source="celery",
            level="ERROR",
            logger_name=task_name,
            exception_type=exception_type,
            message=message,
            traceback=str(einfo) if einfo else "",
            task_name=task_name,
            task_id=task_id,
        )
    except Exception:
        pass