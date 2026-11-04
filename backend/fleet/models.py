import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from accounts.models import User
from documents.models import Document
from tenants.models import Tenant


class FleetVehicle(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_vehicles")
    registration_number = models.CharField(max_length=24)
    normalized_registration = models.CharField(max_length=24)
    make_model = models.CharField(max_length=120, blank=True)
    vehicle_type = models.CharField(max_length=40, blank=True)
    capacity_unit = models.CharField(max_length=16, blank=True)
    capacity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    expected_km_per_litre = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, help_text="Expected fuel efficiency used for trip alerts")
    ownership_type = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "normalized_registration"], name="uniq_fleet_vehicle_registration")]
        indexes = [models.Index(fields=["tenant", "status", "registration_number"])]


class FleetVehicleDocument(models.Model):
    class Kind(models.TextChoices):
        PUC = "PUC", "PUC certificate"
        INSURANCE = "INSURANCE", "Insurance"
        REGISTRATION = "REGISTRATION", "Registration certificate"
        PERMIT = "PERMIT", "Permit"
        FITNESS = "FITNESS", "Fitness certificate"
        TAX = "TAX", "Road tax"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_vehicle_documents")
    vehicle = models.ForeignKey(FleetVehicle, on_delete=models.CASCADE, related_name="documents")
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="fleet_vehicle_records")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    document_number = models.CharField(max_length=100, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="uploaded_vehicle_documents")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "vehicle", "kind"]), models.Index(fields=["tenant", "expires_on"])]


class FleetMaintenanceRecord(models.Model):
    class Category(models.TextChoices):
        SERVICE = "SERVICE", "Routine service"
        REPAIR = "REPAIR", "Repair"
        TYRE = "TYRE", "Tyres"
        ENGINE = "ENGINE", "Engine"
        BRAKES = "BRAKES", "Brakes"
        ELECTRICAL = "ELECTRICAL", "Electrical"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_maintenance_records")
    vehicle = models.ForeignKey(FleetVehicle, on_delete=models.CASCADE, related_name="maintenance_records")
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.SERVICE)
    failure_code = models.CharField(max_length=64, blank=True)
    breakdown_at = models.DateTimeField(null=True, blank=True)
    returned_to_service_at = models.DateTimeField(null=True, blank=True)
    description = models.CharField(max_length=240)
    service_date = models.DateField()
    odometer_km = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    vendor = models.CharField(max_length=180, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    next_due_odometer_km = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    receipt = models.ForeignKey(Document, null=True, blank=True, on_delete=models.PROTECT, related_name="fleet_maintenance_receipts")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="fleet_maintenance_records_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "vehicle", "service_date"]), models.Index(fields=["tenant", "next_due_date"])]


class FleetDriver(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_drivers")
    name = models.CharField(max_length=160)
    contact_phone = models.CharField(max_length=32, blank=True)
    reference_code = models.CharField(max_length=64, blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_driver_profiles")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "reference_code"], condition=~Q(reference_code=""), name="uniq_fleet_driver_reference")]
        indexes = [models.Index(fields=["tenant", "status", "name"])]


class FleetCustomer(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_customers")
    name = models.CharField(max_length=180)
    contact_name = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    billing_address = models.TextField(blank=True)
    dock_free_minutes = models.PositiveIntegerField(null=True, blank=True)
    detention_rate_per_hour = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "status", "name"])]


class TransportOrder(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ASSIGNED = "ASSIGNED", "Assigned"
        PARTIALLY_ASSIGNED = "PARTIALLY_ASSIGNED", "Partially assigned"
        LOADING = "LOADING", "At pickup"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED", "Partially delivered"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="transport_orders")
    order_number = models.CharField(max_length=64)
    customer = models.ForeignKey(FleetCustomer, on_delete=models.PROTECT, related_name="transport_orders")
    origin = models.CharField(max_length=180)
    destination = models.CharField(max_length=180)
    origin_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    origin_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    destination_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    destination_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_due_at = models.DateTimeField(null=True, blank=True)
    delivery_due_at = models.DateTimeField(null=True, blank=True)
    cargo_description = models.CharField(max_length=240, blank=True)
    required_vehicle_type = models.CharField(max_length=40, blank=True)
    load_quantity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    load_unit = models.CharField(max_length=32, blank=True)
    agreed_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    customer_reference = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="transport_orders_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "order_number"], name="uniq_transport_order_number"),
            models.CheckConstraint(condition=Q(origin_latitude__isnull=True, origin_longitude__isnull=True) | Q(origin_latitude__isnull=False, origin_longitude__isnull=False), name="order_origin_coordinates_pair"),
            models.CheckConstraint(condition=Q(destination_latitude__isnull=True, destination_longitude__isnull=True) | Q(destination_latitude__isnull=False, destination_longitude__isnull=False), name="order_destination_coordinates_pair"),
        ]
        indexes = [models.Index(fields=["tenant", "status", "created_at"]), models.Index(fields=["tenant", "customer", "created_at"])]


class FleetDock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_docks")
    site_name = models.CharField(max_length=160)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    parallel_capacity = models.PositiveSmallIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "site_name", "code"], name="uniq_fleet_dock_code"),
            models.CheckConstraint(condition=models.Q(parallel_capacity__gt=0), name="fleet_dock_capacity_positive"),
        ]
        indexes = [models.Index(fields=["tenant", "active", "site_name"])]


class DockAppointment(models.Model):
    class AppointmentType(models.TextChoices):
        PICKUP = "PICKUP", "Pickup"
        DELIVERY = "DELIVERY", "Delivery"

    class Status(models.TextChoices):
        BOOKED = "BOOKED", "Booked"
        ARRIVED = "ARRIVED", "Arrived"
        LOADING = "LOADING", "Loading / unloading"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No show"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="dock_appointments")
    dock = models.ForeignKey(FleetDock, on_delete=models.PROTECT, related_name="appointments")
    order = models.ForeignKey(TransportOrder, on_delete=models.PROTECT, related_name="dock_appointments")
    appointment_type = models.CharField(max_length=10, choices=AppointmentType.choices, default=AppointmentType.PICKUP)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.BOOKED, db_index=True)
    idempotency_key = models.UUIDField()
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    loading_started_at = models.DateTimeField(null=True, blank=True)
    loading_finished_at = models.DateTimeField(null=True, blank=True)
    delay_reason = models.CharField(max_length=500, blank=True)
    free_minutes_snapshot = models.PositiveIntegerField(null=True, blank=True)
    rate_snapshot = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    detention_revenue = models.OneToOneField("TripRevenueLine", null=True, blank=True, on_delete=models.PROTECT, related_name="detention_appointment")
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="dock_appointments_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="dock_appointment_end_after_start"),
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="uniq_dock_appointment_idempotency"),
            models.UniqueConstraint(fields=["tenant", "order", "appointment_type"],
                condition=models.Q(status__in=["BOOKED", "ARRIVED", "LOADING"]), name="uniq_active_order_dock_appointment"),
        ]
        indexes = [models.Index(fields=["tenant", "status", "starts_at"]), models.Index(fields=["tenant", "dock", "starts_at", "ends_at"])]


class FreightImportBatch(models.Model):
    class Status(models.TextChoices):
        REVIEW = "REVIEW", "Needs review"
        PARTIAL = "PARTIAL", "Partially reconciled"
        COMPLETED = "COMPLETED", "Reconciled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="freight_import_batches")
    filename = models.CharField(max_length=255)
    checksum_sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REVIEW)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "checksum_sha256"], name="uniq_freight_import_checksum")]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]


class FreightImportRow(models.Model):
    class Kind(models.TextChoices):
        REVENUE = "REVENUE", "Freight revenue"
        EXPENSE = "EXPENSE", "Trip expense"

    class Status(models.TextChoices):
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs review"
        RECONCILED = "RECONCILED", "Reconciled"
        IGNORED = "IGNORED", "Ignored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="freight_import_rows")
    batch = models.ForeignKey(FreightImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField(default=dict)
    trip = models.ForeignKey("FleetTrip", null=True, blank=True, on_delete=models.PROTECT, related_name="imported_freight_rows")
    kind = models.CharField(max_length=10, choices=Kind.choices, blank=True)
    category = models.CharField(max_length=20, blank=True)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    is_refund = models.BooleanField(default=False)
    quantity_litres = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fuel_fill_type = models.CharField(max_length=10, choices=[("UNKNOWN", "Fill type not recorded"), ("FULL", "Full tank"), ("PARTIAL", "Partial fill")], default="UNKNOWN")
    odometer_km = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    incurred_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEEDS_REVIEW)
    review_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    created_revenue = models.ForeignKey("TripRevenueLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="import_source_rows")
    created_expense = models.ForeignKey("TripExpenseLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="import_source_rows")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "batch", "row_number"], name="uniq_freight_batch_row")]
        indexes = [models.Index(fields=["tenant", "status", "batch"])]


class FleetLogisticsDocument(models.Model):
    class Kind(models.TextChoices):
        EWAY_BILL = "EWAY_BILL", "E-way bill"
        CONSIGNMENT_NOTE = "CONSIGNMENT_NOTE", "Consignment note"
        PROOF_OF_DELIVERY = "PROOF_OF_DELIVERY", "Proof of delivery"

    class Status(models.TextChoices):
        EXTRACTING = "EXTRACTING", "Extracting"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs review"
        CONFIRMED = "CONFIRMED", "Confirmed"
        FAILED = "FAILED", "Extraction failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_logistics_documents")
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="fleet_logistics_records")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    trip = models.ForeignKey("FleetTrip", null=True, blank=True, on_delete=models.PROTECT, related_name="logistics_documents")
    transport_order = models.ForeignKey(TransportOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="logistics_documents")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EXTRACTING)
    extracted_fields = models.JSONField(default=dict, blank=True)
    confidence = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    confirmed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="confirmed_fleet_documents")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "status", "kind", "created_at"])]


class FleetTrip(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    class LoadState(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Not classified"
        LOADED = "LOADED", "Carrying cargo"
        EMPTY = "EMPTY", "Running empty"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_trips")
    trip_number = models.CharField(max_length=64)
    vehicle = models.ForeignKey(FleetVehicle, on_delete=models.PROTECT, related_name="trips")
    driver = models.ForeignKey(FleetDriver, on_delete=models.PROTECT, related_name="trips")
    transport_order = models.OneToOneField(TransportOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="trip")
    load_state = models.CharField(max_length=10, choices=LoadState.choices, default=LoadState.UNKNOWN)
    customer_reference = models.CharField(max_length=160, blank=True)
    origin = models.CharField(max_length=180, blank=True)
    destination = models.CharField(max_length=180, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    pickup_at = models.DateTimeField(null=True, blank=True)
    loaded_at = models.DateTimeField(null=True, blank=True)
    delivery_at = models.DateTimeField(null=True, blank=True)
    predicted_arrival_at = models.DateTimeField(null=True, blank=True)
    eta_source = models.CharField(max_length=32, blank=True)
    delay_reason = models.CharField(max_length=500, blank=True)
    route_refreshed_at = models.DateTimeField(null=True, blank=True)
    route_attempted_at = models.DateTimeField(null=True, blank=True)
    route_distance_m = models.PositiveIntegerField(null=True, blank=True)
    route_error = models.CharField(max_length=200, blank=True)
    odometer_start = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    odometer_end = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    delivery_proof = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_trip_delivery_proofs")
    delivery_signature_name = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_trips_submitted")
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_trips_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_trips_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "trip_number"], name="uniq_fleet_trip_number")]
        indexes = [models.Index(fields=["tenant", "status", "starts_at"]), models.Index(fields=["tenant", "vehicle", "starts_at"]), models.Index(fields=["tenant", "driver", "starts_at"])]


class FleetTripManifestItem(models.Model):
    """A shipment allocation carried by a trip; quantities may be split across trips."""
    class Status(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_trip_manifest_items")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="manifest_items")
    order = models.ForeignKey(TransportOrder, on_delete=models.PROTECT, related_name="manifest_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    load_unit = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ASSIGNED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["trip", "order"], name="uniq_trip_manifest_order"),
            models.CheckConstraint(condition=Q(quantity__isnull=True) | Q(quantity__gt=0), name="manifest_quantity_positive"),
        ]
        indexes = [models.Index(fields=["tenant", "order", "trip"])]


class FleetTripStop(models.Model):
    class Kind(models.TextChoices):
        PICKUP = "PICKUP", "Pickup"
        DELIVERY = "DELIVERY", "Delivery"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        ARRIVED = "ARRIVED", "Arrived"
        COMPLETED = "COMPLETED", "Completed"
        SKIPPED = "SKIPPED", "Skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_trip_stops")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="stops")
    order = models.ForeignKey(TransportOrder, on_delete=models.PROTECT, related_name="trip_stops")
    sequence = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    address = models.CharField(max_length=240)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)
    service_minutes = models.PositiveSmallIntegerField(default=30)
    planned_at = models.DateTimeField(null=True, blank=True)
    actual_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["trip", "sequence"], name="uniq_trip_stop_sequence"),
            models.CheckConstraint(condition=Q(latitude__isnull=True, longitude__isnull=True) | Q(latitude__isnull=False, longitude__isnull=False), name="trip_stop_coordinates_pair"),
            models.CheckConstraint(condition=Q(window_end__isnull=True) | Q(window_start__isnull=True) | Q(window_end__gte=models.F("window_start")), name="trip_stop_window_valid"),
        ]
        indexes = [models.Index(fields=["tenant", "trip", "sequence"]), models.Index(fields=["tenant", "order", "kind"])]


class FleetDriverSchedule(models.Model):
    class Kind(models.TextChoices):
        SHIFT = "SHIFT", "Available shift"
        LEAVE = "LEAVE", "Leave"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_schedules")
    driver = models.ForeignKey(FleetDriver, on_delete=models.CASCADE, related_name="schedule_entries")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    note = models.CharField(max_length=240, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="fleet_driver_schedules_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="driver_schedule_end_after_start")]
        indexes = [models.Index(fields=["tenant", "driver", "kind", "starts_at", "ends_at"])]


class FleetResourceReservation(models.Model):
    """Confirmed dispatch horizon reservation; protected by locked resource checks."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_resource_reservations")
    trip = models.OneToOneField(FleetTrip, on_delete=models.CASCADE, related_name="dispatch_reservation")
    vehicle = models.ForeignKey(FleetVehicle, on_delete=models.PROTECT, related_name="dispatch_reservations")
    driver = models.ForeignKey(FleetDriver, on_delete=models.PROTECT, related_name="dispatch_reservations")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="resource_reservation_end_after_start")]
        indexes = [models.Index(fields=["tenant", "vehicle", "released_at", "starts_at", "ends_at"]), models.Index(fields=["tenant", "driver", "released_at", "starts_at", "ends_at"])]


class FleetDispatchPlan(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Awaiting confirmation"
        CONFIRMED = "CONFIRMED", "Confirmed"
        EXPIRED = "EXPIRED", "Expired"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_dispatch_plans")
    request_key = models.UUIDField()
    input_fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROPOSED)
    snapshot = models.JSONField(default=dict)
    selected_option = models.JSONField(default=dict, blank=True)
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    confirmed_trip = models.ForeignKey(FleetTrip, null=True, blank=True, on_delete=models.PROTECT, related_name="dispatch_plans_confirmed")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="fleet_dispatch_plans_created")
    confirmed_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="fleet_dispatch_plans_confirmed_by")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "request_key"], name="uniq_fleet_dispatch_request")]
        indexes = [models.Index(fields=["tenant", "status", "expires_at"])]


class FleetDispatchRouteAttempt(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        UPDATED = "UPDATED", "Updated"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_dispatch_route_attempts")
    plan = models.ForeignKey(FleetDispatchPlan, on_delete=models.CASCADE, related_name="route_attempts")
    assignment_index = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=32, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "assignment_index"], name="uniq_dispatch_route_attempt")]
        indexes = [models.Index(fields=["tenant", "requested_at"]), models.Index(fields=["tenant", "status", "requested_at"])]


class ReturnLoadOffer(models.Model):
    class Status(models.TextChoices):
        OFFERED = "OFFERED", "Offer recorded"
        DECLINED = "DECLINED", "Declined"
        BOOKED = "BOOKED", "Booked"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="return_load_offers")
    source_trip = models.ForeignKey(FleetTrip, on_delete=models.PROTECT, related_name="return_load_offers")
    order = models.ForeignKey(TransportOrder, on_delete=models.PROTECT, related_name="return_load_offers")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OFFERED, db_index=True)
    proposed_amount = models.DecimalField(max_digits=18, decimal_places=2)
    accepted_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    offered_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="return_load_offers_recorded")
    accepted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="return_load_offers_accepted")
    accepted_at = models.DateTimeField(null=True, blank=True)
    trip = models.OneToOneField(FleetTrip, null=True, blank=True, on_delete=models.PROTECT, related_name="return_load_booking")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "source_trip", "order"], condition=~Q(status="CANCELLED"), name="uniq_return_load_offer_pair")]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]


class ShipmentAccessLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    trip = models.ForeignKey(FleetTrip, on_delete=models.PROTECT, related_name="shipment_links")
    token_hash = models.CharField(max_length=64, unique=True)
    notify_email = models.EmailField(blank=True)
    notify_phone = models.CharField(max_length=20, blank=True)
    consent_note = models.CharField(max_length=500, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class ShipmentNotice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    link = models.ForeignKey(ShipmentAccessLink, on_delete=models.CASCADE, related_name="notices")
    event_key = models.CharField(max_length=100)
    delivery_key = models.CharField(max_length=64, unique=True)
    channel = models.CharField(max_length=12)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.CharField(max_length=200, blank=True)
    provider_reference = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["link", "event_key", "channel"], name="uniq_shipment_notice_event")]


class FleetTripLocation(models.Model):
    """Latest phone GPS fix for an active trip; location history is not retained."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_trip_locations")
    trip = models.OneToOneField(FleetTrip, on_delete=models.CASCADE, related_name="latest_phone_location")
    reported_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="fleet_trip_locations_reported")
    source_provider = models.CharField(max_length=32, default="PHONE")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    speed_kmh = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    heading_degrees = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now=True)
    client_event_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "client_event_id"], name="uniq_fleet_location_event"),
            models.CheckConstraint(condition=models.Q(latitude__gte=-90, latitude__lte=90), name="fleet_location_latitude_range"),
            models.CheckConstraint(condition=models.Q(longitude__gte=-180, longitude__lte=180), name="fleet_location_longitude_range"),
        ]
        indexes = [models.Index(fields=["tenant", "captured_at"])]


class FleetTripLocationSample(models.Model):
    """Append-only GPS history used for trip playback and audit."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_trip_location_samples")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="location_samples")
    reported_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="fleet_trip_location_samples")
    source_provider = models.CharField(max_length=32, default="PHONE")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    speed_kmh = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    heading_degrees = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    client_event_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "client_event_id"], name="uniq_fleet_location_sample_event"),
            models.CheckConstraint(condition=models.Q(latitude__gte=-90, latitude__lte=90), name="fleet_sample_latitude_range"),
            models.CheckConstraint(condition=models.Q(longitude__gte=-180, longitude__lte=180), name="fleet_sample_longitude_range"),
        ]
        indexes = [models.Index(fields=["tenant", "trip", "captured_at"]) ]


class FleetGpsDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_gps_devices")
    provider = models.CharField(max_length=32)
    device_id = models.CharField(max_length=128)
    vehicle = models.ForeignKey(FleetVehicle, on_delete=models.PROTECT, related_name="gps_devices")
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_gps_devices_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "device_id"], name="uniq_fleet_gps_provider_device")]
        indexes = [models.Index(fields=["tenant", "active", "provider"])]


class FleetGeofence(models.Model):
    class SiteType(models.TextChoices):
        FACTORY = "FACTORY", "Factory"
        WAREHOUSE = "WAREHOUSE", "Warehouse"
        CUSTOMER = "CUSTOMER", "Customer"
        OTHER = "OTHER", "Other"

    class Shape(models.TextChoices):
        CIRCLE = "CIRCLE", "Circle"
        POLYGON = "POLYGON", "Polygon"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_geofences")
    name = models.CharField(max_length=160)
    site_type = models.CharField(max_length=16, choices=SiteType.choices, default=SiteType.OTHER)
    active = models.BooleanField(default=True)
    current_version = models.PositiveIntegerField(default=1)
    dwell_alert_minutes = models.PositiveSmallIntegerField(default=60, help_text="Raise a review case after this many minutes inside; zero disables dwell alerts.")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="fleet_geofences_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="uniq_fleet_geofence_name")]
        indexes = [models.Index(fields=["tenant", "active", "site_type"])]


class FleetGeofenceVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    geofence = models.ForeignKey(FleetGeofence, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    shape = models.CharField(max_length=12, choices=FleetGeofence.Shape.choices)
    geometry = models.JSONField()
    reason = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="fleet_geofence_versions_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["geofence", "version"], name="uniq_fleet_geofence_version")]
        ordering = ["geofence_id", "-version"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Geofence versions are immutable; create a new version instead.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Geofence versions are immutable.")


class FleetGeofenceTripState(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_geofence_trip_states")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="geofence_states")
    geofence = models.ForeignKey(FleetGeofence, on_delete=models.CASCADE, related_name="trip_states")
    version = models.PositiveIntegerField()
    inside = models.BooleanField(null=True, blank=True)
    candidate_inside = models.BooleanField(null=True, blank=True)
    candidate_count = models.PositiveSmallIntegerField(default=0)
    candidate_since = models.DateTimeField(null=True, blank=True)
    last_sample_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "trip", "geofence"], name="uniq_fleet_geofence_trip_state")]
        indexes = [models.Index(fields=["tenant", "trip", "updated_at"])]


class FleetGeofenceEvent(models.Model):
    class EventType(models.TextChoices):
        ARRIVAL = "ARRIVAL", "Arrival"
        DEPARTURE = "DEPARTURE", "Departure"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_geofence_events")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="geofence_events")
    geofence = models.ForeignKey(FleetGeofence, on_delete=models.PROTECT, related_name="events")
    version = models.PositiveIntegerField()
    source_sample = models.ForeignKey(FleetTripLocationSample, on_delete=models.PROTECT, related_name="geofence_events")
    event_type = models.CharField(max_length=12, choices=EventType.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "geofence", "source_sample"], name="uniq_fleet_geofence_event_sample")]
        indexes = [models.Index(fields=["tenant", "occurred_at"]), models.Index(fields=["tenant", "trip", "occurred_at"])]


class FleetStopEpisode(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        INTERRUPTED = "INTERRUPTED", "Interrupted by GPS gap"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_stop_episodes")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="stop_episodes")
    inside_geofence = models.ForeignKey(FleetGeofence, null=True, blank=True, on_delete=models.SET_NULL, related_name="stop_episodes")
    started_at = models.DateTimeField()
    last_sample_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    sample_count = models.PositiveIntegerField(default=1)
    start_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    start_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    exception_case = models.ForeignKey("fleet.FleetExceptionCase", null=True, blank=True, on_delete=models.SET_NULL, related_name="stop_episodes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "trip"], condition=models.Q(ended_at__isnull=True), name="uniq_open_fleet_stop_episode")]
        indexes = [models.Index(fields=["tenant", "started_at"]), models.Index(fields=["tenant", "trip", "status"])]


class FleetGeofenceDwellEpisode(models.Model):
    class EndReason(models.TextChoices):
        DEPARTURE = "DEPARTURE", "Departure"
        GPS_GAP = "GPS_GAP", "GPS gap"
        BOUNDARY_CHANGED = "BOUNDARY_CHANGED", "Boundary changed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_geofence_dwell_episodes")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="geofence_dwell_episodes")
    geofence = models.ForeignKey(FleetGeofence, on_delete=models.PROTECT, related_name="dwell_episodes")
    version = models.PositiveIntegerField()
    started_at = models.DateTimeField()
    last_sample_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=24, choices=EndReason.choices, blank=True)
    sample_count = models.PositiveIntegerField(default=1)
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    exception_case = models.ForeignKey("fleet.FleetExceptionCase", null=True, blank=True, on_delete=models.SET_NULL, related_name="geofence_dwell_episodes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "trip", "geofence"], condition=models.Q(ended_at__isnull=True), name="uniq_open_fleet_geofence_dwell")]
        indexes = [models.Index(fields=["tenant", "started_at"]), models.Index(fields=["tenant", "trip", "geofence", "ended_at"])]


class FleetRouteProviderAttempt(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        UPDATED = "UPDATED", "Updated"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_route_provider_attempts")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="route_provider_attempts")
    provider = models.CharField(max_length=32, default="GOOGLE_ROUTES")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    eta_at = models.DateTimeField(null=True, blank=True)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "requested_at"]), models.Index(fields=["tenant", "trip", "requested_at"]), models.Index(fields=["tenant", "status", "requested_at"])]


class FleetRouteSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_route_snapshots")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="route_snapshots")
    version = models.PositiveIntegerField()
    provider = models.CharField(max_length=32, default="GOOGLE_ROUTES")
    route_fingerprint = models.CharField(max_length=64)
    route_path = models.JSONField()
    distance_m = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()
    destination = models.CharField(max_length=240)
    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["trip", "version"], name="uniq_fleet_route_snapshot_version"),
            models.UniqueConstraint(fields=["trip", "route_fingerprint"], name="uniq_fleet_route_snapshot_fingerprint"),
        ]
        indexes = [models.Index(fields=["tenant", "trip", "version"])]


class FleetRouteDeviationEpisode(models.Model):
    class Status(models.TextChoices):
        CANDIDATE = "CANDIDATE", "Candidate"
        ACTIVE = "ACTIVE", "Confirmed deviation"
        CLOSED = "CLOSED", "Rejoined route"
        INTERRUPTED = "INTERRUPTED", "Interrupted by GPS gap"
        EXEMPTED = "EXEMPTED", "Planned site stop"
        SUPERSEDED = "SUPERSEDED", "Route plan changed"

    class EndReason(models.TextChoices):
        REJOINED = "REJOINED", "Rejoined route"
        GPS_GAP = "GPS_GAP", "GPS gap"
        PLANNED_SITE = "PLANNED_SITE", "Inside planned site"
        ROUTE_UPDATED = "ROUTE_UPDATED", "Route updated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_route_deviation_episodes")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="route_deviation_episodes")
    route_snapshot = models.ForeignKey(FleetRouteSnapshot, on_delete=models.PROTECT, related_name="deviation_episodes")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CANDIDATE)
    end_reason = models.CharField(max_length=20, choices=EndReason.choices, blank=True)
    threshold_m = models.PositiveIntegerField(default=2000)
    candidate_since = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    last_sample_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    candidate_count = models.PositiveSmallIntegerField(default=1)
    sample_count = models.PositiveIntegerField(default=1)
    max_deviation_m = models.PositiveIntegerField(default=0)
    last_deviation_m = models.PositiveIntegerField(default=0)
    first_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    first_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    exception_case = models.ForeignKey("fleet.FleetExceptionCase", null=True, blank=True, on_delete=models.SET_NULL, related_name="route_deviation_episodes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "trip"], condition=models.Q(status__in=["CANDIDATE", "ACTIVE"]), name="uniq_open_fleet_route_deviation")]
        indexes = [models.Index(fields=["tenant", "trip", "status"]), models.Index(fields=["tenant", "candidate_since"])]


class TripRevenueLine(models.Model):
    class ReviewStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_trip_revenue")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="revenue_lines")
    description = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    is_estimated = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)


class TripExpenseLine(models.Model):
    class Category(models.TextChoices):
        FUEL = "FUEL", "Fuel"
        TOLL = "TOLL", "Toll / FASTag"
        LOADING = "LOADING", "Loading / unloading"
        ALLOWANCE = "ALLOWANCE", "Food / allowance"
        PERMIT = "PERMIT", "Permit"
        REPAIR = "REPAIR", "Repair / maintenance"
        PARKING = "PARKING", "Parking"
        COMMISSION = "COMMISSION", "Commission"
        OTHER = "OTHER", "Other"

    class ReviewStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class FuelFillType(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Fill type not recorded"
        FULL = "FULL", "Full tank"
        PARTIAL = "PARTIAL", "Partial fill"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_trip_expenses")
    trip = models.ForeignKey(FleetTrip, on_delete=models.CASCADE, related_name="expense_lines")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    is_refund = models.BooleanField(default=False, help_text="Fuel card or station credit; reduces net fuel spend and is not a new fill.")
    budgeted_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    quantity_litres = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fuel_fill_type = models.CharField(max_length=10, choices=FuelFillType.choices, default=FuelFillType.UNKNOWN)
    odometer_km = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    incurred_at = models.DateField(null=True, blank=True)
    payee = models.CharField(max_length=160, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    paid_by_driver = models.BooleanField(default=False, help_text="Mark expenses paid personally by the driver; approved lines are reimbursable through salary.")
    idempotency_key = models.UUIDField(null=True, blank=True)
    receipt = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_expenses")
    is_estimated = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "idempotency_key"], condition=models.Q(idempotency_key__isnull=False), name="uniq_fleet_expense_idempotency")]
        indexes = [models.Index(fields=["tenant", "status", "category"]), models.Index(fields=["tenant", "trip", "incurred_at"])]


class FleetFuelBudget(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_fuel_budgets")
    vehicle = models.OneToOneField(FleetVehicle, on_delete=models.CASCADE, related_name="fuel_budget")
    monthly_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    trip_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    expected_efficiency_km_per_litre = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "vehicle"], name="uniq_tenant_vehicle_fuel_budget")]


class FleetFollowUp(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        RESOLVED = "RESOLVED", "Resolved"
        WAIVED = "WAIVED", "Waived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_follow_ups")
    trip = models.ForeignKey(FleetTrip, null=True, blank=True, on_delete=models.CASCADE, related_name="follow_ups")
    category = models.CharField(max_length=40)
    description = models.CharField(max_length=240)
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolution_note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_followups_created")
    resolved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="fleet_followups_resolved")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "status", "due_at"])]


class DriverSalaryRecord(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Awaiting approval"
        APPROVED = "APPROVED", "Approved"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"
        SETTLED = "SETTLED", "Settled by advance recovery"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_salaries")
    driver = models.ForeignKey(FleetDriver, on_delete=models.PROTECT, related_name="salary_records")
    period_start = models.DateField(help_text="First day of the salary month")
    settlement_number = models.PositiveSmallIntegerField(default=1)
    salary_amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="driver_salaries_submitted")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="driver_salaries_approved")
    approved_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=240, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "driver", "period_start", "settlement_number"], name="uniq_fleet_driver_salary_settlement")]
        indexes = [models.Index(fields=["tenant", "period_start"]), models.Index(fields=["tenant", "status", "period_start"])]

    @property
    def trip_earnings_amount(self):
        return self.trip_earnings.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def gross_earnings_amount(self):
        return self.salary_amount + self.trip_earnings_amount + self.driver_expense_reimbursement_amount

    @property
    def driver_expense_reimbursement_amount(self):
        return self.expense_settlements.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


class DriverExpenseSettlement(models.Model):
    """Immutable amount snapshot for an approved expense reimbursed to its driver."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_expense_settlements")
    salary_record = models.ForeignKey(DriverSalaryRecord, on_delete=models.PROTECT, related_name="expense_settlements")
    expense = models.OneToOneField(TripExpenseLine, on_delete=models.PROTECT, related_name="driver_settlement")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "salary_record"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Driver expense settlement snapshots are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Driver expense settlement snapshots are immutable.")


class DriverSalaryPayment(models.Model):
    source_account = models.ForeignKey("settlements.SourceAccount", null=True, blank=True, on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, blank=True, default="")
    provenance_note = models.CharField(max_length=500, blank=True)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_salary_payments")
    salary_record = models.ForeignKey(DriverSalaryRecord, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_date = models.DateField(default=timezone.localdate)
    payment_reference = models.CharField(max_length=120, blank=True)
    idempotency_key = models.UUIDField(null=True, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "idempotency_key"], condition=models.Q(idempotency_key__isnull=False), name="uniq_fleet_salary_payment_idempotency")]
        indexes = [models.Index(fields=["tenant", "payment_date"])]


class DriverSalaryAdjustment(models.Model):
    class Kind(models.TextChoices):
        DEDUCTION = "DEDUCTION", "Deduction"
        PAYMENT_REVERSAL = "PAYMENT_REVERSAL", "Payment reversal"

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Awaiting approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_salary_adjustments")
    salary_record = models.ForeignKey(DriverSalaryRecord, on_delete=models.PROTECT, related_name="adjustments")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    category = models.CharField(max_length=60, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reason = models.CharField(max_length=240)
    evidence = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="driver_salary_adjustments")
    original_payment = models.ForeignKey(DriverSalaryPayment, null=True, blank=True, on_delete=models.PROTECT, related_name="reversals")
    adjustment_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="driver_salary_adjustments_submitted")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="driver_salary_adjustments_approved")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=240, blank=True)
    idempotency_key = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "idempotency_key"], condition=Q(idempotency_key__isnull=False), name="uniq_fleet_salary_adjustment_idempotency")]
        indexes = [models.Index(fields=["tenant", "status", "adjustment_date"])]


class DriverAdvance(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED", "Partially recovered"
        RECOVERED = "RECOVERED", "Recovered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_advances")
    driver = models.ForeignKey(FleetDriver, on_delete=models.PROTECT, related_name="advances")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    given_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=120, blank=True)
    idempotency_key = models.UUIDField(null=True, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "idempotency_key"], condition=Q(idempotency_key__isnull=False), name="uniq_fleet_driver_advance_idempotency")]
        indexes = [models.Index(fields=["tenant", "driver", "given_date"])]


class DriverAdvanceRecovery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_advance_recoveries")
    advance = models.ForeignKey(DriverAdvance, on_delete=models.PROTECT, related_name="recoveries")
    salary_record = models.ForeignKey(DriverSalaryRecord, on_delete=models.PROTECT, related_name="advance_recoveries")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    idempotency_key = models.UUIDField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "idempotency_key"], condition=Q(idempotency_key__isnull=False), name="uniq_fleet_advance_recovery_idempotency")]
        indexes = [models.Index(fields=["tenant", "salary_record", "created_at"]), models.Index(fields=["tenant", "advance", "created_at"])]


class DriverPayPolicy(models.Model):
    class Basis(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly salary"
        PER_TRIP = "PER_TRIP", "Per trip"
        PER_KILOMETRE = "PER_KILOMETRE", "Per kilometre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_pay_policies")
    driver = models.ForeignKey(FleetDriver, on_delete=models.PROTECT, related_name="pay_policies")
    basis = models.CharField(max_length=20, choices=Basis.choices)
    rate = models.DecimalField(max_digits=18, decimal_places=2)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "driver", "effective_from"], name="uniq_driver_pay_policy_effective_start")]
        indexes = [models.Index(fields=["tenant", "driver", "effective_from"])]


class DriverTripEarning(models.Model):
    class Basis(models.TextChoices):
        PER_TRIP = "PER_TRIP", "Per trip"
        PER_KILOMETRE = "PER_KILOMETRE", "Per kilometre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_driver_trip_earnings")
    driver = models.ForeignKey(FleetDriver, on_delete=models.PROTECT, related_name="trip_earnings")
    trip = models.OneToOneField(FleetTrip, on_delete=models.PROTECT, related_name="driver_earning")
    policy = models.ForeignKey(DriverPayPolicy, on_delete=models.PROTECT, related_name="earnings")
    salary_record = models.ForeignKey(DriverSalaryRecord, null=True, blank=True, on_delete=models.PROTECT, related_name="trip_earnings")
    basis = models.CharField(max_length=20, choices=Basis.choices)
    trip_date = models.DateField()
    units = models.DecimalField(max_digits=12, decimal_places=2)
    rate_snapshot = models.DecimalField(max_digits=18, decimal_places=2)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "driver", "trip_date"])]


class FleetExceptionCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_exception_cases")
    source_key = models.CharField(max_length=160)
    category = models.CharField(max_length=64)
    evidence = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="OPEN", choices=[("OPEN", "Open"), ("CONFIRMED", "Confirmed"), ("DISMISSED", "Dismissed"), ("RESOLVED", "Resolved")])
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_fleet_exceptions")
    due_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=1000, blank=True)
    public_resolution = models.CharField(max_length=1000, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_fleet_exceptions")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "source_key"], name="uniq_fleet_exception_source")]
        indexes = [models.Index(fields=["tenant", "status", "due_at"])]


class FleetReminderDelivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fleet_reminder_deliveries")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fleet_reminder_deliveries")
    reminder_key = models.CharField(max_length=100)
    reminder_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "recipient", "reminder_key", "reminder_date"], name="uniq_fleet_reminder_delivery")]


class TransportInvoice(models.Model):
    """Customer receivable generated from a completed, evidenced transport trip."""
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="transport_invoices")
    customer = models.ForeignKey(FleetCustomer, on_delete=models.PROTECT, related_name="transport_invoices")
    order = models.OneToOneField(TransportOrder, on_delete=models.PROTECT, related_name="customer_invoice")
    trip = models.ForeignKey(FleetTrip, on_delete=models.PROTECT, related_name="customer_invoices")
    invoice_number = models.CharField(max_length=64)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=240, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="transport_invoices_issued")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="transport_invoices_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "invoice_number"], name="uniq_transport_invoice_number")]
        indexes = [models.Index(fields=["tenant", "status", "due_date"])]


class TransportCollection(models.Model):
    class Method(models.TextChoices):
        BANK = "BANK", "Bank transfer"
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        CHEQUE = "CHEQUE", "Cheque"
        OTHER = "OTHER", "Other"

    source_account = models.ForeignKey("settlements.SourceAccount", null=True, blank=True, on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, blank=True, default="")
    provenance_note = models.CharField(max_length=500, blank=True)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="transport_collections")
    invoice = models.ForeignKey(TransportInvoice, on_delete=models.PROTECT, related_name="collections")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    received_date = models.DateField(default=timezone.localdate)
    method = models.CharField(max_length=12, choices=Method.choices, default=Method.BANK)
    reference = models.CharField(max_length=120, blank=True)
    idempotency_key = models.UUIDField(null=True, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "idempotency_key"], condition=Q(idempotency_key__isnull=False), name="uniq_transport_collection_idempotency")]
        indexes = [models.Index(fields=["tenant", "received_date"])]
