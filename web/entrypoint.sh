#!/bin/sh

if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for postgres..."

    while ! nc -z $DB_HOST $DB_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL started"
fi

# Migrations are applied only by the dedicated "migrate" service (RUN_MIGRATE=true).
# Running migrate from every container at once races against the same database.
if [ "$RUN_MIGRATE" = "true" ]; then
    python manage.py migrate
    python manage.py initial_data
else
    echo "Skipping migrations (RUN_MIGRATE is not 'true')"
fi

python manage.py collectstatic --no-input

exec "$@"
