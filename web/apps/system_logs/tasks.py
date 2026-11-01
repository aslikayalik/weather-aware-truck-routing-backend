import logging
import os

from celery import shared_task
from django.db import connection, ProgrammingError
from django.utils import timezone

logger = logging.getLogger(__name__)

SYSTEM_LOG_RETENTION_DAYS = int(os.environ.get("SYSTEM_LOG_RETENTION_DAYS", 30))
QUERY_STATS_SNAPSHOT_LIMIT = int(os.environ.get("QUERY_STATS_SNAPSHOT_LIMIT", 20))


@shared_task(name="apps.system_logs.tasks.cleanup_old_system_logs", bind=True)
def cleanup_old_system_logs(self):
    """Deletes ServerErrorLog/ClientErrorLog/QueryStatSnapshot records older than SYSTEM_LOG_RETENTION_DAYS."""
    from apps.system_logs.models import ServerErrorLog, ClientErrorLog, QueryStatSnapshot

    cutoff = timezone.now() - timezone.timedelta(days=SYSTEM_LOG_RETENTION_DAYS)

    server_deleted, _ = ServerErrorLog.objects.filter(created_at__lt=cutoff).delete()
    client_deleted, _ = ClientErrorLog.objects.filter(created_at__lt=cutoff).delete()
    query_stats_deleted, _ = QueryStatSnapshot.objects.filter(captured_at__lt=cutoff).delete()

    logger.info(
        "system_logs cleanup: %s ServerErrorLog, %s ClientErrorLog, %s QueryStatSnapshot rows deleted (cutoff=%s)",
        server_deleted, client_deleted, query_stats_deleted, cutoff,
    )
    return {
        "server_deleted": server_deleted,
        "client_deleted": client_deleted,
        "query_stats_deleted": query_stats_deleted,
    }


@shared_task(name="apps.system_logs.tasks.snapshot_query_stats", bind=True)
def snapshot_query_stats(self):
    """Writes a snapshot of the most expensive and most frequent SELECTs from pg_stat_statements to QueryStatSnapshot.

    pg_stat_statements is reset on restart, so the persistent history is kept here.
    """
    from apps.system_logs.models import QueryStatSnapshot

    queries = {
        "total_time": """
            SELECT calls, total_exec_time, mean_exec_time, rows, query
            FROM pg_stat_statements
            WHERE query ILIKE 'select%%'
            ORDER BY total_exec_time DESC
            LIMIT %s
        """,
        "calls": """
            SELECT calls, total_exec_time, mean_exec_time, rows, query
            FROM pg_stat_statements
            WHERE query ILIKE 'select%%'
            ORDER BY calls DESC
            LIMIT %s
        """,
    }

    snapshots = []
    try:
        with connection.cursor() as cursor:
            for metric, sql in queries.items():
                cursor.execute(sql, [QUERY_STATS_SNAPSHOT_LIMIT])
                for calls, total_ms, mean_ms, row_count, query in cursor.fetchall():
                    snapshots.append(QueryStatSnapshot(
                        metric=metric,
                        query=query,
                        calls=calls,
                        total_exec_time_ms=total_ms,
                        mean_exec_time_ms=mean_ms,
                        rows=row_count,
                    ))
    except ProgrammingError:
        logger.warning("snapshot_query_stats: pg_stat_statements extension is not enabled; snapshot skipped.")
        return {"created": 0}

    QueryStatSnapshot.objects.bulk_create(snapshots)
    logger.info("snapshot_query_stats: %s rows saved.", len(snapshots))
    return {"created": len(snapshots)}
