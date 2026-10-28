import hashlib
from decimal import Decimal
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from audit.models import AuditLog
from admin_console.models import AdminAuditLog
from .models import SourceAccount, ImportBatch, ImportRow, SettlementRecord
from .parsing import read_rows, normalized, fingerprint, MAX_BYTES


def audit(account, actor, action, object_id, metadata=None):
    values = dict(actor=actor, action=action, object_type="FinancialSource", object_id=str(object_id), metadata=metadata or {})
    if account.scope == "PLATFORM":
        from admin_console.models import AdminStaff
        values["actor_role"] = AdminStaff.objects.filter(user=actor).values_list("role", flat=True).first() or ""
        AdminAuditLog.objects.create(**values)
    else:
        AuditLog.objects.create(tenant_id=account.tenant_id, **values)


def stage(account, upload, actor):
    raw = upload.read(MAX_BYTES + 1)
    extension = upload.name.rsplit(".", 1)[-1].lower()
    try:
        source = read_rows(raw, extension)
    except ValueError as error:
        raise ValidationError({"file": str(error)}) from None
    digest = hashlib.sha256(raw).hexdigest()
    stored = None
    try:
        with transaction.atomic():
            account = SourceAccount.objects.select_for_update().get(pk=account.pk, active=True)
            existing = ImportBatch.objects.filter(account=account, content_hash=digest).first()
            if existing:
                return existing, False
            rows, errors, warnings, seen = [], [], [], {}
            source_ids = {str(data.get("external_id") or "").strip()[:120] for _, data in source}
            known = {(row.record_type, row.external_id): row.fingerprint for row in
                     SettlementRecord.objects.filter(account=account, external_id__in=source_ids).only("record_type", "external_id", "fingerprint")}
            for number, data in source:
                try:
                    row, notices = normalized(data, account.currency)
                    identity = (row["record_type"], row["external_id"])
                    hashed = fingerprint(row)
                    if identity in seen:
                        raise ValueError("Repeated provider identifier in this file; remove duplicate rows.")
                    seen[identity] = hashed
                    if identity in known and known[identity] != hashed:
                        raise ValueError("Provider ID conflicts with an approved observation. Import an explicit reversal/correction with a new ID.")
                    rows.append((number, row, hashed))
                    warnings.extend({"row": number, "message": message} for message in notices)
                except ValueError as error:
                    errors.append({"row": number, "message": str(error)})
            batch = ImportBatch.objects.create(account=account, filename=upload.name.replace("\\", "/").split("/")[-1][:180],
                content_hash=digest, status="INVALID" if errors else "NEEDS_REVIEW", row_count=len(source),
                errors=errors[:100], warnings=warnings[:100], imported_by=actor)
            ImportRow.objects.bulk_create([ImportRow(batch=batch, row_number=number, normalized=data, fingerprint=hashed)
                                          for number, data, hashed in rows])
            batch.original_file.save(f"source.{extension}", ContentFile(raw), save=False)
            stored = batch.original_file
            batch.save(update_fields=["original_file"])
            audit(account, actor, "SETTLEMENT_IMPORT_STAGED", batch.pk, {"rows": len(source), "invalid": bool(errors)})
            return batch, True
    except Exception:
        if stored:
            stored.delete(save=False)
        raise


@transaction.atomic
def review(batch, actor, decision, note, acknowledge=False):
    account = SourceAccount.objects.select_for_update().get(pk=batch.account_id)
    batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
    if not isinstance(decision, str) or decision not in {"APPROVED", "REJECTED"}:
        raise ValidationError("Choose APPROVED or REJECTED.")
    note = str(note or "").strip()
    if not note or len(note) > 500:
        raise ValidationError("A review note of up to 500 characters is required.")
    if batch.status in {"APPROVED", "REJECTED"}:
        if batch.status != decision:
            raise ValidationError("This import was already decided; history is not overwritten.")
        return batch
    if decision == "APPROVED":
        if not account.active or batch.status == "INVALID":
            raise ValidationError("Invalid imports or disabled accounts cannot be approved.")
        if batch.warnings and acknowledge is not True:
            raise ValidationError("Acknowledge incomplete source evidence before approving an observation.")
        rows = list(batch.rows.order_by("row_number"))
        # Settlements/refunds are materialized first, then full reversals. Source row order is preserved separately.
        rows.sort(key=lambda row: row.normalized["record_type"] == "REVERSAL")
        keys = {row.normalized["external_id"] for row in rows} | {row.normalized["reverses_id"] for row in rows}
        known = {(item.record_type, item.external_id): item for item in SettlementRecord.objects.filter(account=account, external_id__in=keys)}
        reversed_ids = set(SettlementRecord.objects.filter(account=account, reverses_id__in=[item.pk for item in known.values()]).values_list("reverses_id", flat=True))
        pending = []
        for row in rows:
            data = dict(row.normalized)
            key = (data["record_type"], data["external_id"])
            prior = known.get(key)
            if prior:
                if prior.fingerprint != row.fingerprint:
                    raise ValidationError(f"Row {row.row_number}: provider ID now conflicts with an approved observation.")
                continue
            reverse_type = data.pop("reverses_type")
            reverse_id = data.pop("reverses_id")
            reverse = None
            if data["record_type"] == "REVERSAL":
                reverse = known.get((reverse_type, reverse_id))
                if not reverse or reverse.pk in reversed_ids:
                    raise ValidationError(f"Row {row.row_number}: select an unreversed observation in the same source account.")
                original = reverse.net if reverse.record_type == "SETTLEMENT" else reverse.amount
                if abs(Decimal(original)) != Decimal(data["amount"]) or reverse.currency != data["currency"]:
                    raise ValidationError("Only exact full reversals in the same currency are supported.")
                reversed_ids.add(reverse.pk)
            item = SettlementRecord(account=account, source_row=row, fingerprint=row.fingerprint, reverses=reverse, **data)
            pending.append(item)
            known[key] = item
        # FK targets precede reversal rows, and no historical observation is updated.
        SettlementRecord.objects.bulk_create([item for item in pending if item.record_type != "REVERSAL"])
        SettlementRecord.objects.bulk_create([item for item in pending if item.record_type == "REVERSAL"])
    batch.status = decision
    batch.reviewed_by = actor
    batch.reviewed_at = timezone.now()
    batch.review_note = note
    batch.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    audit(account, actor, "SETTLEMENT_IMPORT_" + decision, batch.pk, {"rows": batch.row_count})
    return batch
