"""Fast test settings without Postgres/Redis: pytest --ds=weather_aware_truck_routing.test_settings"""
from weather_aware_truck_routing.settings import *  # noqa: F401,F403

SECRET_KEY = SECRET_KEY or "test-secret-key"  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LOGGING = {"version": 1, "disable_existing_loggers": False}
