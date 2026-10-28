export type NavigationAccess = {
  role: string;
  entitlements: { features: Record<string, { enabled: boolean }> };
};

// Keys are the same catalog keys used by Super Admin and API permissions.
const features: Record<string, string> = {
  "/fleet": "fleet_management",
  "/invoices": "invoice_upload",
  "/email-intake": "email_invoice_intake",
  "/duplicates": "duplicate_detection",
  "/bulk-actions": "bulk_actions",
  "/approvals": "approval_workflow",
  "/approval-rules": "approval_workflow",
  "/payments": "payment_tracking",
  "/settlements": "payment_tracking",
  "/bank-reconciliation": "payment_tracking",
  "/purchase-orders": "po_grn_matching",
  "/grns": "po_grn_matching",
  "/financial-notes": "credit_debit_notes",
  "/reports": "advanced_reports",
  "/exports": "tally_csv_export",
  "/ai-review": "ai_extraction",
  "/integrations": "api_access",
  "/integrations/erp": "api_access",
  "/whatsapp": "whatsapp_intake",
  "/custom-fields": "custom_fields",
};
const financeReaders = ["OWNER", "FINANCE", "AUDITOR"];
const roles: Record<string, string[]> = {
  "/integrations/erp": financeReaders,
  "/settlements": financeReaders,
  "/users": ["OWNER"], "/branches": ["OWNER"],
  "/invoices": [...financeReaders, "APPROVER", "PURCHASE", "STORE"],
  "/payments": financeReaders, "/bank-reconciliation": financeReaders,
  "/reports": financeReaders, "/audit": financeReaders, "/exports": financeReaders,
  "/purchase-orders": [...financeReaders, "PURCHASE"],
  "/grns": [...financeReaders, "PURCHASE", "STORE"],
  "/fleet/driver": ["DRIVER"],
  "/fleet/driver-salaries": [...financeReaders, "FLEET"],
  "/fleet/finance-settings": [...financeReaders, "FLEET"],
  "/fleet/dock-schedule": [...financeReaders, "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/return-loads": [...financeReaders, "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/freight-reconciliation": [...financeReaders, "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/documents": [...financeReaders, "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/truck-documents": [...financeReaders, "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/maintenance": [...financeReaders, "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/revenue-leakage": [...financeReaders, "FLEET", "APPROVER"],
  "/fleet/exception-center": ["OWNER", "FINANCE", "FLEET", "APPROVER"],
  "/fleet/booking-history": ["OWNER", "FINANCE", "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/customer-portal": ["OWNER", "FINANCE", "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/customer-notifications": ["OWNER", "FINANCE", "FLEET", "APPROVER"],
  "/fleet/reliability": ["OWNER", "FINANCE", "FLEET", "PURCHASE", "APPROVER"],
  "/fleet/live-tracking": ["OWNER", "FINANCE", "FLEET", "APPROVER"],
};

export function canShowNavigation(href: string, access: NavigationAccess | null): boolean {
  if (!access) return false;
  const path = href.split(/[?#]/)[0];
  const rolePath = Object.keys(roles).sort((a,b)=>b.length-a.length).find(route=>path===route||path.startsWith(`${route}/`));
  const featurePath = Object.keys(features).sort((a,b)=>b.length-a.length).find(route=>path===route||path.startsWith(`${route}/`));
  if (access.role === "DRIVER" && path !== "/fleet/driver") return false;
  if (rolePath && !roles[rolePath].includes(access.role)) return false;
  const feature = featurePath ? features[featurePath] : undefined;
  return !feature || access.entitlements?.features?.[feature]?.enabled === true;
}

export function filterNavigation<T extends { href: string; children?: T[] }>(items: T[], access: NavigationAccess | null): T[] {
  return items.flatMap(item => {
    const children = item.children ? filterNavigation(item.children, access) : undefined;
    const allowed = canShowNavigation(item.href, access);
    // A group can still contain an independently enabled child (e.g. financial notes).
    if (!allowed && !children?.length) return [];
    return [{ ...item, href: allowed ? item.href : children![0].href, children: children?.length ? children : undefined }];
  });
}
