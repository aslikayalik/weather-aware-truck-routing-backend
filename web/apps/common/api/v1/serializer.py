from captcha.models import CaptchaStore
from rest_framework import serializers

from apps.users.models import User


class CaptchaSerializer(serializers.Serializer):
    """Serializer for captcha generation"""
    key = serializers.CharField(read_only=True)
    image_url = serializers.CharField(read_only=True)


class CaptchaValidateSerializer(serializers.Serializer):
    """Serializer for captcha validation"""
    key = serializers.CharField(required=True, help_text="Captcha key received from generation endpoint")
    value = serializers.CharField(required=True, help_text="User's captcha answer")

    def validate(self, attrs):
        """Validate captcha key and value"""
        key = attrs.get('key')
        value = attrs.get('value')

        try:
            captcha = CaptchaStore.objects.get(hashkey=key)
        except CaptchaStore.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired captcha key")

        if captcha.response.lower() != value.lower():
            raise serializers.ValidationError("Invalid captcha value")

        captcha.delete()  # Delete after use
        return attrs


class SearchSharingQuerySerializer(serializers.Serializer):
    query = serializers.CharField(
        help_text="Search text for users or user groups."
    )
    object_type = serializers.ChoiceField(
        required=False,
        choices=["user", "user_group"],
        help_text="The type of object to search for. Either 'user' or 'user_group'.",
    )


class SearchSharingResponseSerializer(serializers.Serializer):
    text = serializers.CharField(source="search_display")
    id = serializers.CharField()
    object_type = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    def get_object_type(self, obj) -> str:
        return "user" if isinstance(obj, User) else "user_group"

    def get_role(self, obj) -> str:
        if isinstance(obj, User) and obj.role:
            return obj.role.display_name
        return ""
