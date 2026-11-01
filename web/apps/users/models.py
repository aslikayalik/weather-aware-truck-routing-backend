import uuid

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.files.storage import FileSystemStorage
from django.db import models

from apps.user_roles.models import UserRole


def get_avatar_storage():
    """Profile photos are stored on the local file system (AVATAR_LOCAL_ROOT)."""
    return FileSystemStorage(
        location=settings.AVATAR_LOCAL_ROOT,
        base_url=settings.AVATAR_LOCAL_URL,
    )


class CustomUserManager(UserManager):
    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        if not email:
            raise ValueError("Email is required.")
        if password and len(password) > 40:
            raise ValueError("Password must be 40 characters or fewer.")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    id = models.UUIDField(
        primary_key=True, editable=False, unique=True, default=uuid.uuid4
    )
    role = models.ForeignKey(
        UserRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    expire_date = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        db_table = "users"
        ordering = ["-date_joined"]

    objects = CustomUserManager()

    @property
    def search_display(self):
        return f"{self.first_name}, {self.last_name}, {self.email}"


class Profile(models.Model):
    INITIALS_SINGLE = "single"
    INITIALS_DOUBLE = "double"
    INITIALS_TYPE_CHOICES = (
        (INITIALS_SINGLE, "Single Initial"),
        (INITIALS_DOUBLE, "Double Initial"),
    )
    id = models.UUIDField(
        primary_key=True, editable=False, unique=True, default=uuid.uuid4
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile"
    )
    avatar = models.ImageField(
        upload_to="", blank=True, null=True, storage=get_avatar_storage
    )
    initials = models.CharField(max_length=2, blank=True, null=True)
    initials_type = models.CharField(
        max_length=10,
        choices=INITIALS_TYPE_CHOICES,
        default=INITIALS_DOUBLE
    )

    avatar_bg_color = models.CharField(max_length=7, default="#64b5f6")
    use_initials_avatar = models.BooleanField(default=True)

    font_size = models.IntegerField(default=16)

    def __str__(self):
        return self.user.email
