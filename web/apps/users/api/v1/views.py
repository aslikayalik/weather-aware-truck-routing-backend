from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.decorators import action
from rest_framework import mixins, status, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.users.api.v1.serializer import (
    UserSerializer,
    PasswordChangeSerializer,
    AvatarUploadSerializer,
    ProfileSerializer,
    build_initials
)
from apps.users.models import User


@extend_schema(
    tags=["me"],
    responses=UserSerializer,
)
class MeViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    pagination_class = None
    serializer_class = UserSerializer

    def get_serializer(self, *args, **kwargs):
        kwargs["many"] = False
        kwargs["partial"] = True
        return super().get_serializer(*args, **kwargs)

    def get_queryset(self):
        return self.queryset.filter(id=self.request.user.id).first()


@extend_schema(
    tags=["user"],
    request=UserSerializer,
    responses=UserSerializer,
)
class UserViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'email', 'role__display_name']
    ordering = ['-date_joined']

    def get_serializer_class(self):
        if self.action == "create":
            return UserSerializer
        return UserSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.action not in ["retrieve"]:
            queryset = queryset.exclude(is_superuser=True)

        status_param = self.request.query_params.get('status', 'all')
        if status_param == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_param == 'inactive':
            queryset = queryset.filter(is_active=False)
        return queryset

    @extend_schema(
        tags=["user"],
        request=UserSerializer,
        responses=UserSerializer,
        examples=[
            OpenApiExample(
                "User Creation Example",
                description="Create a new user",
                value={
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                    "expire_date": "2025-12-31",
                    "password": "password",
                    "password_confirmation": "password",
                    "is_active": True,
                    "role": "<role-uuid>",
                    "profile": {
                        "initials": "JD",  
                        "avatar_bg_color": "#64b5f6",  
                        "use_initials_avatar": True,
                        "initials_type": "double"
                    },
                },
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            role = serializer.validated_data.get('role')
            if role is not None:
                requester_rank = getattr(getattr(request.user, 'role', None), 'rank', 0)
                if requester_rank < getattr(role, 'rank', 0):
                    return Response(
                        {"detail": "You are not allowed to perform this action. You can only assign roles ranked at or below your own."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        tags=["user"],
        request=UserSerializer,
        responses=UserSerializer,
    )
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        requester_rank = getattr(getattr(request.user, 'role', None), 'rank', 0)

        if instance.pk != request.user.pk:
            target_rank = getattr(getattr(instance, 'role', None), 'rank', 0)
            if requester_rank < target_rank:
                return Response(
                    {"detail": "You are not allowed to perform this action. You can only manage users ranked at or below you."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            new_role = serializer.validated_data.get('role')
            if new_role is not None and instance.pk != request.user.pk:
                if requester_rank < getattr(new_role, 'rank', 0):
                    return Response(
                        {"detail": "You are not allowed to perform this action. You can only assign roles ranked at or below your own."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def list(self, request, *args, **kwargs):
        all_queryset = self.get_queryset()
        search_param = request.query_params.get('search', None)
        if search_param:
            all_queryset = all_queryset.filter(
                Q(first_name__icontains=search_param) |
                Q(last_name__icontains=search_param) |
                Q(email__icontains=search_param) |
                Q(role__display_name__icontains=search_param)
            )
        
        all_count = all_queryset.count()
        active_count = all_queryset.filter(is_active=True).count()
        inactive_count = all_queryset.filter(is_active=False).count()
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)

            paginated_response.data["meta"] = {
                "all_count": all_count,
                "active_count": active_count,
                "inactive_count": inactive_count,
            }
            return paginated_response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "results": serializer.data,
            "meta": {
                "all_count": all_count,
                "active_count": active_count,
                "inactive_count": inactive_count,
            }
        })
        


@extend_schema(
    tags=["me"],
    request=PasswordChangeSerializer,
    responses=PasswordChangeSerializer,
)
class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Password changed successfully"}, 
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["me"],
    request=AvatarUploadSerializer,
    responses=ProfileSerializer,
)
class AvatarUpdateView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """Upload or update the avatar"""
        profile = request.user.profile
        
        # Read the use_initials_avatar value
        use_initials_avatar_str = request.data.get("use_initials_avatar", "false")
        profile.use_initials_avatar = str(use_initials_avatar_str).lower() == "true"
        
        # Avatar background color
        if "avatar_bg_color" in request.data:
            profile.avatar_bg_color = request.data.get("avatar_bg_color")
        
        # Initials type
        if "initials_type" in request.data:
            profile.initials_type = request.data.get("initials_type")
        
        # Update initials (when use_initials_avatar is true)
        if profile.use_initials_avatar:
            profile.initials = build_initials(
                request.user.first_name, 
                request.user.last_name, 
                profile.initials_type
            )
        else:
            # Save the avatar file if one was uploaded
            avatar_file = request.FILES.get("avatar") or request.FILES.get("file")
            if avatar_file:
                # Delete the old avatar
                if profile.avatar:
                    try:
                        profile.avatar.delete(save=False)
                    except Exception:
                        pass
                
                profile.avatar = avatar_file
        
        profile.save()
        
        serializer = ProfileSerializer(profile, context={'request': request})
        
        return Response(
            {
                "message": "Avatar and profile updated successfully",
                "profile": serializer.data
            }, 
            status=status.HTTP_200_OK
        )

    def put(self, request, *args, **kwargs):
        """Update the avatar (PUT method)"""
        return self.post(request, *args, **kwargs)
