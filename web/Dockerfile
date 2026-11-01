###########
# BUILDER #
###########

FROM python:3.12-slim-bookworm AS builder

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# system deps (builder only)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --upgrade pip

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.txt


#########
# FINAL #
#########

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV APP_HOME=/app

WORKDIR $APP_HOME

# runtime deps only
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libpq-dev \
    ncat \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/src/app/wheels /wheels
COPY --from=builder /usr/src/app/requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache /wheels/*

COPY entrypoint.sh $APP_HOME
COPY . $APP_HOME

RUN chmod +x $APP_HOME/entrypoint.sh

ENTRYPOINT ["sh", "/app/entrypoint.sh"]

# Default command for platforms that run the image directly (docker-compose overrides it per service).
# PORT is provided by the hosting platform. Threads keep health checks and other requests
# responsive while a long trip plan is waiting on external weather/routing services.
CMD ["sh", "-c", "gunicorn weather_aware_truck_routing.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --worker-class gthread --threads ${GUNICORN_THREADS:-4} --timeout 120"]
