import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from django.utils import timezone


# Create your models here.


class UserGroup(models.Model):
    EVERYONE = "Everyone"
    id = models.UUIDField(
        primary_key=True, editable=False, unique=True, default=uuid.uuid4
    )
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True, max_length=255)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="user_groups",
        db_table="user_groups",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "User Group"
        verbose_name_plural = "User Groups"
        db_table = "user_group"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def search_display(self):
        return self.name

    def clean(self):
        if self.created_at and self.created_at >= timezone.now():
            raise ValidationError("The 'created_at' value cannot be in the future.")

    def save(self, *args, **kwargs):
        self.clean()

        # Deactivate if expire_date is in the past
        if self.expire_date and self.expire_date < date.today():
            self.is_active = False

        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        if self.name == UserGroup.EVERYONE:
            pass
        else:
            super().delete(using=using, keep_parents=keep_parents)
