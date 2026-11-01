import os
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from apps.users.models import User, Profile
from apps.user_group.api.v1.serializers import UserGroupSerializer
from apps.user_roles.models import UserRole


def build_initials(first_name: str | None, last_name: str | None, initials_type: str | None) -> str:
    """Build initials from the user's name"""
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    
    if not first:
        return ""
    
    if initials_type == "single":
        return first[0].upper()
    
    if last:
        return f"{first[0].upper()}{last[0].upper()}"
    
    return first[0].upper()


User = get_user_model()


class ProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField(read_only=True)
    initials = serializers.CharField(required=False, allow_blank=True)
    avatar_bg_color = serializers.CharField(required=False)
    use_initials_avatar = serializers.BooleanField(required=False)
    initials_type = serializers.CharField(required=False)

    class Meta:
        model = Profile
        fields = [
            "id", 
            "avatar", 
            "initials", 
            "avatar_bg_color", 
            "use_initials_avatar",
            "initials_type"
        ]

    def get_avatar(self, obj):
        """Return the avatar URL"""
        try:
            if obj.use_initials_avatar:
                return None

            if obj.avatar and hasattr(obj.avatar, "url"):
                url = obj.avatar.url
                # Build an absolute URL for local storage (/media/...)
                if url.startswith("/"):
                    request = self.context.get("request")
                    if request:
                        return request.build_absolute_uri(url)
                return url

        except Exception:
            return None

        return None

    def update(self, instance, validated_data):
        """Update the profile"""
        instance.initials = validated_data.get("initials", instance.initials)
        instance.use_initials_avatar = validated_data.get(
            "use_initials_avatar", 
            instance.use_initials_avatar
        )
        instance.avatar_bg_color = validated_data.get(
            "avatar_bg_color", 
            instance.avatar_bg_color
        )
        instance.initials_type = validated_data.get(
            "initials_type", 
            instance.initials_type
        )
        
        # Update the avatar if a file was uploaded
        avatar = validated_data.get('avatar')
        if avatar is not None:
            # Delete the old avatar
            if instance.avatar:
                try:
                    instance.avatar.delete(save=False)
                except:
                    pass
            instance.avatar = avatar

        instance.save()
        return instance


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(many=False) 
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password_confirmation = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    user_groups = UserGroupSerializer(many=True, read_only=True)
    role = serializers.PrimaryKeyRelatedField(
        queryset=UserRole.objects.all(), required=True, allow_null=False
    )
    role_detail = serializers.SerializerMethodField(read_only=True)  
    class Meta:
        depth = 1
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "expire_date",
            "profile",
            "role",
            "role_detail",
            "is_active",
            "is_superuser",
            "password",
            "password_confirmation",
            "user_groups",
            "last_login",
        ]
        read_only_fields = ["is_superuser", "last_login"]

    def get_role_detail(self, obj):
        if obj.role:
            return {
                "id": str(obj.role.id),
                "name": obj.role.name,
                "display_name": obj.role.display_name,
                "rank": obj.role.rank,
            }
        return None

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        if instance is None:  # Create operation
            if "password" not in attrs or not attrs["password"]:
                raise serializers.ValidationError(
                    {
                        "password": [
                            {
                                "message": "Password field is required.",
                                "code": "required",
                            }
                        ]
                    }
                )
            if "password_confirmation" not in attrs or not attrs["password_confirmation"]:
                raise serializers.ValidationError(
                    {
                        "password_confirmation": [
                            {
                                "message": "Password confirmation field is required.",
                                "code": "required",
                            }
                        ]
                    }
                )
        return attrs

    def create(self, validated_data):
        profile_data = validated_data.pop('profile', {})
        phone = validated_data.get("phone")
        # Expiry date check
        expire_date = validated_data.get("expire_date")
        if expire_date and expire_date < date.today():
            validated_data["is_active"] = False
        else:
            validated_data["is_active"] = validated_data.get("is_active", True)

        # Create the user
        user = User.objects.create_user(
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            role=validated_data["role"],
            is_active=validated_data["is_active"],
            expire_date=validated_data.get("expire_date"),
            phone=phone,
        )
        user.set_password(validated_data["password"])
        user.save()

        # Create the profile
        initials_type = profile_data.get("initials_type", "double")
        initials = build_initials(user.first_name, user.last_name, initials_type)
        
        Profile.objects.create(
            user=user,
            initials=initials,
            initials_type=initials_type,
            avatar_bg_color=profile_data.get("avatar_bg_color", "#64b5f6"),
            use_initials_avatar=profile_data.get("use_initials_avatar", True)
        )
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        phone = validated_data.get("phone", instance.phone)
        instance.email = validated_data.get("email", instance.email)
        instance.first_name = validated_data.get("first_name", instance.first_name)
        instance.last_name = validated_data.get("last_name", instance.last_name)
        instance.phone = phone

        if "role" in validated_data:
            role = validated_data["role"]
            if isinstance(role, str):
                try:
                    role = UserRole.objects.get(pk=role)
                except UserRole.DoesNotExist:
                    role = None
            instance.role = role

        instance.is_active = validated_data.get("is_active", instance.is_active)
        instance.expire_date = validated_data.get("expire_date", instance.expire_date)

        # Expiry date check
        expire_date = validated_data.get("expire_date", instance.expire_date)
        if expire_date and expire_date < date.today():
            instance.is_active = False

        if "password" in validated_data and validated_data["password"]:
            instance.set_password(validated_data["password"])
            
        instance.save()

        # Update or create the profile
        try:
            profile = instance.profile
        except Profile.DoesNotExist:
            initials_type = profile_data.get("initials_type", "double")
            initials = build_initials(instance.first_name, instance.last_name, initials_type)
            profile = Profile.objects.create(
                user=instance,
                initials=initials,
                initials_type=initials_type,
                avatar_bg_color=profile_data.get("avatar_bg_color", "#64b5f6"),
                use_initials_avatar=profile_data.get("use_initials_avatar", True)
            )

        profile.initials_type = profile_data.get("initials_type", profile.initials_type)
        profile.avatar_bg_color = profile_data.get("avatar_bg_color", profile.avatar_bg_color)
        profile.use_initials_avatar = profile_data.get("use_initials_avatar", profile.use_initials_avatar)
        profile.initials = build_initials(
            instance.first_name, 
            instance.last_name, 
            profile.initials_type
        )
        profile.save()
        return instance

class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    confirm_new_password = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context.get("request").user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct")
        return value

    def validate(self, data):
        if data["new_password"] != data["confirm_new_password"]:
            raise serializers.ValidationError(
                {"confirm_new_password": "New passwords must match"}
            )
        validate_password(data["new_password"])
        return data

    def save(self, **kwargs):
        user = self.context.get("request").user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user


class AvatarUploadSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    avatar = serializers.ImageField(required=False, allow_null=True)
    use_initials_avatar = serializers.BooleanField(required=False)
    initials_type = serializers.ChoiceField(
        choices=["single", "double"], 
        required=False
    )
    initials = serializers.CharField(required=False, read_only=True)
    avatar_bg_color = serializers.CharField(required=False)
    avatar_url = serializers.SerializerMethodField(read_only=True)

    def get_avatar_url(self, obj):
        """Return the avatar URL"""
        if obj.use_initials_avatar:
            return None

        if obj.avatar and hasattr(obj.avatar, "url"):
            url = obj.avatar.url
            if url.startswith("/"):
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(url)
            return url

        return None

    def create(self, validated_data):
        """Create a new avatar"""
        profile = self.context["request"].user.profile
        
        # use_initials_avatar setting
        profile.use_initials_avatar = validated_data.get(
            "use_initials_avatar", 
            profile.use_initials_avatar
        )
        
        # Avatar background color
        profile.avatar_bg_color = validated_data.get(
            "avatar_bg_color", 
            profile.avatar_bg_color
        )
        
        # Initials type
        if "initials_type" in validated_data:
            profile.initials_type = validated_data["initials_type"]
        
        # Avatar file
        if not profile.use_initials_avatar and "avatar" in validated_data:
            # Delete the old avatar
            if profile.avatar:
                try:
                    profile.avatar.delete(save=False)
                except:
                    pass
            profile.avatar = validated_data["avatar"]
        
        # Update initials
        if profile.use_initials_avatar:
            user = profile.user
            profile.initials = build_initials(
                user.first_name, 
                user.last_name, 
                profile.initials_type
            )
        
        profile.save()
        return profile

    def update(self, instance, validated_data):
        """Update the avatar"""
        profile = self.context["request"].user.profile
        
        # use_initials_avatar setting
        profile.use_initials_avatar = validated_data.get(
            "use_initials_avatar", 
            profile.use_initials_avatar
        )
        
        # Avatar background color
        profile.avatar_bg_color = validated_data.get(
            "avatar_bg_color", 
            profile.avatar_bg_color
        )
        
        # Initials type
        if "initials_type" in validated_data:
            profile.initials_type = validated_data["initials_type"]
        
        # Avatar file
        if not profile.use_initials_avatar and "avatar" in validated_data:
            # Delete the old avatar
            if profile.avatar:
                try:
                    profile.avatar.delete(save=False)
                except:
                    pass
            profile.avatar = validated_data["avatar"]
        
        # Update initials
        if profile.use_initials_avatar:
            user = profile.user
            profile.initials = build_initials(
                user.first_name, 
                user.last_name, 
                profile.initials_type
            )
        
        profile.save()
        return profile
