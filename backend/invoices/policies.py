from rest_framework.exceptions import APIException


class InvoiceStateConflict(APIException):
    status_code = 409
    default_code = "STATE_CONFLICT"
    default_detail = "This invoice cannot be changed in its current financial state."


def ensure_invoice_editable(invoice):
    if (invoice.financial_locked_at or invoice.status in {"APPROVED", "PAYMENT_READY", "EXPORTED", "APPROVAL_PENDING"}
            or invoice.payment_status != "UNPAID" or invoice.payment_allocations.exists()):
        raise InvoiceStateConflict("Approved, exported or payment-linked invoices are locked. Use an audited correction or reversal.")
