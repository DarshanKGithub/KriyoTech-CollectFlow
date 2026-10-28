from django.core.paginator import Paginator
from rest_framework.response import Response
from .records import MODELS
from .security import ERPError
from .views import ERPView


class LocalCandidates(ERPView):
    def get(self, request):
        resource = request.query_params.get("resource")
        if resource not in MODELS: raise ERPError("Choose a supported local resource.")
        rows = MODELS[resource].objects.filter(tenant=request.tenant).order_by("pk")
        if resource == "suppliers": rows = rows.filter(approved=True)
        elif resource == "purchase_orders": rows = rows.filter(status="APPROVED")
        elif resource == "receipts": rows = rows.filter(quality_status__in=["ACCEPTED", "PARTIAL"])
        elif resource == "invoices": rows = rows.filter(status="PAYMENT_READY")
        else: rows = rows.filter(cancelled_at__isnull=True)
        field = {"suppliers": "name", "purchase_orders": "number", "receipts": "number", "invoices": "invoice_number", "payments": "reference_number"}[resource]
        query = request.query_params.get("q", "").strip()
        if query: rows = rows.filter(**{field+"__icontains": query})
        page = Paginator(rows, 50).get_page(request.query_params.get("page", 1))
        return Response({"results": [{"id": str(row.pk), "name": getattr(row, field) or str(row.pk)} for row in page], "page": page.number, "pages": page.paginator.num_pages})
