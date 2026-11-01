from captcha.helpers import captcha_image_url
from captcha.models import CaptchaStore
from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.common.api.v1.serializer import (
    CaptchaSerializer,
    CaptchaValidateSerializer,
    SearchSharingQuerySerializer,
    SearchSharingResponseSerializer,
)
from apps.user_group.models import UserGroup
from apps.users.models import User


@extend_schema(
    tags=["common"],
    request=SearchSharingQuerySerializer,
    responses=SearchSharingResponseSerializer,
)
class SharingObjectSearchViewSet(GenericViewSet):
    """Text search across users and user groups."""

    permission_classes = [IsAuthenticated]
    serializer_class = SearchSharingQuerySerializer
    response_serializer_class = SearchSharingResponseSerializer

    @extend_schema(
        tags=["common"],
        request=SearchSharingQuerySerializer,
        responses=SearchSharingResponseSerializer,
        parameters=[SearchSharingQuerySerializer],
    )
    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        query = serializer.validated_data["query"]
        object_type = serializer.validated_data.get("object_type")
        result = []

        if object_type in (None, "user"):
            users = User.objects.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
                | Q(role__display_name__icontains=query),
                is_active=True,
            ).select_related("role")
            result += self.response_serializer_class(users, many=True).data

        if object_type in (None, "user_group"):
            groups = UserGroup.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query),
                is_active=True,
            )
            result += self.response_serializer_class(groups, many=True).data

        return Response(result)


@extend_schema(
    tags=["common"],
    request=None,
    responses=SearchSharingResponseSerializer,
)
class SharingObjectListViewSet(GenericViewSet):
    """Lists all active users and groups."""

    permission_classes = [IsAuthenticated]
    serializer_class = SearchSharingQuerySerializer
    response_serializer_class = SearchSharingResponseSerializer

    def list(self, request, *args, **kwargs):
        users = User.objects.filter(is_active=True).exclude(is_superuser=True).select_related("role")
        groups = UserGroup.objects.filter(is_active=True)
        return Response(
            self.response_serializer_class(users, many=True).data
            + self.response_serializer_class(groups, many=True).data
        )


@extend_schema(tags=["captcha"])
class CaptchaGenerateView(APIView):
    """
    Captcha generation endpoint - no authentication required
    GET /api/v1/common/captcha/generate/
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        responses={200: CaptchaSerializer},
        description="Generates a new captcha and returns key + image_url"
    )
    def get(self, request):
        captcha = CaptchaStore.generate_key()
        return Response({
            'key': captcha,
            'image_url': request.build_absolute_uri(captcha_image_url(captcha)),
        }, status=status.HTTP_200_OK)


@extend_schema(tags=["captcha"])
class CaptchaValidateView(APIView):
    """
    Captcha validation endpoint - no authentication required
    POST /api/v1/common/captcha/validate/
    """
    permission_classes = []
    authentication_classes = []
    serializer_class = CaptchaValidateSerializer

    @extend_schema(
        request=CaptchaValidateSerializer,
        responses={
            200: {"type": "object", "properties": {"valid": {"type": "boolean"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}}
        },
        description="Validates a captcha. Returns valid: true when key and value match"
    )
    def post(self, request):
        serializer = CaptchaValidateSerializer(data=request.data)
        if serializer.is_valid():
            return Response({'valid': True}, status=status.HTTP_200_OK)
        return Response(
            {'valid': False, 'error': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(tags=["common"])
class UserSettingsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def get_settings(self, request):
        profile = request.user.profile
        return Response({
            'font_size': profile.font_size,
            'max_upload_size_mb': settings.MAX_UPLOAD_SIZE_MB,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def update_font_size(self, request):
        new_size = request.data.get('font_size')
        if not new_size:
            return Response({'error': 'font_size is required'}, status=status.HTTP_400_BAD_REQUEST)

        profile = request.user.profile
        profile.font_size = new_size
        profile.save(update_fields=['font_size'])

        return Response({'message': 'Updated', 'font_size': new_size})
