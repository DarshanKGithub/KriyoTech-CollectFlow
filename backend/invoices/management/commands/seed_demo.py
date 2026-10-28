from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from tenants.models import Tenant
from accounts.models import User, Membership
from vendors.models import Vendor
from procurement.models import PurchaseOrder, PurchaseOrderLine, GRN, GRNLine
from invoices.models import Invoice, InvoiceLine
from exceptions_app.models import InvoiceException

class Command(BaseCommand):
    help = "Create a repeatable synthetic KriyoPay pilot workspace"
    def handle(self, *args, **options):
        tenant, _ = Tenant.objects.get_or_create(workspace_key="kriyo-demo", defaults={"name": "Kriyo Components Demo"})
        user, created = User.objects.get_or_create(email="owner@kriyopay.demo", defaults={"username": "owner@kriyopay.demo", "first_name": "Demo Owner"})
        if created: user.set_password("ChangeMe123!"); user.save()
        Membership.objects.get_or_create(tenant=tenant, user=user, defaults={"role": "OWNER"})
        vendor_names = ["Aarav Industrial Supplies", "Shree Ganesh Metals", "Precision Parts Co.", "Mehta Packaging Works", "National Bearings Ltd."]
        vendors = []
        for i, name in enumerate(vendor_names, 1):
            vendor, _ = Vendor.objects.get_or_create(tenant=tenant, external_code=f"V{i:02}", defaults={"name": name, "gstin": f"27ABCDE1234F{i}Z1", "approved": i != 5})
            vendors.append(vendor)
        orders, grns = [], []
        for i in range(10):
            vendor = vendors[i % len(vendors)]
            po, _ = PurchaseOrder.objects.get_or_create(tenant=tenant, number=f"PO-DEMO-{i+1:03}", defaults={"vendor": vendor, "order_date": date.today()-timedelta(days=25-i)})
            line, _ = PurchaseOrderLine.objects.get_or_create(tenant=tenant, purchase_order=po, line_no=1, defaults={"item_code": f"ITEM-{i+1:03}", "description": f"Industrial component {i+1}", "quantity": Decimal("100"), "uom": "EA", "rate": Decimal("1000.00"), "taxable_value": Decimal("100000.00"), "gst_rate": Decimal("18")})
            grn, _ = GRN.objects.get_or_create(tenant=tenant, number=f"GRN-DEMO-{i+1:03}", defaults={"vendor": vendor, "purchase_order": po, "received_at": date.today()-timedelta(days=14-i)})
            GRNLine.objects.get_or_create(tenant=tenant, grn=grn, purchase_order_line=line, defaults={"item_code": line.item_code, "description": line.description, "quantity_received": Decimal("100") if i != 8 else Decimal("35"), "uom": "EA"})
            orders.append((po, line)); grns.append(grn)
        statuses = [Invoice.Status.MATCHED, Invoice.Status.EXCEPTION, Invoice.Status.REVIEW_REQUIRED, Invoice.Status.APPROVAL_PENDING, Invoice.Status.APPROVED]
        for i in range(20):
            po, po_line = orders[i % 10]
            number = "INV-DUP-001" if i in (0, 19) else f"INV-DEMO-{i+1:03}"
            invoice, created = Invoice.objects.get_or_create(tenant=tenant, invoice_number=number, vendor=po.vendor, defaults={"po_number": po.number, "invoice_date": date.today()-timedelta(days=i), "status": statuses[i % len(statuses)], "taxable_total": Decimal("100000.00"), "gst_total": Decimal("18000.00"), "invoice_total": Decimal("118000.00"), "uploaded_by": user})
            if created: InvoiceLine.objects.create(tenant=tenant, invoice=invoice, line_no=1, item_code=po_line.item_code, description=po_line.description, quantity=Decimal("100" if i != 8 else "50"), uom="EA", rate=Decimal("1124.00" if i == 6 else "1000.00"), taxable_value=Decimal("100000.00"), gst_rate=Decimal("18"), gst_amount=Decimal("18000.00"))
            if i in {1, 6, 8, 11, 14, 17, 19}:
                code = "RATE_VARIANCE" if i == 6 else "MISSING_GRN" if i == 8 else "DUPLICATE_INVOICE" if i == 19 else ["TAX_MISMATCH", "QTY_OVER_INVOICE", "VENDOR_NOT_APPROVED", "MANUAL_REVIEW"][([1,11,14,17].index(i))]
                InvoiceException.objects.get_or_create(tenant=tenant, invoice=invoice, code=code, defaults={"details": {"seeded": True}})
        self.stdout.write(self.style.SUCCESS("Demo tenant ready. Login: owner@kriyopay.demo / ChangeMe123! (change before shared use). 5 vendors, 10 POs, 10 GRNs, 20 invoices."))
