import logging
import traceback as tb_module

from django.db import transaction

from weather_aware_truck_routing.log_throttle import should_write


class DBLogHandler(logging.Handler):
    """Writes ERROR+ log records to the ServerErrorLog table.

    Same defensive principle as telegram_logger.TelegramLogHandler: logging
    must never cause a new error itself.
    """

    def emit(self, record):
        try:
            from apps.system_logs.models import ServerErrorLog
            from apps.helper.middleware.current_user import get_current_authenticated_user

            exc_type = exc_message = tb_text = None
            if record.exc_info:
                exc_type = record.exc_info[0].__name__ if record.exc_info[0] else None
                exc_message = str(record.exc_info[1]) if record.exc_info[1] else None
                tb_text = "".join(tb_module.format_exception(*record.exc_info))

            message = exc_message or record.getMessage()
            if not should_write("http", record.name, exc_type or "", message[:200]):
                return

            request = getattr(record, "request", None)

            with transaction.atomic():
                ServerErrorLog.objects.create(
                    source="http",
                    level=record.levelname,
                    logger_name=record.name,
                    exception_type=exc_type or "",
                    message=message,
                    traceback=tb_text or "",
                    request_path=getattr(request, "path", None),
                    request_method=getattr(request, "method", None),
                    status_code=getattr(record, "status_code", None),
                    user=get_current_authenticated_user(),
                )
        except Exception:
            pass
