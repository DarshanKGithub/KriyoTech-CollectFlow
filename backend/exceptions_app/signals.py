from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import Membership
from notifications.models import Notification, NotificationPreference
from .models import ExceptionSLA, InvoiceException


@receiver(post_save, sender=InvoiceException)
def apply_exception_sla(sender, instance, created, **kwargs):
    if not created or instance.sla_due_at:
        return
    sla = ExceptionSLA.objects.filter(tenant_id=instance.tenant_id, exception_code=instance.code, active=True).first()
    if sla:
        InvoiceException.objects.filter(pk=instance.pk, sla_due_at__isnull=True).update(
            sla_due_at=timezone.now() + timedelta(hours=sla.due_after_hours), priority=sla.priority
        )
    if created:
        members = Membership.objects.filter(tenant_id=instance.tenant_id, is_active=True, role__in=["OWNER", "FINANCE", "PURCHASE", "STORE"]).select_related("user")
        for member in members:
            pref = NotificationPreference.objects.filter(tenant_id=instance.tenant_id, user=member.user).first()
            if pref and not pref.preferences.get("exceptions", True):
                continue
            Notification.objects.create(tenant_id=instance.tenant_id, recipient=member.user, channel="IN_APP", status="UNREAD",
                payload={"title": "Exception needs review", "body": f"{instance.code} was raised for invoice {instance.invoice_id}.", "link": "/exceptions"})
