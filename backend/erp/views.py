from partners.instance import export_prefix
import json
import re
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .adapters import adapter, REGIONS
from .catalog import CATALOG, RESOURCES
from .models import ERPConnection, ERPRecord, ERPSyncRun
from .outbound import payload_for, tally_xml
from .records import MODELS, apply_inbound, snapshot, suggest
from .security import ERPError, credentials, encrypt


class ERPAccess(HasTenantMembership):
    def has_permission(self, request, view):
        if not super().has_permission(request, view): return False
        allowed = {"OWNER", "FINANCE"} | ({"AUDITOR"} if request.method == "GET" else set())
        if request.membership.role not in allowed:
            raise PermissionDenied("Owner or Finance access is required for ERP connections.")
        if request.membership.branch_scope_enabled:
            raise PermissionDenied("Company-wide ERP access requires an unrestricted Owner or Finance membership.")
        return True


def log(request, action, connection, record=None):
    AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=action,
        object_type="ERPRecord" if record else "ERPConnection", object_id=str(record.id if record else connection.id),
        metadata={"connection_id": str(connection.id), "provider": connection.provider})


def connection_data(connection):
    return {"id": str(connection.id), "provider": connection.provider, "name": connection.name,
        "config": connection.config, "has_credentials": bool(connection.encrypted_credentials),
        "enabled": connection.enabled, "tested_at": connection.tested_at, "last_error": connection.last_error}


def run_data(run):
    return {"id": str(run.id), "connection_id": str(run.connection_id), "resource": run.resource,
        "direction": run.direction, "status": run.status, "record_count": run.record_count,
        "page": run.page, "has_more": run.has_more, "error": run.error, "created_at": run.created_at}


def record_data(record):
    return {"id": str(record.id), "connection_id": str(record.connection_id), "resource": record.resource,
        "direction": record.direction, "external_id": record.external_id, "local_id": str(record.local_id) if record.local_id else None,
        "status": record.status, "error": record.error, "updated_at": record.updated_at}


class ERPView(APIView):
    permission_classes = [ERPAccess]

    def handle_exception(self, exc):
        if isinstance(exc, IntegrityError):
            return Response({"error": "This record conflicts with an existing record. Refresh the review queue and link the existing record if appropriate."}, status=409)
        if isinstance(exc, (ERPError, ValidationError, ValueError, TypeError, KeyError)):
            return Response({"error": str(exc) if isinstance(exc, ERPError) else "Invalid connection, document fields or record identifiers."}, status=400)
        return super().handle_exception(exc)

    def connection(self, request, connection_id):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(ERPConnection, tenant=request.tenant, pk=connection_id)


class Connections(ERPView):
    def get(self, request):
        return Response({"catalog": CATALOG, "encryption_configured": bool(settings.ERP_CREDENTIALS_KEY or settings.WEBHOOK_FERNET_KEY),
            "connections": [connection_data(row) for row in ERPConnection.objects.filter(tenant=request.tenant).order_by("name")]})

    @transaction.atomic
    def post(self, request):
        return self.save(request)

    def save(self, request, connection=None):
        provider = connection.provider if connection else request.data.get("provider")
        if provider not in CATALOG: raise ERPError("Choose a supported ERP provider.")
        name = str(request.data.get("name", connection.name if connection else "")).strip()
        config = request.data.get("config", connection.config if connection else {})
        secret = request.data.get("credentials", {})
        if not name or len(name) > 120 or not isinstance(config, dict) or not isinstance(secret, dict): raise ERPError("Connection name, configuration and credentials are required.")
        if len(json.dumps(config)) > 30000 or len(json.dumps(secret)) > 20000: raise ERPError("Connection settings are too large.")
        schema = CATALOG[provider]
        required = schema["config_fields"]
        if any(not isinstance(config.get(field), str) or not config[field].strip() for field in required): raise ERPError("Complete all required connection fields.")
        allowed = set(required) | {"entities", "defaults", "item_map", "tax_map", "supplier_groups", "receipt_line_map", "document_maps", "sync_interval_minutes", "sync_resources"}
        if set(config)-allowed: raise ERPError("Unsupported connection configuration field.")
        interval = config.get("sync_interval_minutes", 0)
        if not isinstance(interval, int) or (interval != 0 and not 5 <= interval <= 1440): raise ERPError("Automatic import interval must be 0 (off) or 5 to 1440 minutes.")
        if "sync_resources" in config and (not isinstance(config["sync_resources"], list) or not config["sync_resources"] or any(resource not in schema["resources"] for resource in config["sync_resources"])): raise ERPError("Choose supported resources for automatic imports.")
        for key in ("entities", "defaults", "item_map", "tax_map", "receipt_line_map", "document_maps"):
            if key in config and not isinstance(config[key], dict): raise ERPError(f"{key} must be an object.")
        if provider in {"ZOHO_BOOKS", "ZOHO_INVENTORY"} and config["region"] not in REGIONS: raise ERPError("Select a supported Zoho data centre.")
        if "base_url" in config:
            parsed = urlsplit(config["base_url"])
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
                raise ERPError("Enter the ERP site origin without paths, credentials or query parameters.")
            config["base_url"] = config["base_url"].rstrip("/")
        if provider == "DYNAMICS_FINANCE":
            if not re.fullmatch(r"[A-Za-z0-9.-]+", config["entra_tenant_id"]): raise ERPError("Enter a valid Entra tenant identifier.")
            for resource, entity in config.get("entities", {}).items():
                if resource not in RESOURCES or not isinstance(entity, dict) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(entity.get("collection", ""))): raise ERPError("Invalid Finance entity mapping.")
                fields = entity.get("key_fields")
                if not isinstance(fields, list) or not fields or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(field)) for field in fields): raise ERPError("Finance entities need valid key_fields.")
            for resource, mapping in config.get("document_maps", {}).items():
                if resource not in RESOURCES or not isinstance(mapping, dict): raise ERPError("Invalid Finance document mapping.")
                if not isinstance(mapping.get("header"), dict): raise ERPError("Finance document mappings require header fields.")
                if resource in {"invoices", "purchase_orders", "receipts"} and not isinstance(mapping.get("line"), dict): raise ERPError("Finance documents require header and line mappings.")
                for key in ("header_collection", "line_collection"):
                    if key in mapping and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(mapping[key])): raise ERPError("Invalid Finance document collection name.")
        if set(secret)-set(schema["secret_fields"]): raise ERPError("Unsupported credential field.")
        saved = credentials(connection) if connection else {}
        saved.update({key: value for key, value in secret.items() if isinstance(value, str) and value.strip()})
        if any(not saved.get(field) for field in schema["secret_fields"]): raise ERPError("Complete all required credentials. Existing secrets can be left blank when editing.")
        if connection is None: connection = ERPConnection(tenant=request.tenant, provider=provider, created_by=request.user)
        connection.name, connection.config = name, config
        connection.encrypted_credentials = encrypt(saved) if saved else ""
        connection.enabled = False
        connection.tested_at = None
        connection.last_error = ""
        connection.save()
        log(request, "ERP_CONNECTION_SAVED", connection)
        return Response(connection_data(connection), status=201)


class ConnectionDetail(Connections):
    def get(self, request, connection_id):
        return Response(connection_data(self.connection(request, connection_id)))

    @transaction.atomic
    def patch(self, request, connection_id):
        connection = self.connection(request, connection_id)
        connection = ERPConnection.objects.select_for_update().get(pk=connection.pk)
        return self.save(request, connection)

    @transaction.atomic
    def delete(self, request, connection_id):
        connection = self.connection(request, connection_id)
        connection.enabled = False
        connection.encrypted_credentials = ""
        connection.tested_at = None
        connection.save(update_fields=["enabled", "encrypted_credentials", "tested_at", "updated_at"])
        log(request, "ERP_CONNECTION_DISCONNECTED", connection)
        return Response({"status": "DISCONNECTED"})


class ConnectionTest(ERPView):
    def post(self, request, connection_id):
        connection = self.connection(request, connection_id)
        try:
            message = adapter(connection).test()
        except ERPError as error:
            ERPConnection.objects.filter(pk=connection.pk, updated_at=connection.updated_at).update(enabled=False, last_error=str(error)[:300])
            raise
        changed = ERPConnection.objects.filter(pk=connection.pk, updated_at=connection.updated_at).update(enabled=True, tested_at=timezone.now(), last_error="")
        if not changed: raise ERPError("Connection changed during the test; test the saved settings again.")
        log(request, "ERP_CONNECTION_VERIFIED", connection)
        return Response({"message": message, "enabled": True})


class SyncRuns(ERPView):
    def get(self, request):
        rows = ERPSyncRun.objects.filter(connection__tenant=request.tenant).order_by("-created_at")[:100]
        return Response([run_data(row) for row in rows])

    @transaction.atomic
    def post(self, request):
        connection = self.connection(request, request.data.get("connection_id"))
        connection = ERPConnection.objects.select_for_update().get(pk=connection.pk)
        resource = request.data.get("resource")
        if resource not in CATALOG[connection.provider]["resources"]: raise ERPError("This resource is not supported by the selected connection.")
        if not connection.enabled: raise ERPError("Test the connection successfully before importing.")
        page = int(request.data.get("page", 1))
        if not 1 <= page <= 100000: raise ERPError("Invalid page number.")
        existing = connection.runs.filter(resource=resource, page=page, status__in=["QUEUED", "RUNNING"]).first()
        if existing: return Response(run_data(existing), status=202)
        run = ERPSyncRun.objects.create(connection=connection, resource=resource, page=page, requested_by=request.user)
        def dispatch():
            try:
                from .tasks import pull_records
                pull_records.delay(str(run.id))
            except Exception:
                ERPSyncRun.objects.filter(pk=run.pk).update(status="FAILED", error="Could not queue the import. Check Redis and Celery, then start the import again.", finished_at=timezone.now())
        transaction.on_commit(dispatch)
        log(request, "ERP_IMPORT_QUEUED", connection)
        return Response(run_data(run), status=202)


class Records(ERPView):
    def get(self, request):
        rows = ERPRecord.objects.filter(connection__tenant=request.tenant).order_by("-updated_at")
        if request.query_params.get("connection_id"): rows = rows.filter(connection_id=request.query_params["connection_id"])
        if request.query_params.get("status"): rows = rows.filter(status=request.query_params["status"])
        from django.core.paginator import Paginator
        page = Paginator(rows, 50).get_page(request.query_params.get("page", 1))
        return Response({"results": [record_data(row) for row in page], "page": page.number, "pages": page.paginator.num_pages, "total": page.paginator.count})

    @transaction.atomic
    def post(self, request):
        connection = self.connection(request, request.data.get("connection_id"))
        resource = request.data.get("resource")
        if resource not in CATALOG[connection.provider]["resources"]: raise ERPError("Unsupported resource.")
        local = MODELS[resource].objects.filter(tenant=request.tenant, pk=request.data.get("local_id")).first()
        if not local: raise ERPError("Choose a local record from this workspace.")
        if resource == "suppliers" and not local.approved: raise ERPError("Approve the supplier before preparing an ERP export.")
        if resource == "purchase_orders" and local.status != "APPROVED": raise ERPError("Approve the purchase order before preparing an ERP export.")
        if resource == "receipts" and local.quality_status not in {"ACCEPTED", "PARTIAL"}: raise ERPError("Review and accept the receipt before preparing an ERP export.")
        if resource == "invoices":
            if local.status != "PAYMENT_READY" or local.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists(): raise ERPError("Only payment-ready invoices without blocking exceptions can be prepared.")
            if local.taxable_total+local.gst_total-local.tds_total != local.invoice_total: raise ERPError("Invoice totals must reconcile before ERP export.")
        if resource == "payments" and local.cancelled_at: raise ERPError("Cancelled payments cannot be exported.")
        connection = ERPConnection.objects.select_for_update().get(pk=connection.pk)
        existing = connection.records.filter(resource=resource, direction="OUTBOUND", local_id=local.pk).first()
        if existing and existing.status in {"SENDING", "SENT", "UNKNOWN", "RECONCILED"}: raise ERPError("This record has already been sent or needs reconciliation; it cannot be prepared again.")
        source, target = payload_for(connection, resource, local)
        record, _ = ERPRecord.objects.update_or_create(connection=connection, resource=resource, direction="OUTBOUND", local_id=local.pk,
            defaults={"payload": {"source": source, "target": target, "connection_version": connection.updated_at.isoformat()}, "status": "NEEDS_REVIEW", "error": ""})
        log(request, "ERP_EXPORT_PREPARED", connection, record)
        return Response(record_data(record), status=201)


class RecordDetail(ERPView):
    def record(self, request, record_id):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(ERPRecord.objects.select_related("connection__tenant"), connection__tenant=request.tenant, pk=record_id)

    def get(self, request, record_id):
        record = self.record(request, record_id)
        return Response({**record_data(record), "payload": record.payload, "suggested_import": suggest(record) if record.direction == "INBOUND" else None})

    def post(self, request, record_id):
        record = self.record(request, record_id)
        data = request.data.get("reviewed_import")
        if not isinstance(data, dict): raise ERPError("Review the import fields before applying.")
        if record.direction != "INBOUND": raise ERPError("Only inbound records can be imported here.")
        from admin_console.services import has_feature, get_limit
        features = {"purchase_orders": "po_grn_matching", "receipts": "po_grn_matching", "invoices": "invoice_upload", "payments": "payment_tracking"}
        feature = features.get(record.resource)
        if feature and request.tenant.admin_subscriptions.exists() and not has_feature(request.tenant, feature): raise PermissionDenied("Your plan does not include this resource.")
        if record.resource == "invoices" and not data.get("local_id"):
            limit = get_limit(request.tenant, "invoice_upload")
            if limit is not None and invoice_count(request.tenant) >= limit: raise PermissionDenied("Monthly invoice limit reached.")
        local = apply_inbound(record, data, request.user)
        return Response({"local_id": str(local.pk), "status": "APPLIED"})


def invoice_count(tenant):
    from invoices.models import Invoice
    return Invoice.objects.filter(tenant=tenant, created_at__date__gte=timezone.localdate().replace(day=1)).count()


class RecordDownload(RecordDetail):
    def get(self, request, record_id):
        record = self.record(request, record_id)
        if request.query_params.get("format") == "xml":
            if record.connection.provider != "TALLY" or record.direction != "OUTBOUND": raise ERPError("XML is available only for prepared Tally exports.")
            response = HttpResponse(tally_xml(record), content_type="application/xml")
            extension = "xml"
        else:
            response = HttpResponse(json.dumps(record.payload, indent=2), content_type="application/json")
            extension = "json"
        response["Content-Disposition"] = f'attachment; filename="{export_prefix()}-{record.resource}-{record.id}.{extension}"'
        log(request, "ERP_REVIEW_PACKAGE_DOWNLOADED", record.connection, record)
        return response


class RecordSend(RecordDetail):
    def post(self, request, record_id):
        if request.data.get("confirm_send") is not True: raise ERPError("Confirm sending this reviewed record to the connected ERP.")
        with transaction.atomic():
            record = self.record(request, record_id)
            record = ERPRecord.objects.select_for_update().select_related("connection").get(pk=record.pk)
            if record.direction != "OUTBOUND" or record.status != "NEEDS_REVIEW": raise ERPError("This export cannot be sent again. Check its sync outcome first.")
            connection = record.connection
            if not connection.enabled: raise ERPError("Test and enable the connection before sending.")
            if record.payload.get("connection_version") != connection.updated_at.isoformat(): raise ERPError("Connection mappings changed. Prepare the record again.")
            local = MODELS[record.resource].objects.filter(pk=record.local_id, tenant=request.tenant).first()
            if not local or snapshot(record.resource, local) != record.payload.get("source"): raise ERPError("The local record changed. Prepare a fresh review package before sending.")
            # Unsupported writes are stopped before entering the ambiguous state.
            if connection.provider == "TALLY" and record.resource not in {"suppliers", "invoices", "payments"}: raise ERPError("Tally orders and receipts require inventory-specific voucher mapping. Use the review package.")
            if connection.provider == "DYNAMICS_FINANCE" and record.payload["target"].get("mapping_required"): raise ERPError("Configure Finance header/line and journal mappings, then prepare a new review package.")
            if connection.provider == "TALLY":
                # Validate balanced, mapped XML before changing the send state.
                tally_xml(record)
            record.status = "SENDING"
            record.reviewed_by = request.user
            record.reviewed_at = timezone.now()
            record.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
            log(request, "ERP_SEND_STARTED", connection, record)
        try:
            payload = record.payload["target"]
            if connection.provider == "TALLY": payload = {"xml": tally_xml(record).decode(), "external_reference": str(record.id)}
            external_id = adapter(connection).send(record.resource, payload)
        except Exception as error:
            # A timeout can occur after the ERP committed the write. Never retry
            # a financial POST automatically without remote idempotency support.
            message = str(error) if isinstance(error, ERPError) else "ERP outcome is unknown. Check the ERP before recording the remote ID."
            ERPRecord.objects.filter(pk=record.pk, status__in=["SENDING", "UNKNOWN"]).update(status="UNKNOWN", error=message[:300], updated_at=timezone.now())
            return Response({"error": message, "status": "UNKNOWN"}, status=409)
        updated = ERPRecord.objects.filter(pk=record.pk, status__in=["SENDING", "UNKNOWN"]).update(status="SENT", external_id=external_id, error="", updated_at=timezone.now())
        if not updated: return Response({"status": "RECONCILIATION_PRESERVED", "external_id": external_id})
        log(request, "ERP_RECORD_SENT", connection, record)
        return Response({"status": "SENT", "external_id": external_id})


class RecordReconcile(RecordDetail):
    @transaction.atomic
    def post(self, request, record_id):
        record = self.record(request, record_id)
        record = ERPRecord.objects.select_for_update().get(pk=record.pk)
        external_id = str(request.data.get("external_id", "")).strip()
        note = str(request.data.get("note", "")).strip()
        if record.direction != "OUTBOUND" or record.status not in {"UNKNOWN", "SENDING", "NEEDS_REVIEW"} or not external_id or len(external_id) > 200 or not note:
            raise ERPError("Supply the verified remote ID and reconciliation note for an unresolved outbound record.")
        if record.status == "SENDING" and (timezone.now()-record.updated_at).total_seconds() < 900:
            raise ERPError("A send is still in progress. Wait for the result before reconciling.")
        record.external_id = external_id
        record.status = "RECONCILED"
        record.error = ""
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save()
        log(request, "ERP_RECORD_RECONCILED", record.connection, record)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="ERP_RECONCILIATION_NOTE", object_type="ERPRecord", object_id=str(record.pk), metadata={"note": note[:1000], "external_id": external_id})
        return Response({"status": "RECONCILED"})


class RecordConflictReview(RecordDetail):
    @transaction.atomic
    def post(self, request, record_id):
        record = self.record(request, record_id)
        record = ERPRecord.objects.select_for_update().get(pk=record.pk)
        note = str(request.data.get("note", "")).strip()
        if record.direction != "INBOUND" or record.status != "CONFLICT" or not note:
            raise ERPError("Review the local and ERP records and enter a note before acknowledging the difference.")
        record.status = "ACKNOWLEDGED"
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="ERP_CONFLICT_REVIEWED", object_type="ERPRecord", object_id=str(record.pk), metadata={"note": note[:1000], "local_id": str(record.local_id)})
        return Response({"status": "ACKNOWLEDGED"})
