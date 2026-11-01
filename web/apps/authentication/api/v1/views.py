from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from apps.authentication.api.v1.serializer import MyTokenObtainPairSerializer
from apps.authentication.session_store import invalidate_session


@extend_schema(
    tags=["auth"],
    request=MyTokenObtainPairSerializer,
    responses=MyTokenObtainPairSerializer,
)
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@extend_schema(tags=["auth"])
class AuthTokenRefreshView(TokenRefreshView):
    pass


@extend_schema(tags=["auth"])
class AuthTokenVerifyView(TokenVerifyView):
    pass


@extend_schema(tags=["auth"], request=None, responses={204: None})
class LogoutView(APIView):
    """Ends the user's active session; existing access tokens become invalid."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        invalidate_session(request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
