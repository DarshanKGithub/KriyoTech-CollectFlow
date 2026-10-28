from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from matching.models import MatchingSetting
from .models import GRNLine, PurchaseOrderRevision


QUANTITY_STEP = Decimal("0.000001")


def receipt_balance(po_line, *, excluding_grn_line_id=None):
    received_query = GRNLine.objects.filter(tenant_id=po_line.tenant_id, purchase_order_line=po_line)
    if excluding_grn_line_id:
        received_query = received_query.exclude(id=excluding_grn_line_id)
    received = received_query.aggregate(total=Sum("quantity_received"))["total"] or Decimal("0")
    settings = MatchingSetting.objects.filter(tenant_id=po_line.tenant_id).only("over_receipt_tolerance_percent").first()
    tolerance = settings.over_receipt_tolerance_percent if settings else Decimal("0")
    maximum = (po_line.quantity * (Decimal("1") + tolerance / Decimal("100"))).quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)
    return {"ordered": po_line.quantity, "received": received, "remaining": max(Decimal("0"), po_line.quantity - received),
        "maximum_receivable": maximum, "remaining_receivable": max(Decimal("0"), maximum - received)}


def purchase_order_snapshot(purchase_order):
    return {
        "number": purchase_order.number,
        "vendor_id": str(purchase_order.vendor_id),
        "vendor_name": purchase_order.vendor.name,
        "order_date": purchase_order.order_date.isoformat() if purchase_order.order_date else None,
        "status": purchase_order.status,
        "lines": [{
            "line_no": line.line_no,
            "item_code": line.item_code,
            "description": line.description,
            "hsn_sac": line.hsn_sac,
            "quantity": str(line.quantity),
            "uom": line.uom,
            "rate": str(line.rate),
            "taxable_value": str(line.taxable_value),
            "gst_rate": str(line.gst_rate),
        } for line in purchase_order.lines.order_by("line_no")],
    }


def record_purchase_order_revision(purchase_order, *, user=None, action="EDITED", change_note=""):
    return PurchaseOrderRevision.objects.create(
        tenant_id=purchase_order.tenant_id,
        purchase_order=purchase_order,
        revision=purchase_order.revision,
        action=action,
        change_note=change_note[:500],
        snapshot=purchase_order_snapshot(purchase_order),
        changed_by=user,
    )
