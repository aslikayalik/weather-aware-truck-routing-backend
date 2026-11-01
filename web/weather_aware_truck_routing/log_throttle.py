import hashlib
import time
from threading import Lock

# Prevents the same error (source + type + message) from being written to the DB repeatedly.
DEDUP_WINDOW_SECONDS = 30
# Caps the total number of writes per process, even for different errors
# (e.g. a broken middleware that fails with a different message on every request).
GLOBAL_WINDOW_SECONDS = 10
GLOBAL_MAX_WRITES = 30

_lock = Lock()
_last_seen: dict[str, float] = {}
_global_window_start = 0.0
_global_window_count = 0


def should_write(*key_parts: str) -> bool:
    """If True the record may be written to the DB; if False it should be skipped due to throttling/dedup.

    Note: this is a simple in-memory guard within a single process
    (same principle as the class-level throttle in the Telegram handler); it is not
    shared across worker processes, but it is a sufficient first line of defence
    against bursts of repeated errors.
    """
    global _global_window_start, _global_window_count

    now = time.monotonic()
    dedup_key = hashlib.sha1("|".join(key_parts).encode("utf-8", errors="ignore")).hexdigest()

    with _lock:
        if now - _global_window_start > GLOBAL_WINDOW_SECONDS:
            _global_window_start = now
            _global_window_count = 0
        _global_window_count += 1
        if _global_window_count > GLOBAL_MAX_WRITES:
            return False

        last_seen = _last_seen.get(dedup_key)
        if last_seen is not None and now - last_seen < DEDUP_WINDOW_SECONDS:
            return False
        _last_seen[dedup_key] = now

        if len(_last_seen) > 1000:
            cutoff = now - DEDUP_WINDOW_SECONDS
            for k in [k for k, v in _last_seen.items() if v < cutoff]:
                del _last_seen[k]

    return True
