"""Scheduled, read-only Gmail invoice intake."""
import logging
import uuid
from types import SimpleNamespace

from celery import shared_task
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task
def build_bank_reconciliation_suggestions(statement_id=None):
    """Prepare deterministic bank matches; only unique exact-reference matches are linked."""
    from audit.models import AuditLog
    from .models import BankTransaction
    from . import reconciliation

    rows = BankTransaction.objects.filter(status=BankTransaction.Status.UNMATCHED,
        statement__source_account__isnull=False).select_related("tenant", "statement__source_account")
    if statement_id:
        rows = rows.filter(statement_id=statement_id)
    matched = suggested = skipped = 0
    for row in rows.order_by("created_at", "id").iterator(chunk_size=100):
        try:
            result = reconciliation.suggestions(row.tenant, row.pk)
            candidates = result.get("suggestions", [])
            if (len(candidates) == 1 and candidates[0].get("exact_reference")
                    and int(candidates[0].get("score", 0)) >= 80 and not candidates[0].get("rejected")):
                candidate = candidates[0]
                kind = candidate["target_type"]
                relation = reconciliation.RELATIONS[kind]
                # Recheck the row and target while writing; keep reconciliation
                # separate so a human still confirms bank settlement.
                with transaction.atomic():
                    locked = BankTransaction.objects.select_for_update().select_related("statement__source_account").get(pk=row.pk)
                    if locked.status != BankTransaction.Status.UNMATCHED or locked.reconciliation_group_id:
                        skipped += 1
                        continue
                    target = reconciliation.targets(locked.tenant, kind).filter(pk=candidate["target_id"]).first()
                    if (not target or target.source_account_id != locked.statement.source_account_id
                            or target.currency != locked.statement.currency
                            or abs(locked.amount) != target.amount
                            or reconciliation.claimed(locked.tenant, kind, target.pk, except_bank=locked.pk)):
                        skipped += 1
                        continue
                    setattr(locked, relation, target)
                    locked.status = BankTransaction.Status.MATCHED
                    locked.revision += 1
                    locked.save(update_fields=[relation, "status", "revision"])
                    AuditLog.objects.create(tenant=locked.tenant, actor=None, action="BANK_MATCH_AUTO_LINKED",
                        object_type="BankTransaction", object_id=str(locked.pk), metadata={
                            "target_type": kind, "target_id": str(target.pk), "candidate_id": candidate.get("candidate_id"),
                            "score": candidate.get("score"), "exact_reference": True,
                            "rule_version": result.get("rule_version"), "requires_human_reconciliation": True})
                    matched += 1
            else:
                suggested += len(candidates)
        except Exception:
            logger.exception("Automatic bank suggestion failed for transaction %s", row.pk)
            skipped += 1
    return {"statement_id": str(statement_id) if statement_id else None, "auto_linked": matched,
        "suggestions_saved": suggested, "skipped": skipped}


@shared_task
def sync_gmail_mailboxes():
    """Poll connected workspaces through the same idempotent sync path as manual sync."""
    from accounts.models import Membership
    from admin_console.services import has_feature
    from notifications.models import Notification
    from .models import GmailConnection
    from .views import GmailSync
    import redis

    synced = 0
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=3, socket_timeout=3)
    for connection in GmailConnection.objects.filter(active=True).select_related("tenant", "connected_by"):
        tenant = connection.tenant
        if tenant.is_deleted or not has_feature(tenant, "email_invoice_intake"):
            continue
        membership = Membership.objects.filter(tenant=tenant, is_active=True, user__is_active=True,
            role__in=[Membership.Role.OWNER, Membership.Role.FINANCE]).select_related("user").order_by("id").first()
        if not membership:
            continue
        lock_key = f"kriyopay:gmail-invoice-sync:{connection.pk}"
        lock_token = uuid.uuid4().hex
        if not client.set(lock_key, lock_token, nx=True, ex=240):
            continue
        try:
            request = SimpleNamespace(tenant=tenant, user=membership.user, membership=membership)
            response = GmailSync().post(request)
            synced += 1
            if response.status_code >= 400:
                message = response.data.get("error", "Mailbox sync needs attention.")
                if isinstance(message, dict):
                    message = message.get("message", "Mailbox sync needs attention.")
                Notification.objects.get_or_create(tenant=tenant, recipient=membership.user, channel="IN_APP",
                    payload={"title": "Invoice mailbox needs attention", "body": str(message)[:500],
                        "link": "/integrations/gmail", "category": "invoices", "gmail_connection_id": str(connection.id)},
                    defaults={"status": "UNREAD"})
        except Exception:
            logger.exception("Scheduled Gmail invoice intake failed for connection %s", connection.pk)
            Notification.objects.get_or_create(tenant=tenant, recipient=membership.user, channel="IN_APP",
                payload={"title": "Invoice mailbox sync failed", "body": "KriyoPay could not sync this mailbox. Check its connection and retry from Integrations.",
                    "link": "/integrations/gmail", "category": "invoices", "gmail_connection_id": str(connection.id)},
                defaults={"status": "UNREAD"})
        finally:
            client.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", 1, lock_key, lock_token)
    return {"mailboxes_synced": synced}


@shared_task
def send_daily_operations_digest():
    """Create a deduplicated daily in-app digest for actionable workspace queues."""
    from .models import BankTransaction
    from accounts.models import Membership
    from fleet.models import FleetFollowUp
    from invoices.models import Invoice
    from exceptions_app.models import InvoiceException
    from erp.models import ERPRecord, ERPSyncRun
    from notifications.models import Notification, NotificationPreference
    from tenants.models import Tenant
    from django.utils import timezone

    today = timezone.localdate()
    created = 0
    for tenant in Tenant.objects.filter(is_deleted=False).iterator(chunk_size=100):
        counts = {
            "invoice_review": Invoice.objects.filter(tenant=tenant, status__in=["REVIEW_REQUIRED", "EXTRACTION_FAILED", "EXCEPTION"]).count(),
            "approvals": Invoice.objects.filter(tenant=tenant, status="APPROVAL_PENDING").count(),
            "overdue_invoices": Invoice.objects.filter(tenant=tenant, due_date__lt=today,
                payment_status__in=["UNPAID", "PARTIALLY_PAID"]).exclude(status="REJECTED").count(),
            "exceptions": InvoiceException.objects.filter(tenant=tenant, status__in=["OPEN", "ASSIGNED"]).count(),
            "bank_rows": BankTransaction.objects.filter(tenant=tenant, status__in=["UNMATCHED", "DUPLICATE"]).count(),
            "fleet_followups": FleetFollowUp.objects.filter(tenant=tenant, status__in=["OPEN", "IN_PROGRESS"]).count(),
            "erp_errors": ERPRecord.objects.filter(connection__tenant=tenant, status__in=["FAILED", "ERROR", "NEEDS_REVIEW"]).count()
                + ERPSyncRun.objects.filter(connection__tenant=tenant, status__in=["FAILED", "ERROR"]).count(),
        }
        if not any(counts.values()):
            continue
        memberships = Membership.objects.filter(tenant=tenant, is_active=True,
            role__in=[Membership.Role.OWNER, Membership.Role.FINANCE, "FLEET"]).select_related("user")
        for membership in memberships.iterator():
            visible_counts = counts if membership.role in (Membership.Role.OWNER, Membership.Role.FINANCE) else {
                "fleet_followups": counts["fleet_followups"]
            }
            if not any(visible_counts.values()):
                continue
            labels = {"invoice_review": "Invoice review", "approvals": "Approvals",
                "overdue_invoices": "Overdue invoices", "exceptions": "Exceptions",
                "bank_rows": "Bank rows", "fleet_followups": "Fleet follow-ups", "erp_errors": "ERP sync issues"}
            summary = " · ".join(f"{labels[key]}: {value}" for key, value in visible_counts.items() if value)
            preference = NotificationPreference.objects.filter(tenant=tenant, user=membership.user).first()
            if preference and preference.preferences.get("daily_digest") is False:
                continue
            exists = Notification.objects.filter(tenant=tenant, recipient=membership.user,
                channel="IN_APP", payload__digest_date=today.isoformat()).exists()
            if exists:
                continue
            Notification.objects.create(tenant=tenant, recipient=membership.user, channel="IN_APP", status="UNREAD",
                payload={"title": "KriyoPay daily operations digest", "body": summary,
                    "link": "/needs-attention", "category": "daily_digest", "digest_date": today.isoformat(),
                    "counts": visible_counts})
            created += 1
    return {"digests_created": created, "date": today.isoformat()}
