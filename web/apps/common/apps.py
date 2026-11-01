from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        from rest_framework.filters import SearchFilter

        from apps.common.api.filters import TurkishSearchFilter

        # Patch the method so already-imported viewsets keep working.
        SearchFilter.filter_queryset = TurkishSearchFilter.filter_queryset
