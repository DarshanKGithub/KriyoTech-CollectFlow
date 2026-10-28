from decimal import Decimal
from xml.etree import ElementTree as ET
from .models import ERPRecord
from .records import snapshot
from .security import ERPError


def render_mapping(value, context):
    """Resolve explicit field paths only; never evaluate mapping expressions."""
    if isinstance(value, dict): return {key: render_mapping(item, context) for key, item in value.items()}
    if isinstance(value, list): return [render_mapping(item, context) for item in value]
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        current = context
        for key in value[2:-2].strip().split("."):
            if not isinstance(current, dict) or key not in current:
                raise ERPError("A Finance field mapping references an unavailable source field.")
            current = current[key]
        return current
    return value


def linked_id(connection, resource, local_id):
    record = ERPRecord.objects.filter(connection=connection, resource=resource, local_id=local_id,
        status__in=["APPLIED", "SENT", "RECONCILED"]).exclude(external_id="").first()
    if not record: raise ERPError(f"Map or sync the related {resource} record before preparing this document.")
    if connection.provider == "DYNAMICS_FINANCE":
        return record.payload.get("VendorAccountNumber") or record.external_id
    if connection.provider == "TALLY": return record.payload.get("NAME") or record.payload.get("source", {}).get("name") or record.external_id
    return record.external_id


def payload_for(connection, resource, local):
    source = snapshot(resource, local)
    provider = connection.provider
    defaults = dict(connection.config.get("defaults", {}).get(resource, {}))
    if provider == "ZOHO_INVENTORY":
        if resource != "receipts": raise ERPError("Use Zoho Books for supplier and purchase-order export; link those records to the Inventory connection.")
        if not local.purchase_order_id: raise ERPError("Link the local receipt to its purchase order before exporting.")
        order = linked_id(connection, "purchase_orders", local.purchase_order_id)
        items = []
        for line in local.lines.all():
            if not line.purchase_order_line_id: raise ERPError("Each receipt line needs a local purchase-order line reference.")
            remote_line = connection.config.get("receipt_line_map", {}).get(str(line.purchase_order_line_id))
            if not remote_line: raise ERPError("Map each local PO-line UUID to its Zoho Inventory line_item_id in receipt_line_map.")
            items.append({"line_item_id": remote_line, "quantity": float(line.quantity_received)})
        if not items: raise ERPError("Receipt lines are required.")
        return source, {**defaults, "purchaseorder_id": order, "receive_number": local.number, "date": str(local.received_at), "status": "received", "line_items": items}
    if resource == "suppliers":
        if provider == "ERPNEXT": return source, {**defaults, "supplier_name": local.name, "supplier_type": "Company", "supplier_group": defaults.get("supplier_group", "All Supplier Groups")}
        if provider == "ZOHO_BOOKS": return source, {**defaults, "contact_name": local.name, "contact_type": "vendor", "email": local.contact_email}
        if provider == "DYNAMICS_FINANCE": return source, {**defaults, "VendorOrganizationName": local.name, "dataAreaId": connection.config["legal_entity"]}
        return source, {"name": local.name, "parent": defaults.get("parent", "Sundry Creditors")}
    remote_vendor = linked_id(connection, "suppliers", local.vendor_id)
    if provider == "DYNAMICS_FINANCE":
        mapping = connection.config.get("document_maps", {}).get(resource)
        if not isinstance(mapping, dict):
            # This remains an export package, not a falsely successful sync.
            return source, {"legal_entity": connection.config["legal_entity"], "vendor_account": remote_vendor,
                "resource": resource, "document": source, "mapping_required": True}
        context = {"source": source, "vendor_id": remote_vendor, "legal_entity": connection.config["legal_entity"]}
        header = render_mapping(mapping.get("header", {}), context)
        header["dataAreaId"] = connection.config["legal_entity"]
        operations = [{"collection": mapping.get("header_collection", ""), "body": header}]
        if resource in {"invoices", "purchase_orders", "receipts"}:
            if not mapping.get("line") or not source.get("lines"): raise ERPError("Finance documents require both header and line mappings.")
            for index, line in enumerate(source["lines"], 1):
                body = render_mapping(mapping["line"], {**context, "line": line, "line_number": index})
                body["dataAreaId"] = connection.config["legal_entity"]
                operations.append({"collection": mapping.get("line_collection", ""), "body": body})
        return source, {"operations": operations, "external_reference": render_mapping(mapping.get("external_reference", "{{source.id}}"), context)}
    if provider == "TALLY": return source, {"vendor_ledger": remote_vendor, "defaults": defaults}
    if resource == "payments":
        references = [{"invoice": linked_id(connection, "invoices", allocation.invoice_id), "amount": float(allocation.amount)} for allocation in local.allocations.all()]
        if not references: raise ERPError("Payment needs invoice allocations before ERP export.")
        if provider == "ERPNEXT":
            if not defaults.get("paid_from") or not defaults.get("paid_to"): raise ERPError("Map the ERPNext bank and payable accounts in payment defaults.")
            return source, {**defaults, "payment_type": "Pay", "party_type": "Supplier", "party": remote_vendor, "posting_date": str(local.paid_at), "paid_amount": float(local.amount), "received_amount": float(local.amount), "reference_no": local.reference_number or str(local.pk), "reference_date": str(local.paid_at), "references": [{"reference_doctype": "Purchase Invoice", "reference_name": row["invoice"], "allocated_amount": row["amount"]} for row in references]}
        if not defaults.get("account_id"): raise ERPError("Map a Zoho bank/cash account_id in payment defaults.")
        return source, {**defaults, "vendor_id": remote_vendor, "amount": float(local.amount), "date": str(local.paid_at), "payment_mode": "Bank Transfer", "reference_number": local.reference_number or str(local.pk), "bills": [{"bill_id": row["invoice"], "amount_applied": row["amount"]} for row in references]}
    items = []
    receipt_po = None
    if resource == "receipts":
        if not local.purchase_order_id: raise ERPError("Map the receipt to its purchase order before exporting.")
        receipt_po = linked_id(connection, "purchase_orders", local.purchase_order_id)
    for line in local.lines.all():
        quantity = getattr(line, "quantity", None) or getattr(line, "quantity_received", Decimal(0))
        rate = getattr(line, "rate", Decimal(0))
        if resource == "receipts":
            if not line.purchase_order_line_id: raise ERPError("Map each receipt line to its purchase order line before exporting.")
            rate = line.purchase_order_line.rate
        elif getattr(line, "taxable_value", quantity*rate) != (quantity*rate).quantize(Decimal("0.01")):
            raise ERPError("Line discounts or adjustments need a reviewed provider mapping before direct export.")
        if provider == "ERPNEXT":
            item = connection.config.get("item_map", {}).get(line.item_code)
            if not item: raise ERPError("Map each local item code to an ERPNext item code before export.")
            row = {"item_code": item, "description": line.description, "qty": float(quantity), "rate": float(rate), "schedule_date": str(getattr(local, "order_date", None) or getattr(local, "invoice_date", None) or getattr(local, "received_at", None))}
            if resource == "receipts":
                remote_line = connection.config.get("receipt_line_map", {}).get(str(line.purchase_order_line_id))
                if not remote_line: raise ERPError("Map the local purchase order line UUID to its ERPNext PO item row ID in receipt_line_map.")
                row.update({"purchase_order": receipt_po, "purchase_order_item": remote_line})
            items.append(row)
        else:
            if not defaults.get("account_id"): raise ERPError("Map a Zoho expense account_id in document defaults.")
            row = {"description": line.description, "quantity": float(quantity), "rate": float(rate), "account_id": defaults["account_id"]}
            tax_id = connection.config.get("tax_map", {}).get(format(getattr(line, "gst_rate", Decimal(0)).normalize(), "f"))
            if getattr(line, "gst_amount", 0) or getattr(line, "gst_rate", 0):
                if not tax_id: raise ERPError("Map each GST rate to a Zoho tax ID before export.")
                row["tax_id"] = tax_id
            items.append(row)
    if not items: raise ERPError("Document lines are required before export.")
    if resource == "invoices" and local.tds_total:
        raise ERPError("Invoices containing TDS need an accountant-approved withholding mapping; use the review package until it is configured in a provider extension.")
    if provider == "ERPNEXT":
        target = {**defaults, "supplier": remote_vendor, "items": items, "currency": "INR"}
        if resource == "invoices":
            target.update({"bill_no": local.invoice_number, "bill_date": str(local.invoice_date), "posting_date": str(local.invoice_date)})
            if local.gst_total:
                account = defaults.get("tax_account")
                if not account: raise ERPError("Map an ERPNext GST account in invoice defaults.")
                target["taxes"] = [{"charge_type": "Actual", "account_head": account, "tax_amount": float(local.gst_total), "description": "Reviewed invoice GST"}]
        elif resource == "purchase_orders": target["transaction_date"] = str(local.order_date)
        else: target["posting_date"] = str(local.received_at)
        if resource != "invoices":
            tax_total = Decimal(0)
            for line in local.lines.all():
                if resource == "receipts":
                    taxable, gst_rate = line.quantity_received*line.purchase_order_line.rate, line.purchase_order_line.gst_rate
                else:
                    taxable, gst_rate = line.taxable_value, line.gst_rate
                tax_total += (taxable*gst_rate/100).quantize(Decimal("0.01"))
            if tax_total:
                if not defaults.get("tax_account"): raise ERPError("Map the ERPNext GST account in document defaults.")
                target["taxes"] = [{"charge_type": "Actual", "account_head": defaults["tax_account"], "tax_amount": float(tax_total), "description": "Reviewed GST"}]
        target.pop("tax_account", None)
        return source, target
    target = {**defaults, "vendor_id": remote_vendor, "line_items": items}
    target.pop("account_id", None)
    if resource == "invoices":
        if local.gst_total and not any("tax_id" in row for row in items): raise ERPError("Invoice GST must have explicit line tax mappings.")
        target.update({"bill_number": local.invoice_number, "date": str(local.invoice_date)})
    else: target.update({"purchaseorder_number": local.number, "date": str(local.order_date)})
    return source, target


def tally_xml(record):
    if record.resource not in {"suppliers", "invoices", "payments"}:
        raise ERPError("Tally purchase orders and goods receipts need inventory-specific voucher mappings. Use the JSON review package.")
    source = record.payload["source"]
    target = record.payload["target"]
    root = ET.Element("ENVELOPE")
    ET.SubElement(ET.SubElement(root, "HEADER"), "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(ET.SubElement(root, "BODY"), "IMPORTDATA")
    desc = ET.SubElement(body, "REQUESTDESC")
    ET.SubElement(desc, "REPORTNAME").text = "All Masters" if record.resource == "suppliers" else "Vouchers"
    ET.SubElement(ET.SubElement(desc, "STATICVARIABLES"), "SVCURRENTCOMPANY").text = record.connection.config["company"]
    message = ET.SubElement(ET.SubElement(body, "REQUESTDATA"), "TALLYMESSAGE")
    if record.resource == "suppliers":
        ledger = ET.SubElement(message, "LEDGER", {"NAME": target["name"], "ACTION": "Create"})
        ET.SubElement(ledger, "PARENT").text = target["parent"]
        ET.SubElement(ledger, "GUID").text = str(record.id)
    else:
        kind = "Purchase" if record.resource == "invoices" else "Payment"
        voucher = ET.SubElement(message, "VOUCHER", {"VCHTYPE": kind, "ACTION": "Create", "OBJVIEW": "Accounting Voucher View", "REMOTEID": str(record.id)})
        ET.SubElement(voucher, "DATE").text = str(source.get("invoice_date") or source.get("paid_at", "")).replace("-", "")
        ET.SubElement(voucher, "VOUCHERTYPENAME").text = kind
        ET.SubElement(voucher, "VOUCHERNUMBER").text = source.get("invoice_number") or source.get("reference_number") or str(record.id)
        ET.SubElement(voucher, "PARTYLEDGERNAME").text = target["vendor_ledger"]
        ET.SubElement(voucher, "NARRATION").text = "KriyoPay reviewed export " + str(record.id)
        def entry(ledger, amount):
            row = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(row, "LEDGERNAME").text = ledger
            ET.SubElement(row, "ISDEEMEDPOSITIVE").text = "Yes" if amount < 0 else "No"
            ET.SubElement(row, "AMOUNT").text = format(amount, ".2f")
        defaults = target.get("defaults", {})
        if record.resource == "payments":
            if not defaults.get("bank_ledger"): raise ERPError("Configure the Tally bank ledger in payment defaults.")
            entry(target["vendor_ledger"], -Decimal(source["amount"]))
            entry(defaults["bank_ledger"], Decimal(source["amount"]))
        else:
            if not defaults.get("purchase_ledger"): raise ERPError("Configure the Tally purchase ledger in invoice defaults.")
            entry(defaults["purchase_ledger"], -Decimal(source["taxable_total"]))
            if Decimal(source["gst_total"]):
                if not defaults.get("gst_ledger"): raise ERPError("Configure the Tally GST ledger.")
                entry(defaults["gst_ledger"], -Decimal(source["gst_total"]))
            if Decimal(source["tds_total"]):
                if not defaults.get("tds_ledger"): raise ERPError("Configure the Tally TDS ledger.")
                entry(defaults["tds_ledger"], Decimal(source["tds_total"]))
            entry(target["vendor_ledger"], Decimal(source["invoice_total"]))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
