FROM redis:7-alpine

# gettext for envsubst, dos2unix for line ending conversion
RUN apk add --no-cache gettext dos2unix

# Copy files
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY redis.conf.template /usr/local/etc/redis/redis.conf.template

# Convert Windows line endings to Unix (CRLF -> LF)
RUN dos2unix /usr/local/bin/entrypoint.sh /usr/local/etc/redis/redis.conf.template

# Set permissions
RUN chmod +x /usr/local/bin/entrypoint.sh

# Create redis user home directory for .rediscli_history
RUN mkdir -p /data && chown redis:redis /data

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]