from decimal import Decimal
from datetime import date
from rest_framework import serializers
from django.db.models import Q, Sum

from documents.models import Document
from accounts.models import Membership
from .models import DriverAdvance, DriverAdvanceRecovery, DriverExpenseSettlement, DriverPayPolicy, DriverSalaryAdjustment, DriverSalaryPayment, DriverSalaryRecord, DriverTripEarning, FleetCustomer, FleetDriver, FleetFollowUp, FleetTrip, FleetVehicle, TransportCollection, TransportInvoice, TransportOrder, TripExpenseLine, TripRevenueLine


class FleetVehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FleetVehicle
        fields = ["id", "registration_number", "make_model", "vehicle_type", "capacity_unit", "capacity", "expected_km_per_litre", "ownership_type", "status", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_registration_number(self, value):
        value = " ".join(value.strip().upper().split())
        if not value:
            raise serializers.ValidationError("Registration number is required.")
        return value

    def validate_capacity(self,value):
        if value is not None and value<=0:raise serializers.ValidationError("Capacity must be greater than zero.")
        return value

    def validate_capacity_unit(self,value):
        from .compatibility import canonical_unit
        result=canonical_unit(value)
        if result not in {"","TONNE","KG","CBM","PALLET"}:raise serializers.ValidationError("Choose TONNE, KG, CBM or PALLET.")
        return result

    def validate_vehicle_type(self,value):
        return value.strip().upper()

    def create(self, validated_data):
        validated_data["normalized_registration"] = validated_data["registration_number"].replace(" ", "").replace("-", "")
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "registration_number" in validated_data:
            validated_data["normalized_registration"] = validated_data["registration_number"].replace(" ", "").replace("-", "")
        return super().update(instance, validated_data)


class FleetDriverSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    account_email = serializers.EmailField(source="user.email", read_only=True, default=None)
    class Meta:
        model = FleetDriver
        fields = ["id", "name", "contact_phone", "reference_code", "user_id", "account_email", "status", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_reference_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if "user_id" not in self.initial_data:
            return attrs
        user_id = attrs.pop("user_id", None)
        if user_id is None:
            attrs["user"] = None
            return attrs
        tenant = self.context["tenant"]
        membership = Membership.objects.filter(tenant=tenant, user_id=user_id, is_active=True, role=Membership.Role.DRIVER).first()
        if membership is None:
            raise serializers.ValidationError({"user_id": "Choose an active DRIVER account in this workspace."})
        if FleetDriver.objects.filter(tenant=tenant, user_id=user_id).exclude(id=getattr(self.instance, "id", None)).exists():
            raise serializers.ValidationError({"user_id": "This account is already linked to another driver."})
        attrs["user"] = membership.user
        return attrs


class FleetCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = FleetCustomer
        fields = ["id", "name", "contact_name", "email", "phone", "gstin", "billing_address", "dock_free_minutes", "detention_rate_per_hour", "status", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"dock_free_minutes": {"min_value": 0, "max_value": 1440}, "detention_rate_per_hour": {"min_value": Decimal("0"), "max_value": Decimal("100000")}}

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Customer name is required.")
        return value


class TransportOrderSerializer(serializers.ModelSerializer):
    customer_id = serializers.UUIDField(write_only=True)
    customer = serializers.SerializerMethodField()
    trip_id = serializers.SerializerMethodField()

    class Meta:
        model = TransportOrder
        fields = ["id", "order_number", "customer_id", "customer", "origin", "destination", "pickup_due_at", "delivery_due_at", "cargo_description", "required_vehicle_type", "load_quantity", "load_unit", "agreed_amount", "customer_reference", "status", "notes", "trip_id", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "trip_id", "created_at", "updated_at"]

    def get_customer(self, obj):
        return {"id": str(obj.customer_id), "name": obj.customer.name}

    def get_trip_id(self, obj):
        try:
            return str(obj.trip.id)
        except FleetTrip.DoesNotExist:
            return None

    def validate(self, attrs):
        tenant = self.context["tenant"]
        customer_id = attrs.pop("customer_id", getattr(self.instance, "customer_id", None))
        customer = FleetCustomer.objects.filter(tenant=tenant, id=customer_id, status=FleetCustomer.Status.ACTIVE).first()
        if customer is None:
            raise serializers.ValidationError({"customer_id": "Choose an active customer in this workspace."})
        pickup = attrs.get("pickup_due_at", getattr(self.instance, "pickup_due_at", None))
        delivery = attrs.get("delivery_due_at", getattr(self.instance, "delivery_due_at", None))
        if pickup and delivery and delivery <= pickup:
            raise serializers.ValidationError({"delivery_due_at": "Delivery time must be after pickup time."})
        quantity = attrs.get("load_quantity", getattr(self.instance, "load_quantity", None))
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError({"load_quantity": "Load quantity must be greater than zero."})
        amount = attrs.get("agreed_amount", getattr(self.instance, "agreed_amount", None))
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({"agreed_amount": "Agreed amount must be greater than zero."})
        attrs["customer"] = customer
        attrs["order_number"] = attrs.get("order_number", getattr(self.instance, "order_number", "")).strip().upper()
        attrs["origin"] = attrs.get("origin", getattr(self.instance, "origin", "")).strip()
        attrs["destination"] = attrs.get("destination", getattr(self.instance, "destination", "")).strip()
        if not attrs["order_number"] or not attrs["origin"] or not attrs["destination"]:
            raise serializers.ValidationError("Order number, pickup location, and delivery location are required.")
        return attrs




class TransportInvoiceCreateSerializer(serializers.Serializer):
    trip_id = serializers.UUIDField()
    invoice_number = serializers.CharField(max_length=64, required=False, allow_blank=True)
    invoice_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=240, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get("due_date") and attrs.get("invoice_date") and attrs["due_date"] < attrs["invoice_date"]:
            raise serializers.ValidationError({"due_date": "Due date cannot be before the invoice date."})
        return attrs


class TransportCollectionCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    received_date = serializers.DateField(required=False)
    method = serializers.ChoiceField(choices=TransportCollection.Method.choices, required=False)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    idempotency_key = serializers.UUIDField(required=False)
    notes = serializers.CharField(max_length=240, required=False, allow_blank=True)


class TripRevenueLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripRevenueLine
        fields = ["id", "description", "amount", "is_estimated", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


class TripExpenseLineSerializer(serializers.ModelSerializer):
    receipt_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    receipt_name = serializers.CharField(source="receipt.filename", read_only=True, default=None)

    class Meta:
        model = TripExpenseLine
        fields = ["id", "category", "description", "amount", "budgeted_amount", "quantity_litres", "incurred_at", "payee", "payment_reference", "paid_by_driver", "idempotency_key", "receipt_id", "receipt_name", "is_estimated", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at", "receipt_name"]
        extra_kwargs = {"idempotency_key": {"write_only": True, "required": False}}

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_quantity_litres(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Fuel quantity must be greater than zero litres.")
        return value

    def validate(self, attrs):
        receipt_id = attrs.pop("receipt_id", None)
        if receipt_id:
            tenant = self.context["tenant"]
            receipt = Document.objects.filter(tenant=tenant, id=receipt_id).first()
            if not receipt:
                raise serializers.ValidationError({"receipt_id": "Receipt document not found in this workspace."})
            attrs["receipt"] = receipt
        return attrs


class FleetTripSerializer(serializers.ModelSerializer):
    vehicle_id = serializers.UUIDField(write_only=True)
    driver_id = serializers.UUIDField(write_only=True)
    transport_order_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    vehicle = serializers.SerializerMethodField()
    driver = serializers.SerializerMethodField()
    transport_order = serializers.SerializerMethodField()
    revenue_lines = TripRevenueLineSerializer(many=True, read_only=True)
    expense_lines = TripExpenseLineSerializer(many=True, read_only=True)
    revenue_total = serializers.SerializerMethodField()
    expense_total = serializers.SerializerMethodField()
    margin = serializers.SerializerMethodField()
    driver_earning = serializers.SerializerMethodField()
    eta_error_minutes = serializers.SerializerMethodField()
    delivery_proof_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    delivery_proof_name = serializers.CharField(source="delivery_proof.filename", read_only=True, default=None)

    class Meta:
        model = FleetTrip
        fields = ["id", "trip_number", "vehicle_id", "driver_id", "transport_order_id", "vehicle", "driver", "transport_order", "customer_reference", "origin", "destination", "starts_at", "ends_at", "pickup_at", "loaded_at", "delivery_at", "predicted_arrival_at", "eta_source", "eta_error_minutes", "delay_reason", "odometer_start", "odometer_end", "delivery_proof_id", "delivery_proof_name", "delivery_signature_name", "status", "review_note", "revenue_lines", "expense_lines", "revenue_total", "expense_total", "margin", "driver_earning", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "review_note", "pickup_at", "loaded_at", "delivery_at", "predicted_arrival_at", "eta_source", "eta_error_minutes", "delivery_proof_name", "revenue_lines", "expense_lines", "revenue_total", "expense_total", "margin", "created_at", "updated_at"]

    def get_vehicle(self, obj):
        return {"id": str(obj.vehicle_id), "registration_number": obj.vehicle.registration_number}

    def get_driver(self, obj):
        return {"id": str(obj.driver_id), "name": obj.driver.name}

    def get_transport_order(self, obj):
        try:
            order = obj.transport_order
        except TransportOrder.DoesNotExist:
            return None
        if order is None:
            return None
        return {"id": str(order.id), "order_number": order.order_number, "customer_name": order.customer.name}

    def _totals(self, obj):
        cached = getattr(obj, "_fleet_totals_cache", None)
        if cached is not None:
            return cached
        from django.db.models import Sum
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        if "revenue_lines" in prefetched:
            revenue = sum((line.amount for line in prefetched["revenue_lines"] if line.status == TripRevenueLine.ReviewStatus.APPROVED and not line.is_estimated), Decimal("0.00"))
        else:
            revenue = obj.revenue_lines.filter(status=TripRevenueLine.ReviewStatus.APPROVED, is_estimated=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        if "expense_lines" in prefetched:
            expenses = sum((line.amount for line in prefetched["expense_lines"] if line.status == TripExpenseLine.ReviewStatus.APPROVED and not line.is_estimated), Decimal("0.00"))
        else:
            expenses = obj.expense_lines.filter(status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        obj._fleet_totals_cache = (revenue, expenses)
        return obj._fleet_totals_cache

    def get_revenue_total(self, obj):
        return f"{self._totals(obj)[0]:.2f}"

    def get_expense_total(self, obj):
        return f"{self._totals(obj)[1]:.2f}"

    def get_margin(self, obj):
        revenue, expenses = self._totals(obj)
        return f"{revenue - expenses:.2f}" if obj.status == FleetTrip.Status.APPROVED else None

    def get_driver_earning(self, obj):
        try:
            earning = obj.driver_earning
        except DriverTripEarning.DoesNotExist:
            return None
        return {"amount": f"{earning.amount:.2f}", "basis": earning.get_basis_display(), "units": f"{earning.units:.2f}", "rate": f"{earning.rate_snapshot:.2f}", "trip_date": earning.trip_date.isoformat()}

    def get_eta_error_minutes(self, obj):
        if not obj.predicted_arrival_at or not obj.delivery_at:
            return None
        return round((obj.delivery_at - obj.predicted_arrival_at).total_seconds() / 60, 1)

    def validate(self, attrs):
        tenant = self.context["tenant"]
        vehicle_id = attrs.pop("vehicle_id", getattr(self.instance, "vehicle_id", None))
        driver_id = attrs.pop("driver_id", getattr(self.instance, "driver_id", None))
        vehicle = FleetVehicle.objects.filter(tenant=tenant, id=vehicle_id, status=FleetVehicle.Status.ACTIVE).first()
        driver = FleetDriver.objects.filter(tenant=tenant, id=driver_id, status=FleetDriver.Status.ACTIVE).first()
        if vehicle is None:
            raise serializers.ValidationError({"vehicle_id": "Choose an active truck in this workspace."})
        if driver is None:
            raise serializers.ValidationError({"driver_id": "Choose an active driver in this workspace."})
        odometer_start = attrs.get("odometer_start", getattr(self.instance, "odometer_start", None))
        odometer_end = attrs.get("odometer_end", getattr(self.instance, "odometer_end", None))
        if odometer_start is not None and odometer_end is not None and odometer_end < odometer_start:
            raise serializers.ValidationError({"odometer_end": "Ending odometer cannot be less than starting odometer."})
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "Trip end time must be after its start time."})
        if starts_at and ends_at:
            overlaps = FleetTrip.objects.filter(tenant=tenant, status__in=[FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED], starts_at__lt=ends_at, ends_at__gt=starts_at).filter(Q(vehicle=vehicle) | Q(driver=driver))
            if self.instance:
                overlaps = overlaps.exclude(id=self.instance.id)
            if overlaps.exists():
                raise serializers.ValidationError("The selected truck or driver has an overlapping trip.")
        attrs["vehicle"], attrs["driver"] = vehicle, driver
        order_id = attrs.pop("transport_order_id", getattr(self.instance, "transport_order_id", None))
        current_order_id = getattr(self.instance, "transport_order_id", None)
        if self.instance and order_id != current_order_id:
            raise serializers.ValidationError({"transport_order_id": "A trip’s transport order cannot be changed after the trip is created."})
        if order_id is not None:
            order = TransportOrder.objects.filter(tenant=tenant, id=order_id).select_related("customer").first()
            if order is None:
                raise serializers.ValidationError({"transport_order_id": "Transport order not found in this workspace."})
            if order.status in {TransportOrder.Status.CANCELLED, TransportOrder.Status.DELIVERED} and order_id != current_order_id:
                raise serializers.ValidationError({"transport_order_id": "Choose an open transport order."})
            linked_trip = FleetTrip.objects.filter(transport_order=order).exclude(id=getattr(self.instance, "id", None)).first()
            if linked_trip:
                raise serializers.ValidationError({"transport_order_id": "This transport order is already linked to a trip."})
            from .compatibility import load_compatibility
            fit,reason=load_compatibility(vehicle,order)
            if fit is False:raise serializers.ValidationError({"transport_order_id":reason})
            attrs["transport_order"] = order
            if not attrs.get("customer_reference"):
                attrs["customer_reference"] = order.customer_reference or order.order_number
            if not attrs.get("origin"):
                attrs["origin"] = order.origin
            if not attrs.get("destination"):
                attrs["destination"] = order.destination
        proof_id = attrs.pop("delivery_proof_id", None)
        if proof_id:
            proof = Document.objects.filter(tenant=tenant, id=proof_id).first()
            if not proof:
                raise serializers.ValidationError({"delivery_proof_id": "Proof document not found in this workspace."})
            attrs["delivery_proof"] = proof
        return attrs


class FleetFollowUpSerializer(serializers.ModelSerializer):
    trip_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = FleetFollowUp
        fields = ["id", "trip_id", "category", "description", "due_at", "status", "resolution_note", "created_at", "resolved_at"]
        read_only_fields = ["id", "status", "resolution_note", "created_at", "resolved_at"]

    def validate_trip_id(self, value):
        if value is None:
            return value
        trip = FleetTrip.objects.filter(tenant=self.context["tenant"], id=value).first()
        if trip is None:
            raise serializers.ValidationError("Trip not found in this workspace.")
        return trip

    def create(self, validated_data):
        trip = validated_data.pop("trip_id", None)
        return FleetFollowUp.objects.create(trip=trip, **validated_data)


class DriverSalaryPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverSalaryPayment
        fields = ["id", "amount", "payment_date", "payment_reference", "notes", "idempotency_key", "created_at", "source_account", "currency", "provenance_note"]
        read_only_fields = ["id", "created_at", "source_account", "currency", "provenance_note"]
        extra_kwargs = {"idempotency_key": {"write_only": True, "required": False}}

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Payment must be greater than zero.")
        salary_record = self.context["salary_record"]
        paid = salary_record.payments.aggregate(total=Sum("amount"))["total"] or 0
        recovered = salary_record.advance_recoveries.aggregate(total=Sum("amount"))["total"] or 0
        deducted = salary_record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or 0
        reversed_paid = salary_record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.PAYMENT_REVERSAL, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or 0
        if paid - reversed_paid + recovered + value > salary_record.gross_earnings_amount - deducted:
            raise serializers.ValidationError("Payment cannot be more than the remaining salary balance.")
        return value


class DriverSalaryRecordSerializer(serializers.ModelSerializer):
    driver = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    advance_recovered_amount = serializers.SerializerMethodField()
    net_payable_amount = serializers.SerializerMethodField()
    trip_earnings_amount = serializers.SerializerMethodField()
    driver_expense_reimbursement_amount = serializers.SerializerMethodField()
    driver_expense_reimbursements = serializers.SerializerMethodField()
    gross_earnings_amount = serializers.SerializerMethodField()
    payments = DriverSalaryPaymentSerializer(many=True, read_only=True)
    deductions = serializers.SerializerMethodField()
    adjustments = serializers.SerializerMethodField()
    driver_id = serializers.UUIDField(write_only=True, required=False)
    submitted_by_name = serializers.CharField(source="submitted_by.get_full_name", read_only=True, default="")
    approved_by_name = serializers.CharField(source="approved_by.get_full_name", read_only=True, default="")

    class Meta:
        model = DriverSalaryRecord
        fields = ["id", "driver_id", "driver", "period_start", "settlement_number", "salary_amount", "trip_earnings_amount", "driver_expense_reimbursement_amount", "driver_expense_reimbursements", "gross_earnings_amount", "deductions", "adjustments", "advance_recovered_amount", "net_payable_amount", "paid_amount", "remaining_amount", "status", "submitted_by_name", "submitted_at", "approved_by_name", "approved_at", "review_note", "notes", "payments", "created_at"]
        read_only_fields = ["id", "driver", "settlement_number", "trip_earnings_amount", "gross_earnings_amount", "paid_amount", "remaining_amount", "status", "submitted_by_name", "submitted_at", "approved_by_name", "approved_at", "review_note", "payments", "created_at"]
        extra_kwargs = {"salary_amount": {"required": False}}

    def get_driver(self, obj):
        return {"id": str(obj.driver_id), "name": obj.driver.name}

    def get_paid_amount(self, obj):
        paid = obj.payments.aggregate(total=Sum('amount'))['total'] or 0
        reversed_paid = obj.adjustments.filter(kind=DriverSalaryAdjustment.Kind.PAYMENT_REVERSAL, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum('amount'))['total'] or 0
        return f"{paid - reversed_paid:.2f}"

    def get_remaining_amount(self, obj):
        paid = obj.payments.aggregate(total=Sum("amount"))["total"] or 0
        recovered = obj.advance_recoveries.aggregate(total=Sum("amount"))["total"] or 0
        deducted = obj.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or 0
        reversed_paid = obj.adjustments.filter(kind=DriverSalaryAdjustment.Kind.PAYMENT_REVERSAL, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or 0
        return f"{max(obj.gross_earnings_amount - deducted - paid + reversed_paid - recovered, 0):.2f}"

    def get_deductions(self, obj):
        total = obj.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or 0
        return f"{total:.2f}"

    def get_adjustments(self, obj):
        return [{"id": str(item.id), "kind": item.kind, "category": item.category, "amount": f"{item.amount:.2f}", "reason": item.reason, "adjustment_date": item.adjustment_date.isoformat(), "status": item.status, "review_note": item.review_note, "original_payment_id": str(item.original_payment_id) if item.original_payment_id else None, "evidence_filename": item.evidence.filename if item.evidence_id else ""} for item in obj.adjustments.select_related("evidence", "original_payment", "submitted_by", "approved_by").order_by("-created_at")]

    def get_advance_recovered_amount(self, obj):
        recovered = obj.advance_recoveries.aggregate(total=Sum("amount"))["total"] or 0
        return f"{recovered:.2f}"

    def get_net_payable_amount(self, obj):
        recovered = obj.advance_recoveries.aggregate(total=Sum("amount"))["total"] or 0
        deducted = obj.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or 0
        return f"{max(obj.gross_earnings_amount - recovered - deducted, 0):.2f}"

    def get_trip_earnings_amount(self, obj):
        return f"{obj.trip_earnings_amount:.2f}"

    def get_driver_expense_reimbursement_amount(self, obj):
        return f"{obj.driver_expense_reimbursement_amount:.2f}"

    def get_driver_expense_reimbursements(self, obj):
        return [{"id": str(item.expense_id), "category": item.expense.category,
            "description": item.expense.description, "amount": f"{item.amount:.2f}",
            "trip_number": item.expense.trip.trip_number,
            "receipt": item.expense.receipt.filename if item.expense.receipt_id else None}
            for item in obj.expense_settlements.select_related("expense__trip", "expense__receipt").order_by("created_at")]

    def get_gross_earnings_amount(self, obj):
        return f"{obj.gross_earnings_amount:.2f}"

    def validate_period_start(self, value):
        if value.day != 1:
            raise serializers.ValidationError("Use the first day of the salary month.")
        return value

    def validate_salary_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Monthly salary cannot be negative.")
        return value

    def validate(self, attrs):
        tenant = self.context["tenant"]
        driver_id = attrs.pop("driver_id", getattr(self.instance, "driver_id", None))
        driver = FleetDriver.objects.filter(tenant=tenant, id=driver_id, status=FleetDriver.Status.ACTIVE).first()
        if driver is None:
            raise serializers.ValidationError({"driver_id": "Choose an active driver in this workspace."})
        attrs["driver"] = driver
        period_start = attrs.get("period_start", getattr(self.instance, "period_start", None))
        if period_start and period_start.day != 1:
            raise serializers.ValidationError({"period_start": "Use the first day of the salary month."})
        salary_amount = attrs.get("salary_amount", getattr(self.instance, "salary_amount", None))
        if period_start:
            monthly_policy = DriverPayPolicy.objects.filter(tenant=tenant, driver=driver, basis=DriverPayPolicy.Basis.MONTHLY, effective_from__lte=period_start).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period_start)).first()
            if (salary_amount is None or salary_amount == 0) and monthly_policy:
                salary_amount = monthly_policy.rate
                attrs["salary_amount"] = salary_amount
        if salary_amount is None:
            salary_amount = Decimal("0.00")
        has_trip_earnings = bool(period_start and DriverTripEarning.objects.filter(tenant=tenant, driver=driver, trip_date__year=period_start.year, trip_date__month=period_start.month).exists())
        has_reimbursable_expenses = bool(period_start and TripExpenseLine.objects.filter(tenant=tenant,
            trip__driver=driver, trip__status=FleetTrip.Status.APPROVED, status=TripExpenseLine.ReviewStatus.APPROVED,
            paid_by_driver=True, is_estimated=False, driver_settlement__isnull=True).filter(
                Q(incurred_at__year=period_start.year, incurred_at__month=period_start.month)
                | Q(incurred_at__isnull=True, trip__delivery_at__year=period_start.year,
                    trip__delivery_at__month=period_start.month)).exists())
        if salary_amount == 0 and not has_trip_earnings and not has_reimbursable_expenses:
            raise serializers.ValidationError({"salary_amount": "Enter a monthly salary or ensure approved trip earnings exist for this pay period."})
        if period_start and DriverSalaryRecord.objects.filter(tenant=tenant, driver=driver, period_start=period_start).exclude(id=getattr(self.instance, "id", None)).exists():
            raise serializers.ValidationError("A salary record already exists for this driver and month.")
        if self.instance and self.instance.trip_earnings.exists() and (driver.id != self.instance.driver_id or period_start != self.instance.period_start):
            raise serializers.ValidationError("Driver and month cannot be changed after trip earnings are included in the draft.")
        return attrs

    def _include_unallocated_earnings(self, record):
        DriverTripEarning.objects.filter(
            tenant_id=record.tenant_id, driver_id=record.driver_id,
            trip_date__year=record.period_start.year, trip_date__month=record.period_start.month,
            salary_record__isnull=True,
        ).update(salary_record=record)

    def _include_unallocated_expenses(self, record):
        next_month = date(record.period_start.year + int(record.period_start.month == 12), record.period_start.month % 12 + 1, 1)
        expenses = TripExpenseLine.objects.filter(tenant_id=record.tenant_id, trip__driver_id=record.driver_id,
            trip__status=FleetTrip.Status.APPROVED, status=TripExpenseLine.ReviewStatus.APPROVED,
            paid_by_driver=True, is_estimated=False, driver_settlement__isnull=True).filter(
                Q(incurred_at__gte=record.period_start, incurred_at__lt=next_month)
                | Q(incurred_at__isnull=True, trip__delivery_at__date__gte=record.period_start,
                    trip__delivery_at__date__lt=next_month))
        DriverExpenseSettlement.objects.bulk_create([DriverExpenseSettlement(tenant_id=record.tenant_id,
            salary_record=record, expense=expense, amount=expense.amount) for expense in expenses])

    def create(self, validated_data):
        record = super().create(validated_data)
        self._include_unallocated_earnings(record)
        self._include_unallocated_expenses(record)
        return record

    def update(self, instance, validated_data):
        record = super().update(instance, validated_data)
        self._include_unallocated_earnings(record)
        self._include_unallocated_expenses(record)
        return record


class DriverAdvanceCreateSerializer(serializers.Serializer):
    driver_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    given_date = serializers.DateField(required=False)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    idempotency_key = serializers.UUIDField(required=False)
    notes = serializers.CharField(max_length=240, required=False, allow_blank=True)

    def validate_driver_id(self, value):
        driver = FleetDriver.objects.filter(tenant=self.context["tenant"], id=value, status=FleetDriver.Status.ACTIVE).first()
        if driver is None:
            raise serializers.ValidationError("Choose an active driver in this workspace.")
        return driver


class DriverAdvanceRecoveryCreateSerializer(serializers.Serializer):
    salary_record_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    idempotency_key = serializers.UUIDField(required=False)


class DriverPayPolicySerializer(serializers.ModelSerializer):
    driver_id = serializers.UUIDField(write_only=True)
    driver = serializers.SerializerMethodField()

    class Meta:
        model = DriverPayPolicy
        fields = ["id", "driver_id", "driver", "basis", "rate", "effective_from", "effective_to", "created_at"]
        read_only_fields = ["id", "driver", "created_at"]

    def get_driver(self, obj):
        return {"id": str(obj.driver_id), "name": obj.driver.name}

    def validate(self, attrs):
        tenant = self.context["tenant"]
        driver_id = attrs.pop("driver_id")
        driver = FleetDriver.objects.filter(tenant=tenant, id=driver_id, status=FleetDriver.Status.ACTIVE).first()
        if driver is None:
            raise serializers.ValidationError({"driver_id": "Choose an active driver in this workspace."})
        start, end = attrs["effective_from"], attrs.get("effective_to")
        if end and end < start:
            raise serializers.ValidationError({"effective_to": "End date must be on or after start date."})
        overlaps = DriverPayPolicy.objects.filter(tenant=tenant, driver=driver, effective_from__lte=end or start.max).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
        if overlaps.exists():
            raise serializers.ValidationError("This pay policy overlaps another policy for the driver. Close the earlier policy first.")
        if attrs["rate"] <= 0:
            raise serializers.ValidationError({"rate": "Pay rate must be greater than zero."})
        attrs["driver"] = driver
        return attrs


class DriverSalaryAdjustmentSerializer(serializers.ModelSerializer):
    evidence_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    idempotency_key = serializers.UUIDField(required=False, write_only=True)

    class Meta:
        model = DriverSalaryAdjustment
        fields = ["id", "kind", "category", "amount", "reason", "evidence_id", "original_payment", "adjustment_date", "idempotency_key", "status", "review_note", "created_at"]
        read_only_fields = ["id", "status", "review_note", "created_at", "submitted_by_id", "approved_by_id"]

    def validate(self, attrs):
        tenant = self.context["tenant"]
        record = self.context["salary_record"]
        if attrs["amount"] <= 0:
            raise serializers.ValidationError({"amount": "Amount must be greater than zero."})
        evidence_id = attrs.pop("evidence_id", None)
        if evidence_id:
            evidence = Document.objects.filter(tenant=tenant, id=evidence_id).first()
            if not evidence:
                raise serializers.ValidationError({"evidence_id": "Evidence file was not found in this workspace."})
            attrs["evidence"] = evidence
        if attrs["kind"] == DriverSalaryAdjustment.Kind.DEDUCTION:
            if not attrs.get("category") or not attrs.get("reason"):
                raise serializers.ValidationError("A deduction category and reason are required.")
            if attrs.get("original_payment"):
                raise serializers.ValidationError({"original_payment": "Deductions cannot reference a payment."})
            approved = record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            pending = record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.SUBMITTED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            paid = record.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            recovered = record.advance_recoveries.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            reversed_paid = record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.PAYMENT_REVERSAL, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            if approved + pending + attrs["amount"] > record.gross_earnings_amount - paid + reversed_paid - recovered:
                raise serializers.ValidationError({"amount": "Deduction exceeds the unpaid salary balance."})
        else:
            payment = attrs.get("original_payment")
            if not payment or payment.salary_record_id != record.id:
                raise serializers.ValidationError({"original_payment": "Select a payment from this salary settlement."})
            already = DriverSalaryAdjustment.objects.filter(original_payment=payment, kind=DriverSalaryAdjustment.Kind.PAYMENT_REVERSAL, status__in=[DriverSalaryAdjustment.Status.SUBMITTED, DriverSalaryAdjustment.Status.APPROVED]).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            if already + attrs["amount"] > payment.amount:
                raise serializers.ValidationError({"amount": "Reversal exceeds the un-reversed payment amount."})
            attrs["category"] = "Payment correction"
        return attrs
