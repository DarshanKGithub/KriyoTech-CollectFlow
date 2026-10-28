from django.apps import AppConfig
class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenants"

    def ready(self):
        from django.db.models.signals import post_save
        from django.dispatch import receiver
        from .models import Tenant, default_branch_for

        @receiver(post_save, sender=Tenant, dispatch_uid="tenants.ensure_default_branch")
        def ensure_default_branch(sender, instance, created, **kwargs):
            if created:
                default_branch_for(instance.id)
