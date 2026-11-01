from datetime import timedelta
import hashlib
import hmac
import json
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from io import StringIO
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken
from accounts.models import Invitation, Membership
from tenants.models import Tenant
from .models import AdminAuditLog, AdminStaff, BillingInvoice, Payment, PaymentRefund, Plan, PlanFeature, RazorpayWebhookEvent, TenantFeatureOverride, Feature, Subscription, TenantUsage
from .billing import verify_checkout_signature, verify_webhook_signature
from django.core.cache import cache
from .test_helpers import authenticate_staff


class AdminConsoleTests(APITestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.staff_user = User.objects.create_user(username="admin@kriyopay.test", email="admin@kriyopay.test", password="correct-horse-battery")
        self.staff = AdminStaff.objects.create(user=self.staff_user, role=AdminStaff.Role.SUPER_ADMIN)
        self.plan = Plan.objects.create(name="Starter", slug="starter", monthly_price=750000, trial_days=14)
        authenticate_staff(self.client, self.staff)

    def test_bootstrap_command_creates_one_high_entropy_super_admin_and_refuses_reuse(self):
        self.staff.delete()
        output = StringIO()
        call_command("bootstrap_super_admin", "first-admin@kriyopay.test", stdout=output)
        created_user = get_user_model().objects.get(email="first-admin@kriyopay.test")
        created_staff = AdminStaff.objects.get(user=created_user)
        self.assertEqual(created_staff.role, AdminStaff.Role.SUPER_ADMIN)
        self.assertTrue(created_user.check_password(output.getvalue().split("One-time password (copy it now): ")[1].splitlines()[0]))
        with self.assertRaises(CommandError):
            call_command("bootstrap_super_admin", "second-admin@kriyopay.test", stdout=StringIO())

    def test_internal_admin_login_rejects_tenant_user_and_accepts_provisioned_staff(self):
        tenant_user = get_user_model().objects.create_user(username="tenant@acme.test", email="tenant@acme.test", password="correct-horse-battery")
        response = self.client.post("/api/v1/admin/auth/login", {"email": tenant_user.email, "password": "correct-horse-battery"}, format="json")
        self.assertEqual(response.status_code, 401)
        denied = AdminAuditLog.objects.filter(actor=tenant_user, action="ADMIN_LOGIN_DENIED").exists()
        self.assertTrue(denied)
        response = self.client.post("/api/v1/admin/auth/login", {"email": self.staff_user.email, "password": "correct-horse-battery"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], AdminStaff.Role.SUPER_ADMIN)

    def test_shared_login_marks_admin_for_admin_panel_redirect(self):
        response = self.client.post("/api/v1/auth/login", {"email": self.staff_user.email, "password": "correct-horse-battery"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["account_type"], "ADMIN")
        self.assertEqual(response.data["admin_role"], AdminStaff.Role.SUPER_ADMIN)
        self.assertTrue(response.data["mfa_required"])
        self.assertNotIn("access", response.data)

    def test_shared_login_marks_company_member_as_workspace_account(self):
        user = get_user_model().objects.create_user(username="member@shared.test", email="member@shared.test", password="correct-horse-battery")
        response = self.client.post("/api/v1/auth/login", {"email": user.email, "password": "correct-horse-battery"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["account_type"], "WORKSPACE")

    def test_super_admin_can_create_another_super_admin(self):
        response = self.client.post("/api/v1/admin/staff/super-admins", {"name": "Second Admin", "email": "second-admin@kriyopay.test", "password": "A-different-long-password-82!"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = get_user_model().objects.get(email="second-admin@kriyopay.test")
        self.assertTrue(user.check_password("A-different-long-password-82!"))
        self.assertEqual(AdminStaff.objects.get(user=user).role, AdminStaff.Role.SUPER_ADMIN)
        self.assertTrue(AdminAuditLog.objects.filter(actor=self.staff_user, action="SUPER_ADMIN_CREATED").exists())

    def test_admin_can_change_own_password_with_current_password(self):
        response = self.client.post("/api/v1/admin/auth/change-password", {"current_password": "correct-horse-battery", "new_password": "A-fresh-password-for-admin-82!"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.staff_user.refresh_from_db()
        self.assertTrue(self.staff_user.check_password("A-fresh-password-for-admin-82!"))
        self.assertTrue(AdminAuditLog.objects.filter(actor=self.staff_user, action="ADMIN_PASSWORD_CHANGED").exists())

    def test_company_delete_revokes_access_and_retains_records(self):
        tenant = Tenant.objects.create(name="Delete Me Ltd", workspace_key="delete-me")
        member = get_user_model().objects.create_user(username="delete-member@acme.test", email="delete-member@acme.test", password="correct-horse-battery")
        membership = Membership.objects.create(tenant=tenant, user=member, role=Membership.Role.OWNER)
        response = self.client.delete(f"/api/v1/admin/companies/{tenant.id}", {"confirm_name": "Delete Me Ltd", "reason": "Customer requested account closure."}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        tenant.refresh_from_db(); membership.refresh_from_db()
        self.assertTrue(tenant.is_deleted)
        self.assertFalse(membership.is_active)
        self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())
        self.assertTrue(AdminAuditLog.objects.filter(action="COMPANY_DELETED", object_id=str(tenant.id)).exists())
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(member)}")
        self.assertEqual(self.client.get("/api/v1/auth/workspaces").data, [])

    def test_tenant_token_cannot_access_control_plane(self):
        user = get_user_model().objects.create_user(username="member@acme.test", email="member@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme")
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        response = self.client.get("/api/v1/admin/companies")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(AdminAuditLog.objects.filter(actor=user, action="ADMIN_ACCESS_DENIED").exists())

    @override_settings(FRONTEND_BASE_URL="http://localhost:3000")
    def test_company_onboarding_creates_owner_invitation_subscription_and_audit(self):
        response = self.client.post("/api/v1/admin/companies", {"company_name": "Acme Works", "owner_name": "Asha Rao", "owner_email": "asha@acme.test", "industry": "Manufacturing", "plan_id": str(self.plan.id), "trial_enabled": True, "trial_days": 10}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        tenant = Tenant.objects.get(workspace_key="acme-works")
        membership = Membership.objects.get(tenant=tenant)
        self.assertEqual(membership.role, Membership.Role.OWNER)
        self.assertFalse(membership.user.has_usable_password())
        invite = Invitation.objects.get(tenant=tenant)
        self.assertEqual(len(invite.token_hash), 64)
        subscription = Subscription.objects.get(tenant=tenant)
        self.assertEqual(subscription.status, Subscription.Status.TRIAL)
        self.assertGreater(subscription.trial_ends_at, timezone.now()+timedelta(days=8))
        self.assertTrue(AdminAuditLog.objects.filter(tenant=tenant, action="COMPANY_ONBOARDED").exists())

    def test_read_only_admin_cannot_change_company_or_plan(self):
        self.staff.role = AdminStaff.Role.READ_ONLY
        self.staff.save()
        self.plan.refresh_from_db()
        response = self.client.patch(f"/api/v1/admin/plans/{self.plan.id}", {"name": "Changed"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Plan.objects.get(pk=self.plan.pk).name, "Starter")

    def test_support_role_does_not_receive_revenue_or_company_financial_records(self):
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-support")
        Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL)
        self.staff.role = AdminStaff.Role.SUPPORT; self.staff.save(update_fields=["role"])
        dashboard = self.client.get("/api/v1/admin/dashboard/summary")
        company = self.client.get(f"/api/v1/admin/companies/{tenant.id}")
        self.assertEqual(dashboard.status_code, 200)
        self.assertFalse(dashboard.data["financial_access"])
        self.assertNotIn("mrr_paise", dashboard.data)
        self.assertEqual(company.status_code, 200)
        self.assertNotIn("payments", company.data)
        self.assertNotIn("audit", company.data)

    def test_entitlement_override_is_audited_and_takes_precedence(self):
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme")
        Subscription.objects.create(tenant=tenant, plan=self.plan)
        feature = Feature.objects.create(key="api_access", name="Public API")
        response = self.client.patch(f"/api/v1/admin/companies/{tenant.id}/entitlements", {"feature_key": feature.key, "enabled": True, "reason": "Temporary integration pilot"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["features"][feature.key]["enabled"])
        self.assertTrue(TenantFeatureOverride.objects.filter(tenant=tenant, feature=feature, enabled=True).exists())
        self.assertTrue(AdminAuditLog.objects.filter(tenant=tenant, action="TENANT_ENTITLEMENT_OVERRIDDEN").exists())

    def test_audit_records_are_append_only_at_model_api(self):
        row = AdminAuditLog.objects.create(actor=self.staff_user, actor_role=self.staff.role, action="TEST_EVENT")
        row.action = "CHANGED"
        with self.assertRaises(ValueError):
            row.save()
        with self.assertRaises(ValueError):
            row.delete()

    def test_past_due_tenant_can_read_but_cannot_write(self):
        user = get_user_model().objects.create_user(username="late@acme.test", email="late@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-late")
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
        Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.PAST_DUE)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        self.assertEqual(self.client.get("/api/v1/dashboard/summary").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/invoices/", {}, format="json").status_code, 403)

    def test_invoice_limit_is_enforced_for_active_subscription(self):
        user = get_user_model().objects.create_user(username="limit@acme.test", email="limit@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-limit")
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
        self.plan.invoice_limit = 1; self.plan.save(update_fields=["invoice_limit"])
        feature = Feature.objects.create(key="invoice_upload", name="Invoice upload")
        PlanFeature.objects.create(plan=self.plan, feature=feature, enabled=True)
        Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.ACTIVE)
        TenantUsage.objects.create(tenant=tenant, period_start=timezone.localdate().replace(day=1), period_end=timezone.localdate(), metric="invoices_uploaded", used_count=1, limit_value=1)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        response = self.client.post("/api/v1/invoices/", {}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("invoice limit", response.data["detail"].lower())

    def test_product_api_checks_plan_feature_entitlement(self):
        user = get_user_model().objects.create_user(username="feature@acme.test", email="feature@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-feature")
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
        feature = Feature.objects.create(key="po_grn_matching", name="PO/GRN matching")
        PlanFeature.objects.create(plan=self.plan, feature=feature, enabled=False)
        Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.ACTIVE)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        response = self.client.get("/api/v1/purchase-orders")
        self.assertEqual(response.status_code, 403)
        self.assertIn("not include", response.data["detail"].lower())

    def test_fleet_and_trips_is_configurable_as_plan_and_company_entitlement(self):
        call_command("seed_admin_catalog", stdout=StringIO())
        feature = Feature.objects.get(key="fleet_management")
        self.assertEqual(feature.name, "Fleet & Trips")
        starter = Plan.objects.get(slug="starter")
        self.assertFalse(PlanFeature.objects.get(plan=starter, feature=feature).enabled)
        catalog = self.client.get("/api/v1/admin/features")
        self.assertIn("Fleet & Trips", [row["name"] for row in catalog.data["features"]])

        tenant = Tenant.objects.create(name="Fleet entitlement", workspace_key="fleet-entitlement")
        user = get_user_model().objects.create_user(username="fleet-entitlement@acme.test", email="fleet-entitlement@acme.test", password="correct-horse-battery")
        Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
        Subscription.objects.create(tenant=tenant, plan=starter, status=Subscription.Status.ACTIVE)
        tenant_client = self.client.__class__()
        tenant_client.force_authenticate(user=user)
        denied = tenant_client.get("/api/v1/fleet/customers", HTTP_X_WORKSPACE=tenant.workspace_key)
        self.assertEqual(denied.status_code, 403)

        enabled = self.client.patch(f"/api/v1/admin/companies/{tenant.id}/entitlements", {"feature_key": feature.key, "enabled": True, "reason": "Enable fleet pilot"}, format="json")
        self.assertEqual(enabled.status_code, 200)
        allowed = tenant_client.get("/api/v1/fleet/customers", HTTP_X_WORKSPACE=tenant.workspace_key)
        self.assertEqual(allowed.status_code, 200)

    def test_invoice_creation_updates_monthly_usage_counter(self):
        from invoices.models import Invoice
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-usage")
        Invoice.objects.create(tenant=tenant)
        row = TenantUsage.objects.get(tenant=tenant, metric="invoices_uploaded", period_start=timezone.localdate().replace(day=1))
        self.assertEqual(row.used_count, 1)

    def test_invoice_quota_is_enforced_for_model_creation_and_zero_override(self):
        from rest_framework.exceptions import PermissionDenied
        from invoices.models import Invoice

        tenant = Tenant.objects.create(name="Quota", workspace_key="quota-model")
        self.plan.invoice_limit = 1
        self.plan.save(update_fields=["invoice_limit"])
        feature = Feature.objects.create(key="invoice_upload", name="Invoice upload")
        PlanFeature.objects.create(plan=self.plan, feature=feature, enabled=True)
        Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.ACTIVE)

        Invoice.objects.create(tenant=tenant)
        with self.assertRaises(PermissionDenied):
            Invoice.objects.create(tenant=tenant)
        usage = TenantUsage.objects.get(tenant=tenant, metric="invoices_uploaded")
        self.assertEqual(usage.used_count, 1)

        zero_tenant = Tenant.objects.create(name="Zero quota", workspace_key="quota-zero")
        Subscription.objects.create(tenant=zero_tenant, plan=self.plan, status=Subscription.Status.ACTIVE)
        TenantFeatureOverride.objects.create(
            tenant=zero_tenant, feature=feature, enabled=True, limit_value=0,
            reason="No invoice uploads during setup",
        )
        with self.assertRaises(PermissionDenied):
            Invoice.objects.create(tenant=zero_tenant)
        self.assertFalse(TenantUsage.objects.filter(tenant=zero_tenant, metric="invoices_uploaded").exists())

    def test_razorpay_signatures_use_server_secrets(self):
        with override_settings(RAZORPAY_KEY_SECRET="unit-test-secret", RAZORPAY_WEBHOOK_SECRET="webhook-test-secret"):
            checkout = hmac.new(b"unit-test-secret", b"order_test|pay_test", hashlib.sha256).hexdigest()
            self.assertTrue(verify_checkout_signature("order_test", "pay_test", checkout))
            self.assertFalse(verify_checkout_signature("order_test", "pay_wrong", checkout))
            body = b'{"event":"payment.captured"}'
            webhook = hmac.new(b"webhook-test-secret", body, hashlib.sha256).hexdigest()
            self.assertTrue(verify_webhook_signature(body, webhook))
            self.assertFalse(verify_webhook_signature(body+b" ", webhook))

    @override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="api-secret", RAZORPAY_WEBHOOK_SECRET="hook-secret", RAZORPAY_API_BASE_URL="https://api.razorpay.com/v1")
    def test_verified_payment_activates_subscription_and_creates_billing_invoice(self):
        from unittest.mock import patch
        user = get_user_model().objects.create_user(username="billing@acme.test", email="billing@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-billing")
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
        sub = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL, trial_ends_at=timezone.now()+timedelta(days=3))
        payment = Payment.objects.create(tenant=tenant, subscription=sub, requested_plan=self.plan, billing_cycle=Subscription.Cycle.MONTHLY,
            razorpay_order_id="order_verified", amount=750000, currency="INR")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        signature = hmac.new(b"api-secret", b"order_verified|pay_verified", hashlib.sha256).hexdigest()
        with patch("admin_console.views.razorpay_request", return_value={"id":"pay_verified","order_id":"order_verified","amount":750000,"currency":"INR","status":"captured"}):
            response = self.client.post("/api/v1/billing/razorpay/verify-payment", {"razorpay_order_id":"order_verified","razorpay_payment_id":"pay_verified","razorpay_signature":signature}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        payment.refresh_from_db(); sub.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.razorpay_payment_id, "pay_verified")
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(BillingInvoice.objects.filter(tenant=tenant, status=BillingInvoice.Status.PAID).count(), 1)

    @override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="api-secret", RAZORPAY_WEBHOOK_SECRET="hook-secret", RAZORPAY_API_BASE_URL="https://api.razorpay.com/v1")
    def test_razorpay_checkout_order_verify_and_duplicate_webhook_lifecycle(self):
        """Exercise the local API lifecycle while stubbing only Razorpay's network boundary."""
        from unittest.mock import patch
        from .tasks import process_razorpay_webhook
        user = get_user_model().objects.create_user(username="e2e@acme.test", email="e2e@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="E2E Acme", workspace_key="e2e-acme")
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
        subscription = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}", HTTP_X_WORKSPACE="e2e-acme")

        with patch("admin_console.views.razorpay_request", return_value={"id": "order_e2e", "amount": 750000, "currency": "INR"}) as gateway:
            created = self.client.post("/api/v1/billing/razorpay/create-order", {"plan_id": str(self.plan.id), "billing_cycle": "MONTHLY"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(gateway.call_args.args[1], "/orders")
        payment = Payment.objects.get(pk=created.data["payment_id"])
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(subscription.status, Subscription.Status.TRIAL)

        payment_id = "pay_e2e"
        checkout_signature = hmac.new(b"api-secret", b"order_e2e|pay_e2e", hashlib.sha256).hexdigest()
        with patch("admin_console.views.razorpay_request", return_value={"id": payment_id, "order_id": "order_e2e", "amount": 750000, "currency": "INR", "status": "captured"}):
            verified = self.client.post("/api/v1/billing/razorpay/verify-payment", {"razorpay_order_id": "order_e2e", "razorpay_payment_id": payment_id, "razorpay_signature": checkout_signature}, format="json")
        self.assertEqual(verified.status_code, 200, verified.data)
        subscription.refresh_from_db(); payment.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(BillingInvoice.objects.filter(tenant=tenant).count(), 1)

        # A signed provider event is accepted and duplicate delivery is harmless.
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": payment_id, "order_id": "order_e2e", "amount": 750000, "currency": "INR", "status": "captured"}}}}, separators=(",", ":")).encode()
        signature = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
        with patch("admin_console.tasks.process_razorpay_webhook.delay"):
            accepted = self.client.generic("POST", "/api/v1/billing/razorpay/webhook", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature, HTTP_X_RAZORPAY_EVENT_ID="evt_e2e")
            duplicate = self.client.generic("POST", "/api/v1/billing/razorpay/webhook", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature, HTTP_X_RAZORPAY_EVENT_ID="evt_e2e")
        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(duplicate.status_code, 200)
        event = RazorpayWebhookEvent.objects.get(event_id="evt_e2e")
        self.assertEqual(process_razorpay_webhook.apply(args=[str(event.id)]).get(), "processed")
        self.assertEqual(process_razorpay_webhook.apply(args=[str(event.id)]).get(), "already processed")
        self.assertEqual(BillingInvoice.objects.filter(tenant=tenant).count(), 1)

    @override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="api-secret", RAZORPAY_WEBHOOK_SECRET="hook-secret", RAZORPAY_API_BASE_URL="https://api.razorpay.com/v1")
    def test_frontend_success_claim_without_captured_server_payment_never_activates(self):
        from unittest.mock import patch
        user = get_user_model().objects.create_user(username="notcaptured@acme.test", email="notcaptured@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="Not Captured Ltd", workspace_key="not-captured")
        Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
        subscription = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL)
        payment = Payment.objects.create(tenant=tenant, subscription=subscription, requested_plan=self.plan, billing_cycle=Subscription.Cycle.MONTHLY, razorpay_order_id="order_not_captured", amount=750000, currency="INR")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}", HTTP_X_WORKSPACE="not-captured")
        signature = hmac.new(b"api-secret", b"order_not_captured|pay_authorized", hashlib.sha256).hexdigest()
        with patch("admin_console.views.razorpay_request", return_value={"id": "pay_authorized", "order_id": "order_not_captured", "amount": 750000, "currency": "INR", "status": "authorized"}):
            response = self.client.post("/api/v1/billing/razorpay/verify-payment", {"razorpay_order_id": "order_not_captured", "razorpay_payment_id": "pay_authorized", "razorpay_signature": signature}, format="json")
        self.assertEqual(response.status_code, 409)
        subscription.refresh_from_db(); payment.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.TRIAL)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertFalse(BillingInvoice.objects.filter(tenant=tenant).exists())

    def test_payment_failed_webhook_marks_pending_payment_failed_without_activation(self):
        tenant = Tenant.objects.create(name="Failed Payment Ltd", workspace_key="failed-payment")
        subscription = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL)
        payment = Payment.objects.create(tenant=tenant, subscription=subscription, requested_plan=self.plan, billing_cycle=Subscription.Cycle.MONTHLY, razorpay_order_id="order_failed", amount=750000, currency="INR")
        payload = {"event": "payment.failed", "payload": {"payment": {"entity": {"id": "pay_failed", "order_id": "order_failed", "error_description": "Payment declined"}}}}
        event = RazorpayWebhookEvent.objects.create(event_id="evt_failed", event_type="payment.failed", payload=payload)
        from .tasks import process_razorpay_webhook
        self.assertEqual(process_razorpay_webhook.apply(args=[str(event.id)]).get(), "processed")
        payment.refresh_from_db(); subscription.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(payment.failure_reason, "Payment declined")
        self.assertEqual(subscription.status, Subscription.Status.TRIAL)
        self.assertFalse(BillingInvoice.objects.filter(tenant=tenant).exists())

    @override_settings(RAZORPAY_WEBHOOK_SECRET="hook-secret")
    def test_webhook_requires_signature_and_is_idempotently_queued(self):
        from unittest.mock import patch
        body = json.dumps({"event":"payment.failed","payload":{"payment":{"entity":{"order_id":"missing-order"}}}}).encode()
        bad = self.client.generic("POST", "/api/v1/billing/razorpay/webhook", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="invalid")
        self.assertEqual(bad.status_code, 400)
        signature = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
        with patch("admin_console.tasks.process_razorpay_webhook.delay") as enqueue:
            first = self.client.generic("POST", "/api/v1/billing/razorpay/webhook", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature, HTTP_X_RAZORPAY_EVENT_ID="evt_unique")
            second = self.client.generic("POST", "/api/v1/billing/razorpay/webhook", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature, HTTP_X_RAZORPAY_EVENT_ID="evt_unique")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(RazorpayWebhookEvent.objects.filter(event_id="evt_unique").count(), 1)
        self.assertEqual(enqueue.call_count, 1)

    def test_captured_webhook_task_activates_only_once(self):
        user = get_user_model().objects.create_user(username="hook@acme.test", email="hook@acme.test", password="correct-horse-battery")
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-hook")
        sub = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL)
        payment = Payment.objects.create(tenant=tenant, subscription=sub, requested_plan=self.plan, amount=750000,
            currency="INR", razorpay_order_id="order_hook", billing_cycle=Subscription.Cycle.MONTHLY)
        payload = {"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_hook","order_id":"order_hook","amount":750000,"currency":"INR","status":"captured"}}}}
        event = RazorpayWebhookEvent.objects.create(event_id="evt_hook", event_type="payment.captured", payload=payload)
        from .tasks import process_razorpay_webhook
        self.assertEqual(process_razorpay_webhook.apply(args=[str(event.id)]).get(), "processed")
        sub.refresh_from_db(); event.refresh_from_db()
        original_end = sub.current_period_end
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(event.status, RazorpayWebhookEvent.Status.PROCESSED)
        self.assertEqual(BillingInvoice.objects.filter(tenant=tenant).count(), 1)
        self.assertEqual(process_razorpay_webhook.apply(args=[str(event.id)]).get(), "already processed")
        sub.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(sub.current_period_end, original_end)
        self.assertEqual(payment.razorpay_payment_id, "pay_hook")

    def test_order_paid_provider_read_runs_after_durable_claim_and_duplicate_worker_is_fenced(self):
        from unittest.mock import patch
        from .tasks import process_razorpay_webhook

        tenant = Tenant.objects.create(name="Order paid", workspace_key="order-paid")
        sub = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL)
        payment = Payment.objects.create(tenant=tenant, subscription=sub, requested_plan=self.plan, amount=750000,
            currency="INR", razorpay_order_id="order_paid", billing_cycle=Subscription.Cycle.MONTHLY)
        event = RazorpayWebhookEvent.objects.create(event_id="evt_order_paid", event_type="order.paid",
            payload={"payload": {"order": {"entity": {"id": payment.razorpay_order_id}}}})
        observed = {}

        def fetch_order(_method, _path):
            event.refresh_from_db()
            observed["status_before_provider_read"] = event.status
            observed["duplicate_result"] = process_razorpay_webhook.apply(args=[str(event.id)]).get()
            return {"status": "paid", "amount_paid": payment.amount, "currency": payment.currency}

        with patch("admin_console.tasks.razorpay_request", side_effect=fetch_order):
            self.assertEqual(process_razorpay_webhook.apply(args=[str(event.id)]).get(), "processed")
        self.assertEqual(observed["status_before_provider_read"], RazorpayWebhookEvent.Status.PROCESSING)
        self.assertEqual(observed["duplicate_result"], "already processing")
        sub.refresh_from_db(); event.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(event.status, RazorpayWebhookEvent.Status.PROCESSED)

    def test_offline_bank_payment_records_receipt_and_activates_plan(self):
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-offline")
        subscription = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.TRIAL)
        response = self.client.post("/api/v1/admin/payments/offline", {"tenant_id":str(tenant.id),"plan_id":str(self.plan.id),"billing_cycle":"MONTHLY","amount":750000,"payment_method":"NEFT","reference":"UTR-987654","reason":"Verified bank statement"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        subscription.refresh_from_db()
        payment = Payment.objects.get(tenant=tenant)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.offline_reference, "UTR-987654")
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertTrue(BillingInvoice.objects.filter(tenant=tenant, status=BillingInvoice.Status.PAID).exists())
        self.assertTrue(AdminAuditLog.objects.filter(action="OFFLINE_PAYMENT_RECORDED", tenant=tenant, actor=self.staff_user).exists())

    @override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="api-secret", RAZORPAY_WEBHOOK_SECRET="hook-secret", RAZORPAY_API_BASE_URL="https://api.razorpay.com/v1")
    def test_admin_refund_is_requested_server_side_and_waits_for_webhook(self):
        from unittest.mock import patch
        tenant = Tenant.objects.create(name="Acme", workspace_key="acme-refund")
        subscription = Subscription.objects.create(tenant=tenant, plan=self.plan, status=Subscription.Status.ACTIVE)
        payment = Payment.objects.create(tenant=tenant, subscription=subscription, amount=750000, currency="INR", status=Payment.Status.PAID, razorpay_payment_id="pay_refund")
        with patch("admin_console.views.razorpay_request", return_value={"id":"rfnd_test","amount":200000,"status":"pending"}) as gateway:
            response = self.client.post(f"/api/v1/admin/payments/{payment.id}/refund", {"amount":200000,"reason":"Duplicate charge"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(gateway.call_args.args[1], "/payments/pay_refund/refund")
        refund = PaymentRefund.objects.get(payment=payment)
        self.assertEqual(refund.status, PaymentRefund.Status.PENDING)
        self.assertEqual(Payment.objects.get(pk=payment.pk).status, Payment.Status.PAID)

    def test_admin_mfa_setup_and_verification_lifecycle(self):
        self.staff.mfa_enabled = False
        self.staff.mfa_secret = ""
        self.staff.save(update_fields=["mfa_enabled", "mfa_secret"])
        # 1. Login triggers MFA challenge for high-privilege roles (SUPER_ADMIN)
        response = self.client.post("/api/v1/admin/auth/login", {"email": self.staff_user.email, "password": "correct-horse-battery"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data.get("mfa_required"))
        self.assertTrue(response.data.get("mfa_setup_required"))
        pending_token = response.data.get("mfa_pending_token")
        self.assertIsNotNone(pending_token)

        # Clear credentials for unauthenticated test requests before setup
        self.client.credentials()

        # 2. Enrollment uses the scoped challenge, never a password-only JWT.
        setup_resp = self.client.post("/api/v1/admin/auth/mfa/setup", {"mfa_pending_token": pending_token}, format="json")
        self.assertEqual(setup_resp.status_code, 200, setup_resp.data)
        secret = setup_resp.data["secret"]
        self.assertIsNotNone(secret)

        # 3. Generate a valid code to enable MFA
        from .totp import get_totp_token
        valid_code = get_totp_token(secret)

        enable_resp = self.client.post("/api/v1/admin/auth/mfa/enable", {"code": valid_code, "mfa_pending_token": pending_token}, format="json")
        self.assertEqual(enable_resp.status_code, 200, enable_resp.data)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.mfa_enabled)

        # 4. Verify login flow now expects regular 2FA code instead of setup
        self.client.credentials()
        login_again = self.client.post("/api/v1/admin/auth/login", {"email": self.staff_user.email, "password": "correct-horse-battery"}, format="json")
        self.assertEqual(login_again.status_code, 200, login_again.data)
        self.assertTrue(login_again.data.get("mfa_required"))
        self.assertFalse(login_again.data.get("mfa_setup_required", False))
        mfa_token = login_again.data.get("mfa_pending_token")

        # 5. Verify 2FA token completion
        verify_resp = self.client.post("/api/v1/admin/auth/mfa/verify", {"mfa_pending_token": mfa_token, "code": get_totp_token(secret)}, format="json")
        self.assertEqual(verify_resp.status_code, 200, verify_resp.data)
        self.assertIn("access", verify_resp.data)
        self.assertTrue(verify_resp.data.get("mfa_verified"))
