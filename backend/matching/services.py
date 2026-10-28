from decimal import Decimal
from difflib import SequenceMatcher
import re
from django.db import transaction
from invoices.models import Invoice, DuplicateCheck
from .models import MatchResult
from exceptions_app.models import InvoiceException
from audit.models import AuditLog
from vendors.models import VendorAlias
from .models import MatchingSetting

BLOCKING = {"DUPLICATE_INVOICE", "QTY_OVER_INVOICE", "RATE_VARIANCE", "MISSING_PO", "MISSING_GRN", "TAX_MISMATCH", "VENDOR_NOT_APPROVED", "MANUAL_REVIEW", "SERVICE_NOT_ACCEPTED"}

@transaction.atomic
def run_matching(invoice: Invoice, actor=None):
    from invoices.policies import ensure_invoice_editable
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk, tenant_id=invoice.tenant_id)
    ensure_invoice_editable(locked)
    invoice.refresh_from_db()
    tenant = invoice.tenant
    setting = MatchingSetting.objects.filter(tenant=tenant).first()
    run_number = (invoice.match_results.order_by("-run_number").values_list("run_number", flat=True).first() or 0) + 1
    codes, details = [], {"lines": [], "rules_version": "1"}
    vendor = invoice.vendor
    match_method = ""
    priorities = setting.matching_priority if setting and setting.matching_priority else ["GSTIN", "NAME", "ALIAS", "EMAIL_DOMAIN"]
    sender_domain = str(invoice.source_email.get("sender", "")).rsplit("@", 1)[-1].strip().casefold()
    for signal in priorities:
        if vendor: break
        if signal == "GSTIN" and invoice.supplier_gstin:
            vendor = tenant.vendor_set.filter(gstin__iexact=invoice.supplier_gstin.strip()).first()
        elif signal == "NAME" and invoice.supplier_name:
            vendor = tenant.vendor_set.filter(name__iexact=invoice.supplier_name.strip()).first()
        elif signal == "ALIAS" and invoice.supplier_name:
            alias = VendorAlias.objects.filter(tenant=tenant, normalized_alias=invoice.supplier_name.strip().casefold(), kind=VendorAlias.Kind.NAME).select_related("vendor").first()
            vendor = alias.vendor if alias else None
        elif signal == "EMAIL_DOMAIN" and sender_domain:
            alias = VendorAlias.objects.filter(tenant=tenant, normalized_alias=sender_domain, kind=VendorAlias.Kind.EMAIL_DOMAIN).select_related("vendor").first()
            vendor = alias.vendor if alias else next((candidate for candidate in tenant.vendor_set.all() if sender_domain in [str(d).strip().casefold().lstrip("@") for d in candidate.email_domains]), None)
        if vendor: match_method = signal
    if vendor and invoice.vendor_id is None:
        invoice.vendor = vendor
        invoice.vendor_match_method = match_method or "MANUAL"
        invoice.vendor_match_confidence = Decimal("1.0000") if match_method == "GSTIN" else Decimal("0.9500") if match_method == "NAME" else Decimal("0.9000") if match_method == "ALIAS" else Decimal("0.8500") if match_method == "EMAIL_DOMAIN" else None
        invoice.save(update_fields=["vendor", "vendor_match_method", "vendor_match_confidence", "updated_at"])
    normalized_number = re.sub(r"[^a-z0-9]", "", (invoice.invoice_number or "").casefold())
    if vendor: candidates = Invoice.objects.filter(tenant=tenant, vendor=vendor).exclude(id=invoice.id)
    elif invoice.supplier_gstin: candidates = Invoice.objects.filter(tenant=tenant, supplier_gstin__iexact=invoice.supplier_gstin).exclude(id=invoice.id)
    elif invoice.supplier_name: candidates = Invoice.objects.filter(tenant=tenant, supplier_name__iexact=invoice.supplier_name).exclude(id=invoice.id)
    else: candidates = Invoice.objects.none()
    duplicate_match = False
    if normalized_number:
        for candidate in candidates.exclude(invoice_number="").order_by("-created_at")[:500]:
            candidate_number = re.sub(r"[^a-z0-9]", "", candidate.invoice_number.casefold())
            similarity = SequenceMatcher(None, normalized_number, candidate_number).ratio()
            exact = normalized_number == candidate_number
            same_amount = invoice.invoice_total == candidate.invoice_total
            near_amount = invoice.invoice_total > 0 and candidate.invoice_total > 0 and abs(invoice.invoice_total - candidate.invoice_total) <= max(abs(invoice.invoice_total), abs(candidate.invoice_total)) * Decimal("0.05")
            if exact or (similarity >= 0.82 and near_amount):
                kind = DuplicateCheck.Kind.EXACT if exact else DuplicateCheck.Kind.NEAR
                prior = DuplicateCheck.objects.filter(tenant=tenant, invoice=invoice, candidate_invoice=candidate, kind=kind).first()
                if prior and prior.decision == DuplicateCheck.Decision.NOT_DUPLICATE:
                    continue
                score = Decimal("0.99") if exact and same_amount else Decimal("0.92") if exact else Decimal(str(round(similarity * 0.75 + (0.25 if near_amount else 0), 4)))
                DuplicateCheck.objects.get_or_create(tenant=tenant, invoice=invoice, candidate_invoice=candidate, kind=kind,
                    defaults={"score": score, "reasons": ["Invoice number matches" if exact else f"Invoice number similarity {similarity:.0%}", "Invoice totals are within 5%" if near_amount else "Invoice total differs"]})
                duplicate_match = True
    duplicate_file = False
    if invoice.document and invoice.document.checksum_sha256:
        matching_docs = invoice.document.__class__.objects.filter(tenant=tenant, checksum_sha256=invoice.document.checksum_sha256).exclude(id=invoice.document_id)
        for doc in matching_docs:
            candidate = Invoice.objects.filter(tenant=tenant, document=doc).first()
            if not candidate: continue
            prior = DuplicateCheck.objects.filter(tenant=tenant, invoice=invoice, candidate_invoice=candidate, kind=DuplicateCheck.Kind.FILE).first()
            if prior and prior.decision == DuplicateCheck.Decision.NOT_DUPLICATE: continue
            DuplicateCheck.objects.get_or_create(tenant=tenant, invoice=invoice, candidate_invoice=candidate, kind=DuplicateCheck.Kind.FILE,
                defaults={"score": Decimal("1"), "reasons": ["Identical SHA-256 document checksum"]})
            duplicate_file = True
    if duplicate_file or duplicate_match: codes.append("DUPLICATE_INVOICE")
    if not vendor or not vendor.approved: codes.append("VENDOR_NOT_APPROVED")
    if not invoice.lines.exists():
        codes.append("MANUAL_REVIEW")
        details["lines"].append({"reason": "Invoice has no reviewed line items"})
    if not invoice.po_number: codes.append("MISSING_PO")
    else:
        po = tenant.purchaseorder_set.filter(number=invoice.po_number, vendor=vendor).prefetch_related("lines", "grn_set__lines").first()
        if not po: codes.append("MISSING_PO")
        else:
            grns = list(po.grn_set.all())
            if setting and setting.require_service_acceptance and invoice.category.strip().upper() in {"SERVICE", "SERVICES"} and not any(grn.service_accepted for grn in grns):
                codes.append("SERVICE_NOT_ACCEPTED")
                details["service_acceptance"] = {"required": True, "accepted": False}
            for line in invoice.lines.all():
                candidates = list(po.lines.all())
                if line.item_code: candidates = [p for p in candidates if p.item_code.strip().casefold() == line.item_code.strip().casefold()]
                else: candidates = [p for p in candidates if p.description.strip().casefold() == line.description.strip().casefold()]
                if len(candidates) != 1:
                    codes.append("MANUAL_REVIEW"); details["lines"].append({"line_id": str(line.id), "reason": "PO line is missing or ambiguous"}); continue
                po_line = candidates[0]
                received = sum((gl.quantity_received for grn in grns for gl in grn.lines.all() if gl.purchase_order_line_id == po_line.id), Decimal("0"))
                variance = abs(line.rate - po_line.rate) / max(abs(po_line.rate), Decimal("0.000001"))
                line_codes = []
                if received <= 0: line_codes.append("MISSING_GRN")
                quantity_tolerance = setting.quantity_tolerance_amount if setting else Decimal("0")
                if setting and setting.quantity_tolerance_percent:
                    quantity_tolerance = max(quantity_tolerance, abs(po_line.quantity) * setting.quantity_tolerance_percent / Decimal("100"))
                if line.quantity > po_line.quantity + quantity_tolerance: line_codes.append("QTY_OVER_INVOICE")
                if received > 0 and line.quantity > received + quantity_tolerance: line_codes.append("QTY_OVER_INVOICE")
                if received < po_line.quantity: line_codes.append("PARTIAL_DELIVERY")
                tolerance_pct = setting.rate_tolerance_percent if setting else Decimal(str(tenant.settings.get("rate_tolerance_percent", 0)))
                tolerance_amt = setting.rate_tolerance_amount if setting else Decimal("0")
                if variance > tolerance_pct / Decimal("100") and abs(line.rate - po_line.rate) > tolerance_amt: line_codes.append("RATE_VARIANCE")
                tax_tolerance = (setting.tax_tolerance_percent if setting else Decimal(str(tenant.settings.get("tax_tolerance_percent", 0)))) / Decimal("100")
                if abs(line.gst_rate - po_line.gst_rate) / max(abs(po_line.gst_rate), Decimal("0.000001")) > tax_tolerance: line_codes.append("TAX_MISMATCH")
                if line.tds_amount: line_codes.append("TDS_REVIEW")
                codes.extend(line_codes)
                details["lines"].append({"line_id": str(line.id), "po_line_id": str(po_line.id), "received_quantity": str(received), "rate_variance": str(variance), "exceptions": line_codes})
    result = MatchResult.objects.create(tenant=tenant, invoice=invoice, run_number=run_number, outcome="EXCEPTION" if codes else "MATCHED", details=details)
    current_codes = set(codes)
    stale = invoice.exceptions.filter(status__in=["OPEN", "ASSIGNED"]).exclude(code__in=current_codes)
    for exception in stale:
        exception.status = "RESOLVED"; exception.resolution_note = f"Cleared by matching run {run_number}"; exception.save(update_fields=["status", "resolution_note"])
        AuditLog.objects.create(tenant=tenant, actor=actor, action="EXCEPTION_AUTO_CLEARED", object_type="Exception", object_id=str(exception.id), metadata={"matching_run": run_number})
    for code in sorted(current_codes):
        if invoice.exceptions.filter(code=code, status__in=["OPEN", "ASSIGNED"]).exists(): continue
        blocking = code in BLOCKING or (code == "PARTIAL_DELIVERY" and setting is not None and not setting.allow_partial_grn)
        InvoiceException.objects.create(tenant=tenant, invoice=invoice, match_result=result, code=code, blocking=blocking, severity="HIGH" if blocking else "MEDIUM", details=details)
    has_blocking = any(c in BLOCKING for c in codes) or ("PARTIAL_DELIVERY" in codes and setting is not None and not setting.allow_partial_grn)
    invoice.status = Invoice.Status.EXCEPTION if has_blocking else Invoice.Status.MATCHED
    invoice.save(update_fields=["status", "updated_at"])
    AuditLog.objects.create(tenant=tenant, actor=actor, action="MATCH_RUN", object_type="Invoice", object_id=str(invoice.id), metadata={"run_number": run_number, "exceptions": sorted(set(codes))})
    return result
