from django.core.management.base import BaseCommand
from django.db import connection, ProgrammingError


class Command(BaseCommand):
    help = (
        "Produces an index/query analysis report from Postgres statistics: "
        "tables with heavy sequential scans, unused indexes and (if available) "
        "the most frequent / most expensive SELECT queries from pg_stat_statements."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="Number of rows per report")

    def handle(self, *args, **options):
        limit = options["limit"]

        self._report_seq_scans(limit)
        self._report_unused_indexes(limit)
        self._report_statements(limit)

    def _report_seq_scans(self, limit):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n== Tables with heavy sequential scans (top {limit}) =="))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT relname, seq_scan, seq_tup_read, idx_scan, n_live_tup
                FROM pg_stat_user_tables
                WHERE seq_scan > 0
                ORDER BY seq_scan DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cursor.fetchall()

        if not rows:
            self.stdout.write("No records (seq_scan=0).")
            return

        for relname, seq_scan, seq_tup_read, idx_scan, n_live_tup in rows:
            self.stdout.write(
                f"{relname:<40} seq_scan={seq_scan:<10} seq_tup_read={seq_tup_read:<12} "
                f"idx_scan={idx_scan:<10} n_live_tup={n_live_tup}"
            )

    def _report_unused_indexes(self, limit):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n== Never-used indexes (top {limit}) =="))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT relname, indexrelname, idx_scan
                FROM pg_stat_user_indexes
                WHERE idx_scan = 0
                ORDER BY relname, indexrelname
                LIMIT %s
                """,
                [limit],
            )
            rows = cursor.fetchall()

        if not rows:
            self.stdout.write("No unused indexes found.")
            return

        for relname, indexrelname, idx_scan in rows:
            self.stdout.write(f"{relname:<40} {indexrelname:<50} idx_scan={idx_scan}")

    def _report_statements(self, limit):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n== pg_stat_statements: en maliyetli SELECT'ler (ilk {limit}) =="))
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT calls, round(total_exec_time::numeric, 1), round(mean_exec_time::numeric, 1), rows, query
                    FROM pg_stat_statements
                    WHERE query ILIKE 'select%%'
                    ORDER BY total_exec_time DESC
                    LIMIT %s
                    """,
                    [limit],
                )
                rows = cursor.fetchall()
        except ProgrammingError:
            self.stdout.write(self.style.WARNING(
                "The pg_stat_statements extension is not enabled. It is installed automatically "
                "when migrations run (apps.common 0009) after applying the postgres 'command' "
                "setting from docker-compose and restarting the container."
            ))
            return

        if not rows:
            self.stdout.write("No records yet.")
            return

        for calls, total_ms, mean_ms, row_count, query in rows:
            self.stdout.write(
                f"calls={calls:<8} total_ms={total_ms:<12} mean_ms={mean_ms:<10} rows={row_count:<8} "
                f"{query[:160]}"
            )
