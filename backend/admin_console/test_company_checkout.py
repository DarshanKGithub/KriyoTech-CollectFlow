import hashlib
import hmac
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Membership
from tenants.models import Tenant
from .billing import GatewayError, activate_paid_subscription
from .models import AdminStaff, BillingInvoice, Payment, Plan, RazorpayWebhookEvent, Subscription
from .test_helpers import authenticate_staff


@override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="test-secret", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CompanyCheckoutTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="staff", email="staff@example.test")
        self.staff = AdminStaff.objects.create(user=self.user, role="SUPER_ADMIN")
        authenticate_staff(self.client, self.staff)
        self.plan = Plan.objects.create(name="Starter", slug="starter", monthly_price=750000)
        self.tenant = Tenant.objects.create(name="Transport Co", workspace_key="transport")
        self.subscription = Subscription.objects.create(tenant=self.tenant, plan=self.plan, status="ONBOARDING")
        self.url = f"/api/v1/admin/companies/{self.tenant.id}/checkout"
        self.order = {"id": "order_company", "amount": 750000, "currency": "INR"}

    def create_order(self):
        with patch("admin_console.company_checkout.razorpay_request", return_value=self.order):
            response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Payment.objects.get(tenant=self.tenant)

    def signature(self, order="order_company", payment="pay_company"):
        return hmac.new(b"test-secret", f"{order}|{payment}".encode(), hashlib.sha256).hexdigest()

    def test_order_uses_server_price_and_repeated_click_reuses_pending_order(self):
        payment = self.create_order()
        with patch("admin_console.company_checkout.razorpay_request") as gateway:
            response = self.client.post(self.url, {"amount": 1}, format="json")
        gateway.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["amount"], 750000)
        self.assertEqual(Payment.objects.count(), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, "ONBOARDING")
        self.assertEqual(payment.status, "PENDING")

    def test_verify_and_later_webhook_activate_only_once(self):
        payment = self.create_order()
        payload = {"razorpay_order_id": "order_company", "razorpay_payment_id": "pay_company", "razorpay_signature": self.signature()}
        remote = {"id": "pay_company", "order_id": "order_company", "amount": 750000, "currency": "INR", "status": "captured"}
        with patch("admin_console.company_checkout.razorpay_request", return_value=remote):
            response = self.client.post(self.url+"/verify", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.subscription.refresh_from_db()
        period_end = self.subscription.current_period_end
        event = RazorpayWebhookEvent.objects.create(event_id="evt_company", event_type="payment.captured", payload={"payload": {"payment": {"entity": remote}}})
        from .tasks import process_razorpay_webhook
        process_razorpay_webhook.run(str(event.id))
        self.subscription.refresh_from_db(); payment.refresh_from_db()
        self.assertEqual(payment.status, "PAID")
        self.assertEqual(payment.razorpay_payment_id, "pay_company")
        self.assertEqual(self.subscription.status, "ACTIVE")
        self.assertEqual(self.subscription.current_period_end, period_end)
        self.assertEqual(BillingInvoice.objects.filter(tenant=self.tenant).count(), 1)
        status = self.client.get(self.url)
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.data["paid"])
        # A late failed attempt for the same order cannot undo successful payment.
        failed = RazorpayWebhookEvent.objects.create(event_id="evt_late_failure", event_type="payment.failed", payload={"payload": {"payment": {"entity": {"order_id": "order_company", "id": "pay_failed"}}}})
        process_razorpay_webhook.run(str(failed.id))
        payment.refresh_from_db()
        self.assertEqual(payment.status, "PAID")
        self.assertEqual(payment.razorpay_payment_id, "pay_company")

    def test_bad_signature_and_wrong_amount_cannot_activate(self):
        self.create_order()
        payload = {"razorpay_order_id": "order_company", "razorpay_payment_id": "pay_company", "razorpay_signature": "bad"}
        with patch("admin_console.company_checkout.razorpay_request") as gateway:
            self.assertEqual(self.client.post(self.url+"/verify", payload, format="json").status_code, 400)
            gateway.assert_not_called()
        payload["razorpay_signature"] = self.signature()
        with patch("admin_console.company_checkout.razorpay_request", return_value={"id": "pay_company", "order_id": "order_company", "amount": 1, "currency": "INR", "status": "captured"}):
            self.assertEqual(self.client.post(self.url+"/verify", payload, format="json").status_code, 409)
        self.assertFalse(Payment.objects.filter(status="PAID").exists())

    def test_order_cannot_be_verified_for_another_company(self):
        self.create_order()
        other = Tenant.objects.create(name="Other", workspace_key="other")
        response = self.client.post(f"/api/v1/admin/companies/{other.id}/checkout/verify", {"razorpay_order_id": "order_company", "razorpay_payment_id": "pay_company", "razorpay_signature": self.signature()}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_support_and_tenant_owner_cannot_use_staff_checkout(self):
        self.staff.role = "SUPPORT"; self.staff.save()
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 403)
        self.staff.delete()
        Membership.objects.create(tenant=self.tenant, user=self.user, role="OWNER")
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 403)

    def test_gateway_failure_keeps_company_and_creates_no_payment(self):
        with patch("admin_console.company_checkout.razorpay_request", side_effect=GatewayError()):
            response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 502)
        self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())
        self.assertFalse(Payment.objects.exists())

    def test_collect_now_creates_onboarding_subscription_without_trial(self):
        response = self.client.post("/api/v1/admin/companies", {"company_name": "Paying Client", "owner_name": "Client", "owner_email": "client@example.test", "plan_id": str(self.plan.id), "collect_payment": True, "trial_enabled": True}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["subscription"]["status"], "ONBOARDING")
        self.assertIsNone(response.data["subscription"]["trial_ends_at"])

    @override_settings(RAZORPAY_KEY_SECRET="")
    def test_missing_gateway_configuration_rejects_before_company_creation(self):
        response = self.client.post("/api/v1/admin/companies", {"company_name": "Blocked", "owner_name": "Client", "owner_email": "blocked@example.test", "plan_id": str(self.plan.id), "collect_payment": True}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Tenant.objects.filter(name="Blocked").exists())

    def test_renewal_date_and_duplicate_activation_are_safe(self):
        payment = self.create_order()
        self.subscription.status = "ACTIVE"
        self.subscription.current_period_end = timezone.now()
        self.subscription.save()
        activate_paid_subscription(payment)
        self.subscription.refresh_from_db()
        period_end = self.subscription.current_period_end
        # Same stale instance is deliberate: callbacks may race with webhooks.
        activate_paid_subscription(payment)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.current_period_end, period_end)
        self.assertEqual(BillingInvoice.objects.count(), 1)
