from django.contrib import admin

from apps.user_group.models import UserGroup


# Register your models here.


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    filter_horizontal = ("users",)
