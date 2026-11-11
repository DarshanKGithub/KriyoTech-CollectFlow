# Feature Entitlements

Feature catalog keys are stable identifiers, independent of plan names. Plan-feature rows define default enabled state and optional limit/period. Tenant overrides support enabled state, limit, reason, author, expiry. Resolve active overrides over plan defaults in `admin_console.services.entitlements`. Product APIs must call the centralized service before feature-gated operations; UI visibility is only a convenience.

Initial catalog: invoice_upload, ai_extraction, email_invoice_intake, po_grn_matching, duplicate_detection, approval_workflow, multi_level_approval, auto_approval, payment_tracking, credit_debit_notes, custom_fields, bulk_actions, tally_csv_export, tally_xml_integration, api_access, advanced_reports, whatsapp_intake, sso, priority_support.
