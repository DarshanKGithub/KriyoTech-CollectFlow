import csv
import io
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from invoices.models import Invoice
from audit.models import AuditLog
from .models import ExportJob, TallyLedgerMapping

HEADERS = ["Voucher Type", "Invoice Number", "Invoice Date", "Vendor Ledger", "Purchase Ledger", "GST Ledger", "TDS Ledger", "Cost Center", "Item", "Quantity", "Rate", "Taxable Value", "GST Rate", "GST Amount", "TDS Amount", "Total Debit", "Total Credit"]

@transaction.atomic
def create_tally_csv(tenant, invoices, actor):
    invoices = list(invoices)
    if not invoices: raise ValidationError("Select at least one invoice")
    for invoice in invoices:
        if invoice.tenant_id != tenant.id or invoice.status != Invoice.Status.PAYMENT_READY: raise ValidationError("Only payment-ready invoices from this workspace can be exported")
        if invoice.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists(): raise ValidationError(f"Invoice {invoice.invoice_number} has an open blocking exception")
    invoice_totals = []
    for invoice in invoices:
        taxable = Decimal(str(invoice.taxable_total or 0))
        gst = Decimal(str(invoice.gst_total or 0))
        tds = Decimal(str(invoice.tds_total or 0))
        invoice_total = Decimal(str(invoice.invoice_total or 0))
        expected = taxable + gst
        expected = expected if expected else invoice_total
        net_payable = invoice_total + tds
        if invoice_total and expected != net_payable:
            raise ValidationError(f"Invoice {invoice.invoice_number} totals do not reconcile: gross {expected}, net payable plus TDS {net_payable}")
        invoice_totals.append(expected)
    debit = sum(invoice_totals, Decimal("0")); credit = debit
    mappings = {(row.dimension, row.source_key.casefold()): row.ledger_name for row in TallyLedgerMapping.objects.filter(tenant=tenant, active=True)}
    try:
        from phase3.models import TaxReview
        tds_sections = {str(row.invoice_id): row.tds_section for row in TaxReview.objects.filter(tenant=tenant, invoice_id__in=[invoice.id for invoice in invoices])}
    except (ImportError, AttributeError):
        tds_sections = {}

    def map_name(dimension, key, fallback):
        return mappings.get((dimension, str(key or "").strip().casefold()), fallback)

    out = io.StringIO(newline=""); writer = csv.writer(out); writer.writerow(HEADERS)
    for inv, voucher_total in zip(invoices, invoice_totals):
        vendor_key = str(inv.vendor_id) if inv.vendor_id else ""
        vendor_ledger = map_name("VENDOR_LEDGER", vendor_key, inv.vendor.name if inv.vendor else "")
        purchase_ledger = map_name("PURCHASE_LEDGER", inv.category, map_name("PURCHASE_LEDGER", "default", "Purchases"))
        tds_section = tds_sections.get(str(inv.id), "")
        tds_ledger = map_name("TDS_LEDGER", tds_section, map_name("TDS_LEDGER", "default", "TDS"))
        cost_center_key = f"vendor:{vendor_key}" if vendor_key else ""
        cost_center = map_name("COST_CENTER", cost_center_key, map_name("COST_CENTER", f"category:{inv.category}" if inv.category else "", map_name("COST_CENTER", "default", "")))
        voucher_type = map_name("VOUCHER_TYPE", "default", "Purchase")
        for index, line in enumerate(list(inv.lines.all()) or [None]):
            gst_rate = line.gst_rate if line else None
            gst_key = format(Decimal(gst_rate).normalize(), "f") if gst_rate is not None else "default"
            gst_ledger = map_name("GST_LEDGER", gst_key, map_name("GST_LEDGER", "default", "GST"))
            writer.writerow([voucher_type, inv.invoice_number, inv.invoice_date or "", vendor_ledger, purchase_ledger, gst_ledger, tds_ledger, cost_center,
                line.description if line else "", line.quantity if line else "", line.rate if line else "", line.taxable_value if line else inv.taxable_total, gst_rate or "", line.gst_amount if line else inv.gst_total, line.tds_amount if line else inv.tds_total, voucher_total if index == 0 else "", voucher_total if index == 0 else ""])
        inv.status = Invoice.Status.EXPORTED; inv.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(tenant=tenant, actor=actor, action="EXPORT_GENERATED", object_type="Invoice", object_id=str(inv.id), metadata={"format": "TALLY_CSV", "vendor_ledger": vendor_ledger, "purchase_ledger": purchase_ledger, "tds_ledger": tds_ledger, "cost_center": cost_center})
    job = ExportJob.objects.create(tenant=tenant, requested_by=actor, status="COMPLETED", row_count=len(invoices), debit_total=debit, credit_total=credit)
    return job, out.getvalue()
