from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings

from apps.authentication.session_store import is_session_valid


class SingleSessionJWTAuthentication(JWTAuthentication):
    """
    Enforces a single active session.

    Rejects the request if the `session_id` claim in the access token does not match the user's current active session in Redis
    (i.e. the user logged in elsewhere or logged out).
    Tokens without a `session_id` are not subject to this check.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result
        session_id = validated_token.get("session_id")
        if not session_id:
            return result

        user_id = validated_token.get(api_settings.USER_ID_CLAIM)
        if not is_session_valid(user_id, session_id):
            raise AuthenticationFailed(
                {
                    "code": "session_terminated",
                    "detail": "Your session has ended. Please sign in again.",
                },
                code="session_terminated",
            )
        return result
