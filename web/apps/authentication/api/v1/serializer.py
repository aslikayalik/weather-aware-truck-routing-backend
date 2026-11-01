import uuid
from datetime import date
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.authentication.session_store import set_active_session
from apps.common.redis_client import redis_client
from apps.users.api.v1.serializer import UserSerializer

User = get_user_model()

MAX_FAILED_ATTEMPTS = 3
LOCK_SECONDS = 180


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):

    remember = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        email = attrs.get(self.username_field)
        password = attrs.get("password")
        remember = attrs.get("remember", False)

        request = self.context.get("request")
        ip = request.META.get("REMOTE_ADDR", "unknown") if request else "unknown"
        redis_key = f"login_fail:{email}:{ip}"

        # Check whether the account is locked (after failed login attempts)
        fail_count = redis_client.get(redis_key)
        if fail_count and int(fail_count) >= MAX_FAILED_ATTEMPTS:
            ttl = redis_client.ttl(redis_key)
            raise serializers.ValidationError({
                "detail": f"Your account is locked. Please try again in {ttl // 60} min {ttl % 60} s."
            })

        if not email:
            raise serializers.ValidationError({"email": "Email is required."})
        if not password:
            raise serializers.ValidationError({"password": "Password is required."})

        user = User.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            self._record_failed_attempt(redis_key)
            raise serializers.ValidationError({"detail": "Email or password is incorrect."})

        # Deactivate the user if the expiry date has passed
        if user.expire_date and user.expire_date < date.today():
            user.is_active = False
            user.save(update_fields=["is_active"])

        if not user.is_active:
            raise serializers.ValidationError({"detail": "User account is inactive."})

        redis_client.delete(redis_key)

        refresh = self.get_token(user)

        # Every login generates a new session_id; this claim is also copied into the access token
        # and carried over on every token/refresh call (ROTATE_REFRESH_TOKENS=False).
        session_id = uuid.uuid4().hex
        refresh["session_id"] = session_id
        access_token = refresh.access_token

        set_active_session(user.id, session_id=session_id)

        update_last_login(None, user)
        return {
            "refresh": str(refresh),
            "access": str(access_token),
            "user": UserSerializer(user, context=self.context).data,
            "remember": remember,
        }

    @staticmethod
    def _record_failed_attempt(redis_key: str):
        """Record the failed attempt in Redis and lock the account temporarily once the limit is exceeded."""
        fail_count = redis_client.incr(redis_key)

        if fail_count == 1:
            redis_client.expire(redis_key, LOCK_SECONDS)

        if fail_count >= MAX_FAILED_ATTEMPTS:
            raise serializers.ValidationError({
                "detail": f"You have made {MAX_FAILED_ATTEMPTS} failed attempts. Your account is locked for {LOCK_SECONDS // 60} minutes."
            })
