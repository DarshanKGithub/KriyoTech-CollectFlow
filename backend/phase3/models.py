from settlements.storage import FinancialSourceStorage
import uuid
from django.conf import settings
from django.db import models
from tenants.models import Tenant
from invoices.models import Invoice
from payments.models import Payment
from accounts.models import User
from vendors.models import Vendor


class TaxReview(models.Model):
    """Human-reviewable tax data and checks; this is not a statutory determination."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, related_name="tax_reviews", on_delete=models.CASCADE)
    gstin_valid_format = models.BooleanField(null=True, blank=True)
    gst_registration_status = models.CharField(max_length=24, default="NOT_CHECKED", choices=[("NOT_CHECKED", "Not checked"), ("ACTIVE_CONFIRMED", "Active confirmed by reviewer"), ("INACTIVE_CONFIRMED", "Inactive confirmed by reviewer"), ("UNKNOWN", "Unknown")])
    itc_eligible = models.BooleanField(null=True, blank=True)
    itc_block_reason = models.TextField(blank=True)
    einvoice_irn = models.CharField(max_length=100, blank=True)
    tds_section = models.CharField(max_length=24, blank=True)
    tds_rate = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    tds_certificate_reference = models.CharField(max_length=100, blank=True)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "invoice"], name="uniq_tax_review_invoice")]


class BankStatement(models.Model):
    source_account = models.ForeignKey("settlements.SourceAccount", null=True, blank=True, on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, blank=True, default="")
    provenance_note = models.CharField(max_length=500, blank=True)
    is_test_data = models.BooleanField(default=False, db_index=True)
    original_file = models.FileField(upload_to="bank-statements/%Y/%m/", blank=True, storage=FinancialSourceStorage())

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    content_hash = models.CharField(max_length=64)
    imported_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    imported_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "content_hash"], name="uniq_bank_statement_hash")]


class BankTransaction(models.Model):
    class Status(models.TextChoices):
        UNMATCHED = "UNMATCHED"; MATCHED = "MATCHED"; RECONCILED = "RECONCILED"; DUPLICATE = "DUPLICATE"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    statement = models.ForeignKey(BankStatement, related_name="transactions", on_delete=models.CASCADE)
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    fingerprint = models.CharField(max_length=64)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT)
    transport_collection = models.ForeignKey("fleet.TransportCollection", null=True, blank=True, on_delete=models.PROTECT, related_name="bank_transactions")
    driver_salary_payment = models.ForeignKey("fleet.DriverSalaryPayment", null=True, blank=True, on_delete=models.PROTECT, related_name="bank_transactions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UNMATCHED, db_index=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    reconciliation_group = models.ForeignKey("ReconciliationGroup", null=True, blank=True, on_delete=models.PROTECT, related_name="current_bank_rows")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "status", "transaction_date"]), models.Index(fields=["tenant", "fingerprint"])]
        constraints = [
            models.UniqueConstraint(fields=["payment"], condition=models.Q(payment__isnull=False), name="uniq_bank_txn_vendor_payment"),
            models.UniqueConstraint(fields=["transport_collection"], condition=models.Q(transport_collection__isnull=False), name="uniq_bank_txn_transport_collection"),
            models.UniqueConstraint(fields=["driver_salary_payment"], condition=models.Q(driver_salary_payment__isnull=False), name="uniq_bank_txn_driver_salary_payment"),
        ]


class ReconciliationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    transaction = models.ForeignKey(BankTransaction, on_delete=models.PROTECT, related_name="matching_runs")
    fingerprint = models.CharField(max_length=64)
    rule_version = models.CharField(max_length=40)
    source_snapshot = models.JSONField()
    ambiguous = models.BooleanField(default=False)
    candidate_limit_reached = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["transaction", "fingerprint", "rule_version"], name="uniq_reconciliation_run_input")]


class ReconciliationCandidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ReconciliationRun, on_delete=models.PROTECT, related_name="candidates")
    rank = models.PositiveIntegerField()
    target_type = models.CharField(max_length=24)
    target_id = models.UUIDField()
    evidence = models.JSONField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "target_type", "target_id"], name="uniq_run_candidate_target")]


class ReconciliationGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    source_account = models.ForeignKey("settlements.SourceAccount", on_delete=models.PROTECT)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=12, default="MATCHED", choices=[(s, s) for s in ("MATCHED", "RECONCILED", "CLEARED")])
    revision = models.PositiveIntegerField(default=0)
    reference = models.CharField(max_length=120)
    evidence = models.JSONField()
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class ReconciliationGroupBank(models.Model):
    group = models.ForeignKey(ReconciliationGroup, on_delete=models.PROTECT, related_name="bank_members")
    transaction = models.ForeignKey(BankTransaction, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "transaction"], name="uniq_group_bank_member")]


class ReconciliationGroupTarget(models.Model):
    group = models.ForeignKey(ReconciliationGroup, on_delete=models.PROTECT, related_name="targets")
    active = models.BooleanField(default=True)
    payment = models.ForeignKey(Payment, null=True, on_delete=models.PROTECT)
    transport_collection = models.ForeignKey("fleet.TransportCollection", null=True, on_delete=models.PROTECT)
    driver_salary_payment = models.ForeignKey("fleet.DriverSalaryPayment", null=True, on_delete=models.PROTECT)
    snapshot = models.JSONField()
    class Meta:
        constraints = [
            models.CheckConstraint(condition=(models.Q(payment__isnull=False, transport_collection__isnull=True, driver_salary_payment__isnull=True)
                | models.Q(payment__isnull=True, transport_collection__isnull=False, driver_salary_payment__isnull=True)
                | models.Q(payment__isnull=True, transport_collection__isnull=True, driver_salary_payment__isnull=False)), name="one_group_target_kind"),
            models.UniqueConstraint(fields=["payment"], condition=models.Q(active=True, payment__isnull=False), name="uniq_active_group_payment"),
            models.UniqueConstraint(fields=["transport_collection"], condition=models.Q(active=True, transport_collection__isnull=False), name="uniq_active_group_collection"),
            models.UniqueConstraint(fields=["driver_salary_payment"], condition=models.Q(active=True, driver_salary_payment__isnull=False), name="uniq_active_group_salary"),
        ]


class ReconciliationReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    transaction = models.ForeignKey(BankTransaction, null=True, on_delete=models.PROTECT, related_name="review_events")
    group = models.ForeignKey(ReconciliationGroup, null=True, on_delete=models.PROTECT, related_name="review_events")
    candidate = models.ForeignKey(ReconciliationCandidate, null=True, on_delete=models.PROTECT, related_name="reviews")
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=32)
    reason = models.CharField(max_length=500)
    evidence = models.JSONField(default=dict)
    request_key = models.UUIDField(null=True)
    request_hash = models.CharField(max_length=64, blank=True)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "request_key"], condition=models.Q(request_key__isnull=False), name="uniq_reconciliation_review_key")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Reconciliation decisions are append-only.")
        return super().save(*args, **kwargs)


class VendorPortalInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="vendor_portal_invites")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="portal_invites")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "vendor", "expires_at"])]


class VendorPortalMessage(models.Model):
    class Direction(models.TextChoices): INBOUND = "INBOUND"; OUTBOUND = "OUTBOUND"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="portal_messages")
    direction = models.CharField(max_length=8, choices=Direction.choices)
    body = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "invoice", "created_at"])]


class AIReviewSuggestion(models.Model):
    class Status(models.TextChoices): PENDING = "PENDING"; ACCEPTED = "ACCEPTED"; DISMISSED = "DISMISSED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="ai_review_suggestions")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="ai_review_suggestions")
    provider = models.CharField(max_length=40, default="openai")
    model = models.CharField(max_length=80)
    suggestion_type = models.CharField(max_length=32)
    title = models.CharField(max_length=180)
    rationale = models.TextField()
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    evidence_fields = models.JSONField(default=list)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "invoice", "status"])]


class TenantAPIKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=24, unique=True)
    secret_hash = models.CharField(max_length=256)
    scopes = models.JSONField(default=list)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "revoked_at"])]


class WebhookEndpoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="webhook_endpoints")
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=500)
    encrypted_secret = models.TextField()
    events = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "active"])]


class WebhookDelivery(models.Model):
    class Status(models.TextChoices): QUEUED = "QUEUED"; DELIVERING = "DELIVERING"; DELIVERED = "DELIVERED"; RETRY = "RETRY"; FAILED = "FAILED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    event_id = models.UUIDField(default=uuid.uuid4)
    event_type = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    cycle_attempts = models.PositiveSmallIntegerField(default=0)
    manual_retry_count = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["endpoint", "event_id"], name="uniq_webhook_event_delivery")]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]


class MonthEndChecklist(models.Model):
    class Status(models.TextChoices): OPEN = "OPEN"; REVIEWED = "REVIEWED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="month_end_checklist")
    period = models.CharField(max_length=7)
    item_key = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "period", "item_key"], name="uniq_month_end_check_item")]
        indexes = [models.Index(fields=["tenant", "period", "status"])]


class GmailOAuthState(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state_hash = models.CharField(max_length=64, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="gmail_oauth_states")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gmail_oauth_states")
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GmailConnection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="gmail_connection")
    google_subject = models.CharField(max_length=255)
    email = models.EmailField()
    encrypted_refresh_token = models.TextField()
    scopes = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    connected_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GoogleSignInState(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state_hash = models.CharField(max_length=64, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="google_signin_states")
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
