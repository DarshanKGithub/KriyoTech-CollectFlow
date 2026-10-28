from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from audit.models import AuditLog
from invoices.models import Invoice, InvoiceLine
from procurement.models import PurchaseOrder, PurchaseOrderLine, GRN, GRNLine
from vendors.models import Vendor
from payments.models import Payment, PaymentAllocation
from .models import ERPRecord
from .security import ERPError

MODELS = {"suppliers": Vendor, "purchase_orders": PurchaseOrder, "receipts": GRN, "invoices": Invoice, "payments": Payment}


def number(value):
    try:
        result = Decimal(str(value or 0))
        if not result.is_finite() or result < 0 or result > Decimal("9999999999999999.99"):
            raise ValueError()
        return result
    except (ValueError, TypeError, InvalidOperation):
        raise ERPError("Enter a valid non-negative amount or quantity.") from None


def date(value):
    try: result = parse_date(str(value or "")[:10])
    except ValueError: result = None
    if not result: raise ERPError("A valid YYYY-MM-DD date is required.")
    return result


def vendor_for(tenant, data):
    vendor = Vendor.objects.filter(tenant=tenant, pk=data.get("vendor_id")).first() if data.get("vendor_id") else None
    if not vendor: raise ERPError("Select or map a supplier from this workspace before importing this document.")
    return vendor


def lines(data):
    source = data.get("lines", [])
    if not isinstance(source, list) or not source or len(source) > 500:
        raise ERPError("Provide between 1 and 500 reviewed document lines.")
    result = []
    for line in source:
        if not isinstance(line, dict): raise ERPError("Invalid document line.")
        description = str(line.get("description", "")).strip()[:255]
        qty, rate = number(line.get("quantity")), number(line.get("rate"))
        taxable = number(line.get("taxable_value", qty*rate))
        gst_rate = number(line.get("gst_rate"))
        if not description or qty <= 0 or gst_rate > 100:
            raise ERPError("Lines need a description, positive quantity and GST rate between 0 and 100.")
        result.append({"description": description, "item_code": str(line.get("item_code", ""))[:100], "quantity": qty, "rate": rate, "taxable_value": taxable, "gst_rate": gst_rate, "gst_amount": number(line.get("gst_amount")), "uom": str(line.get("uom", ""))[:30]})
    return result


def suggest(record):
    """Editable canonical import preview; source data remains separately stored."""
    raw = record.payload
    provider = record.connection.provider
    if record.resource == "suppliers":
        names = {"ERPNEXT": "supplier_name", "ZOHO_BOOKS": "contact_name", "ZOHO_INVENTORY": "contact_name", "DYNAMICS_FINANCE": "VendorOrganizationName", "TALLY": "NAME"}
        return {"name": raw.get(names[provider], ""), "gstin": raw.get("gstin") or raw.get("gst_no") or raw.get("PARTYGSTIN", ""), "contact_email": raw.get("email") or raw.get("email_id") or raw.get("EMAIL", ""), "external_code": str(raw.get("name") or raw.get("VendorAccountNumber") or record.external_id)[:80]}
    if provider == "ERPNEXT":
        items = raw.get("items", [])
        result = {"vendor_id": "", "number": raw.get("name", ""), "date": raw.get("posting_date") or raw.get("transaction_date", ""), "po_number": raw.get("po_no") or raw.get("purchase_order", ""), "lines": [{"description": row.get("description") or row.get("item_name", ""), "item_code": row.get("item_code", ""), "quantity": row.get("qty", 0), "rate": row.get("rate", 0), "taxable_value": row.get("amount", 0), "gst_rate": 0, "gst_amount": 0, "uom": row.get("uom", "")} for row in items]}
        result.update({"invoice_number": raw.get("bill_no") or raw.get("name", ""), "taxable_total": raw.get("net_total", 0), "gst_total": raw.get("total_taxes_and_charges", 0), "tds_total": 0, "invoice_total": raw.get("grand_total", 0)})
        if record.resource == "payments": result = {"vendor_id": "", "amount": raw.get("paid_amount", 0), "paid_at": raw.get("posting_date", ""), "reference_number": raw.get("reference_no") or raw.get("name", ""), "allocations": [], "source_posted": raw.get("docstatus") == 1}
        return result
    if provider in {"ZOHO_BOOKS", "ZOHO_INVENTORY"}:
        result = {"vendor_id": "", "number": raw.get("bill_number", ""), "invoice_number": raw.get("bill_number", ""), "date": raw.get("date", ""), "po_number": raw.get("purchaseorder_number", ""), "lines": [{"description": row.get("description") or row.get("name", ""), "item_code": row.get("sku", ""), "quantity": row.get("quantity", 0), "rate": row.get("rate", 0), "taxable_value": number(row.get("quantity", 0))*number(row.get("rate", 0)), "gst_rate": row.get("tax_percentage", 0), "gst_amount": 0} for row in raw.get("line_items", [])], "taxable_total": raw.get("sub_total", 0), "gst_total": raw.get("tax_total", 0), "tds_total": raw.get("tds_amount", 0), "invoice_total": raw.get("total", 0)}
        if record.resource == "payments": result = {"vendor_id": "", "amount": raw.get("amount", 0), "paid_at": raw.get("date", ""), "reference_number": raw.get("reference_number", ""), "allocations": [], "source_posted": True}
        if record.resource == "receipts": result["number"] = raw.get("receive_number", "")
        return result
    # Finance extensions and Tally voucher layouts require explicit field mapping.
    return {"vendor_id": "", "number": "", "date": "", "lines": []} if record.resource != "payments" else {"vendor_id": "", "amount": 0, "paid_at": "", "allocations": [], "source_posted": False}


@transaction.atomic
def apply_inbound(record, data, actor):
    record = ERPRecord.objects.select_for_update().select_related("connection__tenant").get(pk=record.pk)
    if record.direction != "INBOUND" or record.local_id:
        raise ERPError("Record is already linked. Review changes in the original record; existing accounting history is not overwritten.")
    tenant = record.connection.tenant
    from tenants.models import Tenant
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    if data.get("local_id"):
        local = MODELS[record.resource].objects.filter(pk=data["local_id"], tenant=tenant).first()
        if not local: raise ERPError("The selected local record does not belong to this workspace.")
        # Linking an already recorded payment must be explicit and does not add
        # allocations or change the balance a second time.
    elif record.resource == "suppliers":
        name = str(data.get("name", "")).strip()
        if not name: raise ERPError("Supplier name is required.")
        gstin = str(data.get("gstin", "")).strip().upper()
        if gstin:
            import re
            if not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]", gstin): raise ERPError("Enter a valid supplier GSTIN or leave it blank for review.")
        if gstin and Vendor.objects.filter(tenant=tenant, gstin=gstin).exists():
            raise ERPError("A supplier with this GSTIN already exists. Link its local_id instead of creating another.")
        local = Vendor.objects.create(tenant=tenant, name=name[:200], gstin=gstin[:15], external_code=str(data.get("external_code", ""))[:80], contact_email=str(data.get("contact_email", ""))[:254], approved=False)
    elif record.resource == "payments":
        if data.get("source_posted") is not True:
            raise ERPError("Only a confirmed posted ERP payment can be recorded locally.")
        vendor = vendor_for(tenant, data)
        amount = number(data.get("amount"))
        allocations = data.get("allocations", [])
        if not isinstance(allocations, list) or not allocations or amount <= 0:
            raise ERPError("A positive payment and explicit invoice allocations are required.")
        grouped = {}
        for entry in allocations:
            key = str(entry.get("invoice_id", ""))
            grouped[key] = grouped.get(key, Decimal(0))+number(entry.get("amount"))
        if sum(grouped.values()) != amount or any(value <= 0 for value in grouped.values()):
            raise ERPError("Payment allocations must be positive and equal the payment amount.")
        invoices = list(Invoice.objects.select_for_update().filter(tenant=tenant, vendor=vendor, pk__in=sorted(grouped)).order_by("pk"))
        if len(invoices) != len(grouped): raise ERPError("All allocations must belong to this workspace and supplier.")
        from payments.services import record_payment, PaymentConflict
        from rest_framework.exceptions import ValidationError
        try:
            local, _ = record_payment(tenant=tenant, actor=actor,
                data={"vendor": vendor, "amount": amount, "paid_at": date(data.get("paid_at")),
                    "reference_number": str(data.get("reference_number", record.external_id))[:120],
                    "mode": "OTHER", "idempotency_key": record.id, "remarks": "Reviewed ERP payment import"},
                allocations=[{"invoice": invoice, "amount": grouped[str(invoice.pk)]} for invoice in invoices])
        except (PaymentConflict, ValidationError) as error:
            raise ERPError(str(error.detail)) from error

    else:
        vendor = vendor_for(tenant, data)
        parsed_lines = lines(data)
        document_date = date(data.get("date"))
        document_number = str(data.get("invoice_number") if record.resource == "invoices" else data.get("number", "")).strip()
        if not document_number or len(document_number) > 100: raise ERPError("A document number of up to 100 characters is required.")
        if record.resource == "purchase_orders":
            if PurchaseOrder.objects.filter(tenant=tenant, number=document_number).exists(): raise ERPError("Purchase order already exists; link its local_id instead.")
            local = PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, number=document_number, order_date=document_date, status="DRAFT")
            for index, line in enumerate(parsed_lines, 1):
                line.pop("gst_amount")
                PurchaseOrderLine.objects.create(tenant=tenant, purchase_order=local, line_no=index, **line)
        elif record.resource == "receipts":
            if GRN.objects.filter(tenant=tenant, number=document_number).exists(): raise ERPError("Receipt already exists; link its local_id instead.")
            po = PurchaseOrder.objects.filter(tenant=tenant, vendor=vendor, pk=data.get("purchase_order_id")).first() if data.get("purchase_order_id") else None
            if data.get("purchase_order_id") and not po: raise ERPError("Purchase order must belong to this supplier and workspace.")
            local = GRN.objects.create(tenant=tenant, vendor=vendor, purchase_order=po, number=document_number, received_at=document_date, quality_status="PENDING")
            for index, line in enumerate(parsed_lines):
                reference = data["lines"][index].get("purchase_order_line_id")
                po_line = PurchaseOrderLine.objects.select_for_update().filter(tenant=tenant, purchase_order=po, pk=reference).first() if reference else None
                if reference and (not po or not po_line): raise ERPError("Receipt line must reference a line on the selected workspace purchase order.")
                if po and not po_line: raise ERPError("Each PO-backed receipt line needs its purchase_order_line_id to enforce received-quantity limits.")
                if po_line:
                    from procurement.services import receipt_balance
                    if line["quantity"] > receipt_balance(po_line)["remaining_receivable"]:
                        raise ERPError("Receipt quantity exceeds the purchase order's remaining receivable quantity.")
                GRNLine.objects.create(tenant=tenant, grn=local, purchase_order_line=po_line, description=line["description"], item_code=line["item_code"], quantity_received=line["quantity"], uom=line["uom"])
        else:
            if Invoice.objects.filter(tenant=tenant, vendor=vendor, invoice_number=document_number).exists(): raise ERPError("Invoice already exists; link its local_id instead.")
            totals = {key: number(data.get(key)) for key in ("taxable_total", "gst_total", "tds_total", "invoice_total")}
            if totals["taxable_total"]+totals["gst_total"]-totals["tds_total"] != totals["invoice_total"]:
                raise ERPError("Invoice taxable amount + GST − TDS must equal the invoice total.")
            if sum(line["taxable_value"] for line in parsed_lines) != totals["taxable_total"]:
                raise ERPError("Line taxable values must equal the invoice taxable total.")
            if sum(line["gst_amount"] for line in parsed_lines) != totals["gst_total"] or totals["invoice_total"] <= 0:
                raise ERPError("Line GST amounts must equal the GST total and the invoice total must be positive.")
            po_number = str(data.get("po_number", "")).strip()[:100]
            local = Invoice.objects.create(tenant=tenant, vendor=vendor, supplier_name=vendor.name, supplier_gstin=vendor.gstin, invoice_number=document_number, invoice_date=document_date, po_number=po_number, status="REVIEW_REQUIRED", source_channel="ERP", uploaded_by=actor, **totals)
            for index, line in enumerate(parsed_lines, 1): InvoiceLine.objects.create(tenant=tenant, invoice=local, line_no=index, **line)
    record.local_id = local.pk
    record.status = "APPLIED"
    record.reviewed_by = actor
    record.reviewed_at = timezone.now()
    record.save(update_fields=["local_id", "status", "reviewed_by", "reviewed_at", "updated_at"])
    AuditLog.objects.create(tenant=tenant, actor=actor, action="ERP_RECORD_APPLIED", object_type=local.__class__.__name__, object_id=str(local.pk), metadata={"connection_id": str(record.connection_id), "resource": record.resource, "external_id": record.external_id})
    # Applying an invoice is an explicit review of the mapped ERP fields. Continue
    # through the same guarded match/approval workflow used for uploaded invoices.
    if record.resource == "invoices" and isinstance(local, Invoice):
        from invoices.automation import queue_invoice_workflow
        queue_invoice_workflow(local, actor=actor, reviewed=True)
    return local


def snapshot(resource, local):
    from django.core.serializers.json import DjangoJSONEncoder
    import json
    data = {field.name: getattr(local, field.attname) for field in local._meta.fields if field.name not in {"document", "uploaded_by", "created_by"}}
    if hasattr(local, "lines"):
        data["lines"] = [{field.name: getattr(line, field.attname) for field in line._meta.fields if field.name not in {"tenant", "invoice", "purchase_order", "grn"}} for line in local.lines.all()]
    if resource == "payments": data["allocations"] = [{"invoice_id": str(row.invoice_id), "amount": str(row.amount)} for row in local.allocations.all()]
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))
