from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .adapters import adapter
from .models import ERPConnection, ERPRecord, ERPSyncRun
from .security import ERPError
from .access import validate_background_access


@shared_task
def recover_stalled_jobs():
    from datetime import timedelta
    cutoff = timezone.now()-timedelta(minutes=15)
    ERPSyncRun.objects.filter(status__in=["QUEUED", "RUNNING"], created_at__lt=cutoff).update(status="FAILED", error="Import stalled. Start it again; record IDs protect against duplicate imports.", finished_at=timezone.now())
    ERPRecord.objects.filter(direction="OUTBOUND", status="SENDING", updated_at__lt=cutoff).update(status="UNKNOWN", error="Send stopped responding. Check the ERP and reconcile its document ID before any further action.", updated_at=timezone.now())


@shared_task
def schedule_imports():
    """Opt-in polling only. Outbound accounting writes always need review."""
    from datetime import timedelta
    from .catalog import CATALOG
    created = 0
    for connection_id in ERPConnection.objects.filter(enabled=True).values_list("id", flat=True):
        pending = []
        with transaction.atomic():
            connection = ERPConnection.objects.select_for_update().get(pk=connection_id)
            interval = connection.config.get("sync_interval_minutes", 0)
            if not connection.enabled or not interval: continue
            try:
                validate_background_access(connection)
            except ERPError:
                continue
            for resource in connection.config.get("sync_resources", CATALOG[connection.provider]["resources"]):
                if connection.provider == "DYNAMICS_FINANCE" and resource not in connection.config.get("entities", {}): continue
                latest = connection.runs.filter(resource=resource).order_by("-created_at").first()
                if latest and latest.status in {"QUEUED", "RUNNING"}: continue
                next_page = latest.page+1 if latest and latest.status == "COMPLETED" and latest.has_more else 1
                if next_page > 1000: continue
                if next_page == 1 and latest and latest.created_at > timezone.now()-timedelta(minutes=interval): continue
                run = ERPSyncRun.objects.create(connection=connection, resource=resource, page=next_page)
                pending.append(str(run.pk))
        for run_id in pending:
            try:
                pull_records.delay(run_id)
                created += 1
            except Exception:
                ERPSyncRun.objects.filter(pk=run_id).update(status="FAILED", error="Scheduled import could not be queued. Check Redis and Celery.", finished_at=timezone.now())
    return created


@shared_task
def pull_records(run_id):
    with transaction.atomic():
        run = ERPSyncRun.objects.select_for_update().select_related("connection").get(pk=run_id)
        if run.status != "QUEUED": return run.status
        run.status = "RUNNING"
        run.save(update_fields=["status"])
    try:
        connection_version = run.connection.updated_at
        validate_background_access(run.connection, run.requested_by)
        rows, more = adapter(run.connection).pull(run.resource, run.page)
        with transaction.atomic():
            run = ERPSyncRun.objects.select_for_update().select_related("connection").get(pk=run.pk)
            if run.status != "RUNNING": return "STALE_RESULT_IGNORED"
            connection = ERPConnection.objects.select_for_update().get(pk=run.connection_id)
            if not connection.enabled or connection.updated_at != connection_version:
                raise ERPError("Connection changed during sync. Discarded the response; start a new sync.")
            for external_id, payload in rows:
                if not external_id or len(external_id) > 200 or not isinstance(payload, dict):
                    raise ERPError("ERP returned an invalid record identifier or payload.")
                record, created = ERPRecord.objects.get_or_create(connection=connection, resource=run.resource, direction="INBOUND", external_id=external_id, defaults={"payload": payload})
                if not created and record.payload != payload:
                    record.payload = payload
                    record.status = "CONFLICT" if record.local_id else "NEEDS_REVIEW"
                    record.save(update_fields=["payload", "status", "updated_at"])
            run.record_count = len(rows)
            run.has_more = more
            run.status = "COMPLETED"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "record_count", "has_more", "finished_at"])
        return "COMPLETED"
    except Exception as error:
        message = str(error) if isinstance(error, ERPError) else "Sync failed. Check entity configuration and server logs; no raw provider error is exposed."
        ERPSyncRun.objects.filter(pk=run.pk).update(status="FAILED", error=message[:300], finished_at=timezone.now())
        return "FAILED"
