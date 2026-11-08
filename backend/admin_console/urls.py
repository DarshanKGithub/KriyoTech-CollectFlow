from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView
from .auth import AdminLoginView, AdminMFAVerifyView, AdminMFASetupView, AdminMFAEnableView
from .health import ExtractionHealth
from .company_checkout import CompanyCheckout, CompanyCheckoutVerify
from .views import FeaturePricing
from .views import AdminDashboard, AdminMe, AdminPasswordChange, AuditLogs, BillingInvoices, CompanyDetail, CompanyEntitlements, CompanyLifecycle, CompanyListCreate, Features, OfflinePaymentRecord, PaymentRefundCreate, Payments, PlanDetail, PlanFeatures, Plans, RazorpayEvents, Refunds, Subscriptions, SuperAdminCreate, Usage
from .views_configuration import (
    ConfigurationView, PlanFeaturesView, TenantConfigurationView, ConfigurationHistoryView,
    ConfigurationCacheView
)

urlpatterns = [
    path("operations/extraction-health", ExtractionHealth.as_view()),
    path("auth/login", AdminLoginView.as_view()),
    path("auth/mfa/verify", AdminMFAVerifyView.as_view()),
    path("auth/mfa/setup", AdminMFASetupView.as_view()),
    path("auth/mfa/enable", AdminMFAEnableView.as_view()),
    path("auth/logout", TokenBlacklistView.as_view()),
    path("auth/me", AdminMe.as_view()),
    path("auth/change-password", AdminPasswordChange.as_view()),
    path("staff/super-admins", SuperAdminCreate.as_view()),
    path("dashboard/summary", AdminDashboard.as_view()),
    path("companies", CompanyListCreate.as_view()),
    path("companies/<uuid:tenant_id>", CompanyDetail.as_view()),
    path("companies/<uuid:tenant_id>/checkout", CompanyCheckout.as_view()),
    path("companies/<uuid:tenant_id>/checkout/verify", CompanyCheckoutVerify.as_view()),
    path("companies/<uuid:tenant_id>/entitlements", CompanyEntitlements.as_view()),
    path("companies/<uuid:tenant_id>/lifecycle", CompanyLifecycle.as_view()),
    path("plans", Plans.as_view()), path("plans/<uuid:plan_id>", PlanDetail.as_view()), path("plans/<uuid:plan_id>/features", PlanFeatures.as_view()),
    path("features", Features.as_view()), path("features/<slug:feature_key>/pricing", FeaturePricing.as_view()), path("subscriptions", Subscriptions.as_view()),
    path("usage", Usage.as_view()), path("payments", Payments.as_view()), path("payments/offline", OfflinePaymentRecord.as_view()), path("payments/<uuid:payment_id>/refund", PaymentRefundCreate.as_view()), path("refunds", Refunds.as_view()), path("razorpay/events", RazorpayEvents.as_view()),
    path("billing-invoices", BillingInvoices.as_view()), path("audit-logs", AuditLogs.as_view()),
    path("configuration/features", ConfigurationView.as_view()),
    path("configuration/plan/<uuid:plan_id>", PlanFeaturesView.as_view()),
    path("configuration/tenant/<uuid:tenant_id>", TenantConfigurationView.as_view()),
    path("configuration/tenant/<uuid:tenant_id>/feature", TenantConfigurationView.as_view()),
    path("configuration/history/<uuid:tenant_id>", ConfigurationHistoryView.as_view()),
    path("configuration/cache/clear", ConfigurationCacheView.as_view()),
]
