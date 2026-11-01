import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

EXEC_TIME_RE = re.compile(r"Execution Time:\s*([\d.]+)\s*ms")


class Command(BaseCommand):
    help = (
        "Compares a SELECT query with EXPLAIN (ANALYZE, BUFFERS) before and after "
        "actually creating a candidate index. The index is created CONCURRENTLY "
        "(no table lock) and dropped automatically at the end unless --keep is "
        "given; only proven gains should be made permanent."
    )

    def add_arguments(self, parser):
        parser.add_argument("--query", required=True, help="SELECT query to test")
        parser.add_argument(
            "--index-name", required=True,
            help="Name of the candidate index (used to create and, if needed, drop it)",
        )
        parser.add_argument(
            "--index-sql", required=True,
            help="Full 'CREATE INDEX CONCURRENTLY <index-name> ON table(column)' statement",
        )
        parser.add_argument(
            "--keep", action="store_true",
            help="Do not drop the index at the end; keep it",
        )

    def handle(self, *args, **options):
        query = options["query"].strip()
        index_name = options["index_name"]
        index_sql = options["index_sql"].strip()

        if not query.upper().startswith("SELECT"):
            raise CommandError("--query must start with SELECT.")
        if "CREATE INDEX CONCURRENTLY" not in index_sql.upper() and "CREATE UNIQUE INDEX CONCURRENTLY" not in index_sql.upper():
            raise CommandError("--index-sql must use CONCURRENTLY to avoid locking.")
        if index_name not in index_sql:
            raise CommandError("--index-name does not appear in --index-sql; the names must match.")

        self.stdout.write(self.style.MIGRATE_HEADING("== Before creating the index =="))
        before_time, before_plan = self._explain(query)
        self.stdout.write(before_plan)

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n== Creating '{index_name}' (CONCURRENTLY) =="))
        with connection.cursor() as cursor:
            cursor.execute(index_sql)

        self.stdout.write(self.style.MIGRATE_HEADING("\n== After creating the index =="))
        after_time, after_plan = self._explain(query)
        self.stdout.write(after_plan)

        if before_time is not None and after_time is not None:
            delta = before_time - after_time
            pct = (delta / before_time * 100) if before_time else 0
            self.stdout.write(self.style.SUCCESS(
                f"\nExecution time: {before_time} ms -> {after_time} ms ({pct:.1f}% change)"
            ))

        if options["keep"]:
            self.stdout.write(self.style.WARNING(f"'{index_name}' was kept (--keep)."))
        else:
            self.stdout.write(f"\nDropping '{index_name}' (DROP INDEX CONCURRENTLY)...")
            with connection.cursor() as cursor:
                cursor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
            self.stdout.write("Dropped. If the gain is proven, run again with --keep or add it to a migration.")

    def _explain(self, query):
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {query}")
            lines = [row[0] for row in cursor.fetchall()]
        plan = "\n".join(lines)
        match = EXEC_TIME_RE.search(plan)
        exec_time = float(match.group(1)) if match else None
        return exec_time, plan
