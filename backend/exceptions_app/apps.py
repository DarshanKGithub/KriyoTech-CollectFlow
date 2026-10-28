from django.apps import AppConfig
class ExceptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "exceptions_app"

    def ready(self):
        from . import signals  # noqa: F401
