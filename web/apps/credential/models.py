from django.db import models

# Create your models here.


class Credential(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, unique=True)
    name = models.CharField(max_length=100)
    credential_type = models.CharField(max_length=100)
    options = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Credential"
        verbose_name_plural = "Credentials"
        db_table = "credential"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
