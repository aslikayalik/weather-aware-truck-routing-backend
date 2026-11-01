from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from apps.user_roles.models import UserRole
from .serializers import UserRoleSerializer
from drf_spectacular.utils import extend_schema
from apps.users.models import User


@extend_schema(
    tags=["UserRole"]
)
class UserRoleViewSet(viewsets.ModelViewSet):
    serializer_class = UserRoleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name', 'display_name']

    def get_queryset(self):
        return UserRole.objects.filter(is_active=True)

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        force_delete = request.query_params.get('force', 'false').lower() == 'true'
        user_count = User.objects.filter(role_id=role.id).count()

        if not force_delete and user_count > 0:
            msg = f"{user_count} user(s) have this role. Are you sure you want to delete it?"
            return Response(
                {"detail": msg, "has_related": True},
                status=400
            )
            
        role.is_active = False
        role.save()
        return Response({"detail": "Role deactivated successfully."}, status=200)
