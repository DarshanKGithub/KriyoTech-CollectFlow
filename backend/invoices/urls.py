from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import InvoiceViewSet, Me, MyWorkspaces, Branches, BranchAssignments, TenantSettings, Summary, ExceptionList, ExceptionResolve, ExceptionAssign, MatchRun, TallyExport, POs, PORevisions, GRNs, AuditRecords, InviteUser, AcceptInvitation, UserList
from vendors.views import VendorCollection, VendorDetail
from procurement.imports import PurchaseOrderImport, GRNImport
from .phase2 import DuplicateReview, MatchingControls, VendorAliasCollection, PaymentRegister, CreditDebitNoteCollection, CreditDebitNoteDecision
from .phase2_extended import IntakeToken, EmailIngestionWebhook, EmailLogs, ApprovalRules, ApprovalDelegations, ApprovalStepHistory, PendingApprovalQueue, AutoApprovalRules, ExceptionSLASettings, GRNServiceAcceptance, OverdueExceptions, FollowUps, FollowUpDetail, CustomFields, InvoiceCustomValues, Notifications, NotificationPreferences, Reports, BulkJobs
from communications.views import WhatsAppWebhook, WhatsAppMessages, WhatsAppDrafts, WhatsAppDraftSend, WhatsAppDraftReconcile, WhatsAppEndpoints, WhatsAppMessageInvoiceLink, WhatsAppConsents
from phase3.views import TaxCompliance, MonthEndChecklistAPI, GmailIntegrationAPI, GmailOAuthCallback, GmailSync, GoogleSignInStart, GoogleSignInCallback, BankReconciliation, VendorPortalInvitations, VendorPortalAccess, VendorPortalMessages, AIReviewSettings, AIInvoiceReview, APIKeyManagement, ExternalInvoiceAPI, WebhookSubscriptions, WebhookDeliveryRetry
from exports_app.views import TallyMappings
from admin_console.views import TenantBillingSummary, RazorpayCreateOrder, RazorpayVerifyPayment, RazorpayWebhook
from payments.views import PayoutInstructionCollection, PayoutInstructionDecision

router = DefaultRouter()
router.register("invoices", InvoiceViewSet, basename="invoice")
from phase3.mobile_oauth import MobileOAuthExchange

urlpatterns = [
    path("auth/oauth/mobile/exchange", MobileOAuthExchange.as_view()),
    path("billing/summary", TenantBillingSummary.as_view()),
    path("billing/razorpay/create-order", RazorpayCreateOrder.as_view()),
    path("billing/razorpay/verify-payment", RazorpayVerifyPayment.as_view()),
    path("billing/razorpay/webhook", RazorpayWebhook.as_view()),
    path("auth/me", Me.as_view()), path("auth/workspaces", MyWorkspaces.as_view()),
    path("branches", Branches.as_view()), path("branches/<uuid:branch_id>", Branches.as_view()), path("branch-assignments", BranchAssignments.as_view()),
    path("settings", TenantSettings.as_view()),
    path("tally-mappings", TallyMappings.as_view()), path("tally-mappings/<uuid:mapping_id>", TallyMappings.as_view()),
    path("auth/accept-invitation", AcceptInvitation.as_view()), path("users/invite", InviteUser.as_view()),
    path("users", UserList.as_view()), path("users/<uuid:user_id>/role", UserList.as_view()),
    path("dashboard/summary", Summary.as_view()), path("exceptions", ExceptionList.as_view()),
    path("exceptions/<uuid:exception_id>/assign", ExceptionAssign.as_view()), path("exceptions/<uuid:exception_id>/resolve", ExceptionResolve.as_view()),
    path("matching/run", MatchRun.as_view()), path("exports/tally-csv", TallyExport.as_view()), path("vendors", VendorCollection.as_view()), path("vendors/<uuid:vendor_id>", VendorDetail.as_view()),
    path("purchase-orders/import", PurchaseOrderImport.as_view()), path("purchase-orders", POs.as_view()), path("purchase-orders/<uuid:purchase_order_id>/revisions", PORevisions.as_view()), path("grns/import", GRNImport.as_view()), path("grns", GRNs.as_view()), path("audit-logs", AuditRecords.as_view()),
    path("duplicate-checks", DuplicateReview.as_view()), path("duplicate-checks/<uuid:check_id>/decision", DuplicateReview.as_view()),
    path("matching/settings", MatchingControls.as_view()), path("vendors/aliases", VendorAliasCollection.as_view()),
    path("payments", PaymentRegister.as_view()),
    path("payments/instructions", PayoutInstructionCollection.as_view()),
    path("payments/instructions/<uuid:instruction_id>/decision", PayoutInstructionDecision.as_view()),
    path("credit-debit-notes", CreditDebitNoteCollection.as_view()),
    path("credit-debit-notes/<uuid:note_id>/decision", CreditDebitNoteDecision.as_view()),
    path("invoice-intake-token", IntakeToken.as_view()),
    path("whatsapp/webhook", WhatsAppWebhook.as_view()),
    path("whatsapp/endpoints", WhatsAppEndpoints.as_view()), path("whatsapp/messages", WhatsAppMessages.as_view()),
    path("whatsapp/drafts", WhatsAppDrafts.as_view()),
    path("whatsapp/consents", WhatsAppConsents.as_view()),
    path("whatsapp/messages/<uuid:message_id>", WhatsAppMessageInvoiceLink.as_view()),
    path("whatsapp/drafts/<uuid:draft_id>/send", WhatsAppDraftSend.as_view()),
    path("whatsapp/drafts/<uuid:draft_id>/reconcile", WhatsAppDraftReconcile.as_view()),
    path("email-ingestion/logs", EmailLogs.as_view()), path("email-ingestion/<slug:workspace_key>", EmailIngestionWebhook.as_view()),
    path("approval-rules", ApprovalRules.as_view()), path("approval-rules/<uuid:rule_id>", ApprovalRules.as_view()),
    path("approvals/pending", PendingApprovalQueue.as_view()),
    path("approval-delegations", ApprovalDelegations.as_view()), path("invoices/<uuid:invoice_id>/approval-history", ApprovalStepHistory.as_view()),
    path("auto-approval-rules", AutoApprovalRules.as_view()), path("auto-approval-rules/<uuid:rule_id>", AutoApprovalRules.as_view()),
    path("exception-slas", ExceptionSLASettings.as_view()), path("exceptions/overdue", OverdueExceptions.as_view()),
    path("grns/<uuid:grn_id>/service-acceptance", GRNServiceAcceptance.as_view()),
    path("exceptions/escalate-overdue", OverdueExceptions.as_view()),
    path("invoices/<uuid:invoice_id>/follow-ups", FollowUps.as_view()), path("follow-ups/<uuid:followup_id>", FollowUpDetail.as_view()),
    path("follow-ups", FollowUps.as_view()),
    path("custom-fields", CustomFields.as_view()), path("invoices/<uuid:invoice_id>/custom-fields", InvoiceCustomValues.as_view()),
    path("notifications", Notifications.as_view()), path("notifications/<uuid:notification_id>/read", Notifications.as_view()),
    path("notification-preferences", NotificationPreferences.as_view()),
    path("reports/<slug:report_name>", Reports.as_view()),
    path("compliance/tax-reviews", TaxCompliance.as_view()),
    path("compliance/month-end", MonthEndChecklistAPI.as_view()),
    path("google/gmail", GmailIntegrationAPI.as_view()), path("google/gmail/oauth/callback", GmailOAuthCallback.as_view()), path("google/gmail/sync", GmailSync.as_view()),
    path("auth/oauth/google/start", GoogleSignInStart.as_view()), path("auth/oauth/google/callback/", GoogleSignInCallback.as_view()),
    path("bank-reconciliation", BankReconciliation.as_view()),
    path("vendor-portal/invitations", VendorPortalInvitations.as_view()),
    path("vendor-portal/invitations/<uuid:invite_id>", VendorPortalInvitations.as_view()),
    path("vendor-portal/access/<str:token>", VendorPortalAccess.as_view()),
    path("vendor-portal/access/<str:token>/invoices/<uuid:invoice_id>/messages", VendorPortalAccess.as_view()),
    path("vendor-portal/invoices/<uuid:invoice_id>/messages", VendorPortalMessages.as_view()),
    path("vendor-portal/messages", VendorPortalMessages.as_view()),
    path("webhooks/deliveries/<uuid:delivery_id>/retry", WebhookDeliveryRetry.as_view()),
    path("ai-review/settings", AIReviewSettings.as_view()),
    path("ai-review/suggestions", AIInvoiceReview.as_view()),
    path("api-keys", APIKeyManagement.as_view()), path("api-keys/<uuid:key_id>", APIKeyManagement.as_view()),
    path("external/invoices", ExternalInvoiceAPI.as_view()),
    path("webhooks", WebhookSubscriptions.as_view()), path("webhooks/<uuid:endpoint_id>", WebhookSubscriptions.as_view()),
    path("webhooks/<uuid:endpoint_id>/test", WebhookSubscriptions.as_view()),
    path("bulk-jobs", BulkJobs.as_view()), path("bulk-jobs/<uuid:job_id>", BulkJobs.as_view()), path("bulk-jobs/<uuid:job_id>/commit", BulkJobs.as_view()),
    path("", include(router.urls)),
]
