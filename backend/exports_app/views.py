from uuid import UUID

from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from vendors.models import Vendor
from .models import TallyLedgerMapping


class TallyMappings(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        rows = TallyLedgerMapping.objects.filter(tenant=request.tenant).order_by("dimension", "source_key")
        return Response([{"id": str(row.id), "dimension": row.dimension, "source_key": row.source_key,
            "ledger_name": row.ledger_name, "active": row.active, "updated_at": row.updated_at} for row in rows])

    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE"):
            return Response({"error": "Finance role required to manage Tally mappings."}, status=403)
        dimension = str(request.data.get("dimension", "")).upper()
        source_key = str(request.data.get("source_key", "")).strip()
        ledger_name = str(request.data.get("ledger_name", "")).strip()
        if dimension not in TallyLedgerMapping.Dimension.values or not source_key or len(source_key) > 120 or not ledger_name or len(ledger_name) > 120:
            return Response({"error": "Choose a supported mapping dimension and enter a source key and Tally name (up to 120 characters)."}, status=400)
        if dimension != TallyLedgerMapping.Dimension.VENDOR_LEDGER:
            source_key = source_key.casefold()
        if dimension == TallyLedgerMapping.Dimension.VOUCHER_TYPE and source_key.lower() != "default":
            return Response({"error": "Voucher type mappings must use the source key 'default'."}, status=400)
        if dimension == TallyLedgerMapping.Dimension.VENDOR_LEDGER:
            try: vendor_id = UUID(source_key)
            except (ValueError, TypeError, AttributeError): return Response({"error": "Vendor ledger source key must be a vendor ID from this workspace."}, status=400)
            if not Vendor.objects.filter(tenant=request.tenant, id=vendor_id).exists():
                return Response({"error": "Vendor ledger mappings must reference a vendor in this workspace."}, status=400)
            source_key = str(vendor_id)
        if dimension == TallyLedgerMapping.Dimension.COST_CENTER and source_key.startswith("vendor:"):
            try: vendor_id = UUID(source_key.removeprefix("vendor:"))
            except (ValueError, TypeError, AttributeError): return Response({"error": "Cost center vendor key must reference a vendor in this workspace."}, status=400)
            if not Vendor.objects.filter(tenant=request.tenant, id=vendor_id).exists():
                return Response({"error": "Cost center mappings must reference a vendor in this workspace."}, status=400)
        if dimension == TallyLedgerMapping.Dimension.GST_LEDGER and source_key.lower() != "default":
            from decimal import Decimal, InvalidOperation
            try: rate = Decimal(source_key)
            except (InvalidOperation, ValueError, TypeError): return Response({"error": "GST mapping key must be a GST rate or default."}, status=400)
            if not rate.is_finite() or not 0 <= rate <= 100: return Response({"error": "GST rate must be between 0 and 100."}, status=400)
            source_key = format(rate.normalize(), "f")
        row, created = TallyLedgerMapping.objects.update_or_create(tenant=request.tenant, dimension=dimension, source_key=source_key,
            defaults={"ledger_name": ledger_name, "active": True, "created_by": request.user})
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="TALLY_MAPPING_SAVED", object_type="TallyLedgerMapping",
            object_id=str(row.id), metadata={"dimension": dimension, "source_key": source_key, "created": created})
        return Response({"id": str(row.id), "dimension": row.dimension, "source_key": row.source_key, "ledger_name": row.ledger_name, "active": row.active}, status=201 if created else 200)

    def patch(self, request, mapping_id):
        if request.membership.role not in ("OWNER", "FINANCE"):
            return Response({"error": "Finance role required to manage Tally mappings."}, status=403)
        row = TallyLedgerMapping.objects.filter(tenant=request.tenant, id=mapping_id).first()
        if not row: return Response({"error": "Tally mapping not found."}, status=404)
        if not request.data or set(request.data) - {"ledger_name", "active"}:
            return Response({"error": "Only ledger_name and active can be updated."}, status=400)
        if "ledger_name" in request.data:
            value = str(request.data["ledger_name"]).strip()
            if not value or len(value) > 120: return Response({"error": "Tally name must be 1 to 120 characters."}, status=400)
            row.ledger_name = value
        if "active" in request.data:
            if not isinstance(request.data["active"], bool): return Response({"error": "active must be a boolean."}, status=400)
            row.active = request.data["active"]
        row.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="TALLY_MAPPING_UPDATED", object_type="TallyLedgerMapping", object_id=str(row.id), metadata={"fields": sorted(request.data)})
        return Response({"id": str(row.id), "dimension": row.dimension, "source_key": row.source_key, "ledger_name": row.ledger_name, "active": row.active})

    def delete(self, request, mapping_id):
        if request.membership.role not in ("OWNER", "FINANCE"):
            return Response({"error": "Finance role required to manage Tally mappings."}, status=403)
        row = TallyLedgerMapping.objects.filter(tenant=request.tenant, id=mapping_id).first()
        if not row: return Response({"error": "Tally mapping not found."}, status=404)
        metadata = {"dimension": row.dimension, "source_key": row.source_key, "ledger_name": row.ledger_name}
        row.delete()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="TALLY_MAPPING_DELETED", object_type="TallyLedgerMapping", object_id=str(mapping_id), metadata=metadata)
        return Response(status=204)
