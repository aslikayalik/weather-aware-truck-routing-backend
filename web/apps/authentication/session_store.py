"""Redis-backed store that tracks a single active session per user.

JWTs are stateless, so the user's current active session is kept in Redis and compared with the
session_id claim of the access token on every authenticated request.
"""
import json
from datetime import datetime, timezone

from django.conf import settings

from apps.common.redis_client import redis_client

_KEY_PREFIX = "active_session"
_TERMINATED_SENTINEL = "__terminated__"


def _key(user_id) -> str:
    return f"{_KEY_PREFIX}:{user_id}"


def _ttl_seconds() -> int:
    return int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())


def get_active_session(user_id):
    raw = redis_client.get(_key(user_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def set_active_session(user_id, session_id: str, **extra):
    payload = {
        "session_id": session_id,
        "login_time": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    redis_client.set(_key(user_id), json.dumps(payload), ex=_ttl_seconds())
    return payload


def invalidate_session(user_id):
    """
    Forcibly invalidates a session (logout etc.).

    Does NOT delete the key; overwrites it with a sentinel value that no token's session_id can match.
    If we simply deleted it, is_session_valid's fail-open behaviour would make the session valid again.
    """
    redis_client.set(_key(user_id), json.dumps({"session_id": _TERMINATED_SENTINEL}), ex=_ttl_seconds())


def is_session_valid(user_id, session_id: str) -> bool:
    """Fails open when Redis has no record (e.g. Redis restarted); if a record exists the session_id must match."""
    if not user_id or not session_id:
        return True
    active = get_active_session(user_id)
    if active is None:
        return True
    return active.get("session_id") == session_id
