from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.users.api.v1.serializer import UserSerializer
from apps.user_group.api.v1.serializers import UserGroupSerializer
from apps.user_group.models import UserGroup


@extend_schema(
    tags=["user_group"],
    request=UserGroupSerializer,
    responses=UserGroupSerializer,
)
class TeamViewSet(viewsets.ModelViewSet):
    """
    A viewset that provides the standard actions for the Team model.

    Inherits:
        viewsets.ModelViewSet: A type of ViewSet that provides complete CRUD operations.

    Attributes:
        queryset: Specifies the set of data that this view will operate on.
        serializer_class: The serializer class that should be used for validating and deserializing input, and for serializing output.
        permission_classes: A list of permission classes that this view requires.
    """

    queryset = UserGroup.objects.all()
    serializer_class = UserGroupSerializer
    permission_classes = (IsAuthenticated,)


@extend_schema(
    tags=["user_group"],
    request=UserGroupSerializer,
    responses=UserGroupSerializer,
)
class TeamUserViewSet(mixins.ListModelMixin, GenericViewSet):
    """
    A viewset that provides the standard actions for the Team model.

    Inherits:
        viewsets.ModelViewSet: A type of ViewSet that provides complete CRUD operations.

    Attributes:
        queryset: Specifies the set of data that this view will operate on.
        serializer_class: The serializer class that should be used for validating and deserializing input, and for serializing output.
        permission_classes: A list of permission classes that this view requires.
    """

    def get_queryset(self):
        group_id = self.kwargs.get("id")
        return UserGroup.objects.get(id=group_id).users.all()

    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)
