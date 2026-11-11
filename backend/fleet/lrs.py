from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Membership
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .models import FleetTrip, FleetTripManifestItem, LorryReceipt, LorryReceiptSequence, TransportOrder


EDIT_ROLES = {Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.PURCHASE, Membership.Role.FLEET}


class LorryReceiptCreateSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    lr_date = serializers.DateField(required=False)
    consignor_name = serializers.CharField(max_length=180)
    consignor_address = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    consignee_name = serializers.CharField(max_length=180)
    consignee_address = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    goods_description = serializers.CharField(max_length=500)
    package_count = serializers.IntegerField(min_value=1, default=1)
    weight_kg = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, required=False, allow_null=True)
    freight_amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)
    payment_type = serializers.ChoiceField(choices=LorryReceipt.PaymentType.choices, default=LorryReceipt.PaymentType.TO_BE_BILLED)
    eway_bill_number = serializers.CharField(max_length=80, required=False, allow_blank=True)
    invoice_reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    delivery_instructions = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate(self, attrs):
        tenant = self.context["tenant"]
        order = TransportOrder.objects.filter(tenant=tenant, id=attrs["order_id"]).select_related("customer").first()
        if order is None:
            raise serializers.ValidationError({"order_id": "Choose an order in this workspace."})
        if order.status == TransportOrder.Status.CANCELLED:
            raise serializers.ValidationError({"order_id": "A cancelled order cannot receive a lorry receipt."})
        if not attrs["consignor_name"].strip() or not attrs["consignee_name"].strip():
            raise serializers.ValidationError("Consignor and consignee names are required.")
        if not attrs["goods_description"].strip():
            raise serializers.ValidationError({"goods_description": "Enter a description of the goods."})
        attrs["consignor_name"] = attrs["consignor_name"].strip()
        attrs["consignee_name"] = attrs["consignee_name"].strip()
        attrs["goods_description"] = attrs["goods_description"].strip()
        attrs["order"] = order
        attrs.pop("order_id")
        attrs.setdefault("lr_date", timezone.localdate())
        return attrs


def serialize_lorry_receipt(receipt):
    trip = receipt.trip
    return {
        "id": str(receipt.id), "lr_number": receipt.lr_number, "lr_date": receipt.lr_date.isoformat(),
        "status": receipt.status, "order_id": str(receipt.order_id), "order_number": receipt.order.order_number,
        "customer": receipt.customer_name, "origin": receipt.origin, "destination": receipt.destination,
        "trip_id": str(trip.id) if trip else None, "trip_number": receipt.trip_number or None,
        "vehicle": receipt.vehicle_registration or None, "driver": receipt.driver_name or None,
        "consignor_name": receipt.consignor_name, "consignor_address": receipt.consignor_address,
        "consignee_name": receipt.consignee_name, "consignee_address": receipt.consignee_address,
        "goods_description": receipt.goods_description, "package_count": receipt.package_count,
        "weight_kg": str(receipt.weight_kg) if receipt.weight_kg is not None else None,
        "freight_amount": str(receipt.freight_amount), "payment_type": receipt.payment_type,
        "eway_bill_number": receipt.eway_bill_number, "invoice_reference": receipt.invoice_reference,
        "delivery_instructions": receipt.delivery_instructions, "cancellation_reason": receipt.cancellation_reason,
        "created_at": receipt.created_at.isoformat(),
    }


class LorryReceipts(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Lorry receipt access requires workspace operations access."}, status=403)
        rows = LorryReceipt.objects.filter(tenant=request.tenant).select_related(
            "order__customer", "trip__vehicle", "trip__driver",
        ).order_by("-lr_date", "-created_at")
        query = request.query_params.get("search", "").strip()
        if query:
            from django.db.models import Q
            rows = rows.filter(Q(lr_number__icontains=query) | Q(order__order_number__icontains=query)
                | Q(order__customer__name__icontains=query) | Q(consignee_name__icontains=query)
                | Q(consignor_name__icontains=query) | Q(eway_bill_number__icontains=query))
        status = request.query_params.get("status")
        if status in LorryReceipt.Status.values:
            rows = rows.filter(status=status)
        return Response([serialize_lorry_receipt(row) for row in rows[:500]])

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Transport operations edit access is required."}, status=403)
        serializer = LorryReceiptCreateSerializer(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Serialize number allocation per tenant so concurrent issue requests cannot reuse a number.
        from tenants.models import Tenant
        tenant = Tenant.objects.select_for_update().get(pk=request.tenant.pk)
        year = data["lr_date"].year
        sequence, _ = LorryReceiptSequence.objects.get_or_create(tenant=tenant, year=year)
        sequence = LorryReceiptSequence.objects.select_for_update().get(pk=sequence.pk)
        number = sequence.next_number
        sequence.next_number = number + 1
        sequence.save(update_fields=["next_number"])

        order = data.pop("order")
        trip = FleetTrip.objects.filter(tenant=tenant, transport_order=order).select_related("vehicle", "driver").first()
        if trip is None:
            manifest = FleetTripManifestItem.objects.filter(tenant=tenant, order=order).exclude(
                status=FleetTripManifestItem.Status.CANCELLED,
            ).select_related("trip__vehicle", "trip__driver").order_by("created_at").first()
            trip = manifest.trip if manifest else None
        receipt = LorryReceipt.objects.create(
            tenant=tenant, order=order, trip=trip, lr_number=f"LR-{year}-{number:06d}",
            customer_name=order.customer.name, origin=order.origin, destination=order.destination,
            trip_number=trip.trip_number if trip else "",
            vehicle_registration=trip.vehicle.registration_number if trip else "",
            driver_name=trip.driver.name if trip else "",
            created_by=request.user, **data,
        )
        AuditLog.objects.create(tenant=tenant, actor=request.user, action="LORRY_RECEIPT_ISSUED",
            object_type="LorryReceipt", object_id=str(receipt.id), metadata={"lr_number": receipt.lr_number, "order_id": str(order.id)})
        receipt = LorryReceipt.objects.select_related("order__customer", "trip__vehicle", "trip__driver").get(pk=receipt.pk)
        return Response(serialize_lorry_receipt(receipt), status=201)


class LorryReceiptCancel(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, receipt_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Transport operations edit access is required."}, status=403)
        receipt = get_object_or_404(LorryReceipt.objects.select_for_update(), tenant=request.tenant, id=receipt_id)
        if receipt.status == LorryReceipt.Status.CANCELLED:
            return Response({"error": "This lorry receipt is already cancelled."}, status=409)
        reason = str(request.data.get("reason", "")).strip()
        if len(reason) < 3:
            return Response({"error": "Enter a cancellation reason (at least 3 characters)."}, status=400)
        receipt.status = LorryReceipt.Status.CANCELLED
        receipt.cancellation_reason = reason[:300]
        receipt.cancelled_at = timezone.now()
        receipt.cancelled_by = request.user
        receipt.save(update_fields=["status", "cancellation_reason", "cancelled_at", "cancelled_by", "updated_at"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="LORRY_RECEIPT_CANCELLED",
            object_type="LorryReceipt", object_id=str(receipt.id), metadata={"lr_number": receipt.lr_number, "reason": reason[:300]})
        return Response({"id": str(receipt.id), "status": receipt.status, "cancellation_reason": receipt.cancellation_reason})
