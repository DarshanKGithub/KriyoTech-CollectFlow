from django.apps import AppConfig


class PartnersConfig(AppConfig):
    name = "partners"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.contrib.contenttypes.models import ContentType
        from .context import SchemaContentTypeCache
        ContentType.objects._cache = SchemaContentTypeCache()

