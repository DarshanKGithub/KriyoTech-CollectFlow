from rest_framework import serializers
from .models import Payment, PaymentAllocation, CreditDebitNote
from invoices.models import Invoice
from vendors.models import Vendor
from decimal import Decimal

class PaymentAllocationSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    class Meta:
        model = PaymentAllocation
        exclude = ["tenant", "payment"]

class PaymentSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default="")
    allocations = PaymentAllocationSerializer(many=True, required=True, allow_empty=False)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    class Meta:
        model = Payment
        exclude = ["tenant", "created_by", "cancelled_at"]
        read_only_fields = ["id", "created_at", "source_account", "currency", "provenance_note"]
        extra_kwargs = {"idempotency_key": {"write_only": True, "required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant = getattr(self.context.get("request"), "tenant", None)
        self.fields["vendor"].queryset = Vendor.objects.filter(tenant=tenant) if tenant else Vendor.objects.none()
        self.fields["allocations"].child.fields["invoice"].queryset = Invoice.objects.filter(tenant=tenant) if tenant else Invoice.objects.none()

class CreditDebitNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditDebitNote
        exclude = ["tenant", "created_by", "approved_by", "approved_at"]
        read_only_fields = ["id", "status", "created_at"]
