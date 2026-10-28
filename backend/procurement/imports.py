import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .models import PurchaseOrder, PurchaseOrderLine, GRN, GRNLine
from .services import receipt_balance, record_purchase_order_revision
from vendors.models import Vendor

def rows_from_upload(request):
    uploaded = request.FILES.get("file")
    if not uploaded: return None, Response({"error": {"code": "VALIDATION_ERROR", "message": "CSV file is required"}}, status=400)
    try: return list(csv.DictReader(io.TextIOWrapper(uploaded.file, encoding="utf-8-sig"))), None
    except (UnicodeDecodeError, csv.Error): return None, Response({"error": {"code": "VALIDATION_ERROR", "message": "Upload a UTF-8 CSV file"}}, status=400)

class PurchaseOrderImport(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Purchase role required"}}, status=403)
        rows, error = rows_from_upload(request)
        if error: return error
        accepted, errors = 0, []
        for number, row in enumerate(rows, 2):
            try:
                with transaction.atomic():
                    vendor = Vendor.objects.get(tenant=request.tenant, external_code=row.get("vendor_code", "")) if row.get("vendor_code") else Vendor.objects.get(tenant=request.tenant, gstin=row.get("gstin", ""))
                    po, created = PurchaseOrder.objects.get_or_create(tenant=request.tenant, number=row["po_number"], defaults={"vendor": vendor, "order_date": date.fromisoformat(row["order_date"]) if row.get("order_date") else None})
                    po = PurchaseOrder.objects.select_for_update().get(tenant=request.tenant, id=po.id)
                    if po.vendor_id != vendor.id: raise ValueError("PO vendor does not match existing PO")
                    if po.status != PurchaseOrder.Status.DRAFT: raise ValueError("Imported PO lines can only update a draft purchase order")
                    line_no = int(row["line_no"]); quantity = Decimal(row["quantity"]); rate = Decimal(row["rate"])
                    taxable_value = Decimal(row.get("taxable_value") or str(quantity * rate)); gst_rate = Decimal(row.get("gst_rate") or "0")
                    if line_no < 1 or not quantity.is_finite() or not rate.is_finite() or not taxable_value.is_finite() or not gst_rate.is_finite() or quantity <= 0 or rate < 0 or taxable_value < 0 or not 0 <= gst_rate <= 100 or not row.get("description", "").strip():
                        raise ValueError("Line quantity, rate, taxable value, GST rate or description is invalid")
                    PurchaseOrderLine.objects.update_or_create(tenant=request.tenant, purchase_order=po, line_no=line_no, defaults={"item_code": row.get("item_code", ""), "description": row["description"], "quantity": quantity, "uom": row.get("uom", ""), "rate": rate, "taxable_value": taxable_value, "gst_rate": gst_rate})
                    if not created:
                        po.revision += 1
                        po.save(update_fields=["revision"])
                    record_purchase_order_revision(po, user=request.user, action="IMPORTED", change_note=f"CSV import row {number}")
                    AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="PURCHASE_ORDER_LINE_IMPORTED", object_type="PurchaseOrder", object_id=str(po.id), metadata={"revision": po.revision, "line_no": line_no})
                accepted += 1
            except (KeyError, ValueError, InvalidOperation, Vendor.DoesNotExist) as exc: errors.append({"row": number, "message": str(exc) or "Invalid row"})
        return Response({"accepted_rows": accepted, "rejected_rows": len(errors), "errors": errors}, status=200 if not errors else 207)

class GRNImport(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE", "STORE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Store or purchase role required"}}, status=403)
        rows, error = rows_from_upload(request)
        if error: return error
        accepted, errors = 0, []
        for number, row in enumerate(rows, 2):
            try:
                with transaction.atomic():
                    po = PurchaseOrder.objects.select_for_update().get(tenant=request.tenant, number=row["po_number"], status=PurchaseOrder.Status.APPROVED)
                    grn, _ = GRN.objects.get_or_create(tenant=request.tenant, number=row["grn_number"], defaults={"vendor": po.vendor, "purchase_order": po, "received_at": date.fromisoformat(row["received_at"]) if row.get("received_at") else None})
                    if grn.purchase_order_id != po.id or grn.vendor_id != po.vendor_id: raise ValueError("GRN number is already linked to another purchase order")
                    po_line = po.lines.get(line_no=int(row["po_line_no"]))
                    quantity = Decimal(row["quantity_received"])
                    if not quantity.is_finite() or quantity <= 0: raise ValueError("Received quantity must be positive")
                    prior_line = GRNLine.objects.filter(tenant=request.tenant, grn=grn, purchase_order_line=po_line).first()
                    balance = receipt_balance(po_line, excluding_grn_line_id=prior_line.id if prior_line else None)
                    if balance["received"] + quantity > balance["maximum_receivable"]:
                        raise ValueError(f"PO line {po_line.line_no} exceeds its remaining receivable quantity of {balance['remaining_receivable']}")
                    GRNLine.objects.update_or_create(tenant=request.tenant, grn=grn, purchase_order_line=po_line, defaults={"item_code": row.get("item_code", po_line.item_code), "description": row.get("description", po_line.description), "quantity_received": quantity, "uom": row.get("uom", po_line.uom)})
                accepted += 1
            except (KeyError, ValueError, InvalidOperation, PurchaseOrder.DoesNotExist, PurchaseOrderLine.DoesNotExist) as exc: errors.append({"row": number, "message": str(exc) or "Invalid row"})
        return Response({"accepted_rows": accepted, "rejected_rows": len(errors), "errors": errors}, status=200 if not errors else 207)
