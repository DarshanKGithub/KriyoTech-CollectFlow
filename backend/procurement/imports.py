import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from vendors.models import Vendor
from .models import GRN, GRNLine, PurchaseOrder, PurchaseOrderLine
from .services import receipt_balance, record_purchase_order_revision

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 1000


def rows_from_upload(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        return None, Response(
            {"error": {"code": "VALIDATION_ERROR", "message": "CSV file is required"}},
            status=400,
        )
    if uploaded.size > MAX_IMPORT_BYTES:
        return None, Response(
            {"error": {"code": "VALIDATION_ERROR", "message": "CSV file exceeds 5 MB"}},
            status=400,
        )
    try:
        content = uploaded.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content, newline=""))
        if not reader.fieldnames or any(not name or not name.strip() for name in reader.fieldnames):
            raise ValueError("CSV must have a header row with named columns")
        headers = [name.strip() for name in reader.fieldnames]
        if len(set(headers)) != len(headers):
            raise ValueError("CSV header names must be unique")
        rows = []
        for raw_row in reader:
            row = {
                (key.strip() if key else key): value.strip() if isinstance(value, str) else value
                for key, value in raw_row.items()
            }
            rows.append(row)
            if len(rows) > MAX_IMPORT_ROWS:
                return None, Response(
                    {"error": {"code": "VALIDATION_ERROR", "message": "CSV may contain at most 1,000 data rows"}},
                    status=400,
                )
        if not rows:
            return None, Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "CSV must contain at least one data row"}},
                status=400,
            )
        return rows, None
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        return None, Response(
            {"error": {"code": "VALIDATION_ERROR", "message": str(exc) or "Upload a valid UTF-8 CSV file"}},
            status=400,
        )


def _process_rows(rows, import_row, preview):
    accepted = 0
    errors = []

    def process():
        nonlocal accepted
        for number, row in enumerate(rows, 2):
            try:
                with transaction.atomic():
                    if None in row:
                        raise ValueError("Row has more values than the header.")
                    import_row(row, number)
                accepted += 1
            except (
                KeyError,
                ValueError,
                InvalidOperation,
                Vendor.DoesNotExist,
                PurchaseOrder.DoesNotExist,
                PurchaseOrderLine.DoesNotExist,
            ) as exc:
                errors.append({"row": number, "message": str(exc) or "Invalid row", "values": row})

    if preview:
        with transaction.atomic():
            process()
            transaction.set_rollback(True)
    else:
        process()

    return {
        "preview": preview,
        "accepted_rows": accepted,
        "rejected_rows": len(errors),
        "errors": errors,
        "correction_rows": [
            {**error["values"], "import_error": error["message"], "source_row": error["row"]}
            for error in errors
        ],
    }


def _is_preview(request):
    value = request.data.get("preview", False)
    return value is True or str(value).lower() in {"1", "true", "yes"}


def _resolve_vendor(tenant, row):
    if row.get("vendor_code"):
        matches = Vendor.objects.filter(tenant=tenant, external_code=row["vendor_code"])
    elif row.get("gstin"):
        matches = Vendor.objects.filter(tenant=tenant, gstin=row["gstin"])
    else:
        raise ValueError("Vendor code or GSTIN is required")
    if matches.count() != 1:
        raise ValueError("Vendor reference is missing or ambiguous in this workspace")
    return matches.get()


class PurchaseOrderImport(APIView):
    permission_classes = [HasTenantMembership]

    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE"):
            return Response(
                {"error": {"code": "PERMISSION_DENIED", "message": "Purchase role required"}},
                status=403,
            )
        rows, error = rows_from_upload(request)
        if error:
            return error

        def import_row(row, number):
            if not row.get("po_number") or not row.get("line_no") or not row.get("quantity") or not row.get("rate") or not row.get("description"):
                raise ValueError("PO number, line number, quantity, rate, and description are required")
            vendor = _resolve_vendor(request.tenant, row)
            order_date = date.fromisoformat(row["order_date"]) if row.get("order_date") else None
            po, created = PurchaseOrder.objects.get_or_create(
                tenant=request.tenant,
                number=row["po_number"],
                defaults={"vendor": vendor, "order_date": order_date},
            )
            po = PurchaseOrder.objects.select_for_update().get(tenant=request.tenant, id=po.id)
            if po.vendor_id != vendor.id:
                raise ValueError("PO vendor does not match existing PO")
            if po.status != PurchaseOrder.Status.DRAFT:
                raise ValueError("Imported PO lines can only update a draft purchase order")
            line_no = int(row["line_no"])
            quantity = Decimal(row["quantity"])
            rate = Decimal(row["rate"])
            taxable_value = Decimal(row.get("taxable_value") or str(quantity * rate))
            gst_rate = Decimal(row.get("gst_rate") or "0")
            description = row["description"]
            if (
                line_no < 1
                or not quantity.is_finite()
                or not rate.is_finite()
                or not taxable_value.is_finite()
                or not gst_rate.is_finite()
                or quantity <= 0
                or rate < 0
                or taxable_value < 0
                or not 0 <= gst_rate <= 100
                or not description.strip()
            ):
                raise ValueError("Line quantity, rate, taxable value, GST rate or description is invalid")
            defaults = {
                "item_code": row.get("item_code", ""),
                "description": description,
                "quantity": quantity,
                "uom": row.get("uom", ""),
                "rate": rate,
                "taxable_value": taxable_value,
                "gst_rate": gst_rate,
            }
            existing_line = PurchaseOrderLine.objects.filter(
                tenant=request.tenant, purchase_order=po, line_no=line_no
            ).first()
            if existing_line and all(
                getattr(existing_line, field) == value for field, value in defaults.items()
            ):
                return
            PurchaseOrderLine.objects.update_or_create(
                tenant=request.tenant,
                purchase_order=po,
                line_no=line_no,
                defaults=defaults,
            )
            if not created:
                po.revision += 1
                po.save(update_fields=["revision"])
            record_purchase_order_revision(
                po, user=request.user, action="IMPORTED", change_note=f"CSV import row {number}"
            )
            AuditLog.objects.create(
                tenant=request.tenant,
                actor=request.user,
                action="PURCHASE_ORDER_LINE_IMPORTED",
                object_type="PurchaseOrder",
                object_id=str(po.id),
                metadata={"revision": po.revision, "line_no": line_no},
            )

        result = _process_rows(rows, import_row, _is_preview(request))
        return Response(result, status=200 if not result["rejected_rows"] else 207)


class GRNImport(APIView):
    permission_classes = [HasTenantMembership]

    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE", "STORE"):
            return Response(
                {"error": {"code": "PERMISSION_DENIED", "message": "Store or purchase role required"}},
                status=403,
            )
        rows, error = rows_from_upload(request)
        if error:
            return error

        def import_row(row, _number):
            if not row.get("po_number") or not row.get("grn_number") or not row.get("po_line_no") or not row.get("quantity_received"):
                raise ValueError("PO number, GRN number, PO line number, and received quantity are required")
            po = PurchaseOrder.objects.select_for_update().get(
                tenant=request.tenant,
                number=row["po_number"],
                status=PurchaseOrder.Status.APPROVED,
            )
            received_at = date.fromisoformat(row["received_at"]) if row.get("received_at") else None
            grn, _ = GRN.objects.get_or_create(
                tenant=request.tenant,
                number=row["grn_number"],
                defaults={
                    "vendor": po.vendor,
                    "purchase_order": po,
                    "received_at": received_at,
                },
            )
            if grn.purchase_order_id != po.id or grn.vendor_id != po.vendor_id:
                raise ValueError("GRN number is already linked to another purchase order")
            po_line = po.lines.get(line_no=int(row["po_line_no"]))
            quantity = Decimal(row["quantity_received"])
            if not quantity.is_finite() or quantity <= 0:
                raise ValueError("Received quantity must be positive")
            prior_line = GRNLine.objects.filter(
                tenant=request.tenant, grn=grn, purchase_order_line=po_line
            ).first()
            balance = receipt_balance(
                po_line,
                excluding_grn_line_id=prior_line.id if prior_line else None,
            )
            if balance["received"] + quantity > balance["maximum_receivable"]:
                raise ValueError(
                    f"PO line {po_line.line_no} exceeds its remaining receivable quantity of {balance['remaining_receivable']}"
                )
            GRNLine.objects.update_or_create(
                tenant=request.tenant,
                grn=grn,
                purchase_order_line=po_line,
                defaults={
                    "item_code": row.get("item_code", po_line.item_code),
                    "description": row.get("description", po_line.description),
                    "quantity_received": quantity,
                    "uom": row.get("uom", po_line.uom),
                },
            )

        result = _process_rows(rows, import_row, _is_preview(request))
        return Response(result, status=200 if not result["rejected_rows"] else 207)
