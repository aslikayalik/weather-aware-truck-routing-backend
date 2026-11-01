#!/bin/sh
set -e

echo "Generating redis.conf from template..."
envsubst < /usr/local/etc/redis/redis.conf.template > /usr/local/etc/redis/redis.conf

echo "Starting Redis with password protection..."
exec "$@"