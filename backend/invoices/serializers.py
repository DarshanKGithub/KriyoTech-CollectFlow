from rest_framework import serializers
from .models import Invoice, InvoiceLine
from .policies import ensure_invoice_editable
from vendors.models import Vendor
from documents.models import Document

class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        exclude = ["tenant", "invoice", "line_no"]

class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, required=False)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    vendor_phone = serializers.CharField(source="vendor.contact_phone", read_only=True)
    extraction_confidence = serializers.SerializerMethodField()
    class Meta:
        model = Invoice
        exclude = ["tenant"]
        read_only_fields = ["id", "status", "version", "uploaded_by", "created_at", "updated_at", "payment_status", "financial_locked_at", "automation"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant = getattr(self.context.get("request"), "tenant", None)
        self.fields["vendor"].queryset = Vendor.objects.filter(tenant=tenant) if tenant else Vendor.objects.none()
        self.fields["document"].queryset = Document.objects.filter(tenant=tenant) if tenant else Document.objects.none()

    def validate(self, attrs):
        tenant = getattr(self.context.get("request"), "tenant", None)
        for field in ("vendor", "document"):
            value = attrs.get(field)
            if value is not None and (not tenant or value.tenant_id != tenant.pk):
                raise serializers.ValidationError({field: "Choose a record from the current workspace."})
        return attrs
    def latest_extraction(self, instance):
        if hasattr(instance, "_latest_extractions"):
            return next(iter(instance._latest_extractions), None)
        # The same extraction supplies confidence, status and error text.
        # Keep this fallback local to the serializer, including write responses.
        if not hasattr(self, "_extraction_cache"):
            self._extraction_cache = {}
        if instance.pk not in self._extraction_cache:
            self._extraction_cache[instance.pk] = instance.extractions.order_by("-created_at", "-id").first()
        return self._extraction_cache[instance.pk]
    def get_extraction_confidence(self, instance):
        latest = self.latest_extraction(instance)
        return latest.confidence if latest else {}
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.vendor_id and instance.vendor.tenant_id != instance.tenant_id:
            data["vendor"] = data["vendor_name"] = data["vendor_phone"] = None
        if instance.document_id and instance.document.tenant_id != instance.tenant_id:
            data["document"] = None
        if hasattr(instance, "outstanding_balance"):
            data["outstanding_balance"] = format(instance.outstanding_balance, ".2f")
            if not data["vendor"]:
                data["payment_hold"] = "missing_supplier"
            elif not instance.vendor.approved:
                data["payment_hold"] = "unapproved_supplier"
            elif any(item.blocking and item.status not in {"RESOLVED", "OVERRIDDEN"} for item in instance.exceptions.all()):
                data["payment_hold"] = "blocking_exception"
            else:
                data["payment_hold"] = None
        latest = self.latest_extraction(instance)
        data["extraction_status"] = latest.status if latest else None
        warnings = latest.output.get("warnings", []) if latest and isinstance(latest.output, dict) else []
        data["extraction_error"] = " ".join(str(warning) for warning in warnings) if latest and latest.status == "FAILED" else ""
        return data
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        invoice = Invoice.objects.create(tenant=self.context["request"].tenant, uploaded_by=self.context["request"].user, status=Invoice.Status.REVIEW_REQUIRED, **validated_data)
        for idx, line in enumerate(lines, 1): InvoiceLine.objects.create(tenant=invoice.tenant, invoice=invoice, line_no=idx, **line)
        return invoice
    def update(self, instance, validated_data):
        ensure_invoice_editable(instance)
        if "vendor" in validated_data and validated_data["vendor"] != instance.vendor:
            validated_data["vendor_match_method"] = "MANUAL_REVIEW"
            validated_data["vendor_match_confidence"] = None
        lines = validated_data.pop("lines", None)
        for key, value in validated_data.items(): setattr(instance, key, value)
        instance.version += 1; instance.status = Invoice.Status.REVIEW_REQUIRED; instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for idx, line in enumerate(lines, 1): InvoiceLine.objects.create(tenant=instance.tenant, invoice=instance, line_no=idx, **line)
        return instance
