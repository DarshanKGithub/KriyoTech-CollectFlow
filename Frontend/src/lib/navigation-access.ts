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
const fleetModules:Record<string,string> = {
  "/fleet/live-tracking":"fleet_tracking", "/fleet/geofences":"fleet_geofencing",
  "/fleet/dispatch":"fleet_dispatch", "/fleet/dispatch-planner":"fleet_dispatch",
  "/fleet/lrs":"fleet_orders",
  "/fleet/trips":"fleet_trips", "/fleet/create-trip":"fleet_trips",
  "/fleet/trucks":"fleet_assets", "/fleet/drivers":"fleet_assets",
  "/fleet/fuel":"fleet_fuel", "/fleet/maintenance":"fleet_maintenance", "/fleet/reliability":"fleet_maintenance",
  "/fleet/documents":"fleet_documents", "/fleet/truck-documents":"fleet_documents",
  "/fleet/orders":"fleet_orders", "/fleet/customers":"fleet_orders",
  "/fleet/return-loads":"fleet_return_loads", "/fleet/booking-history":"fleet_return_loads",
  "/fleet/dock-schedule":"fleet_docks", "/fleet/exception-center":"fleet_exceptions",
  "/fleet/alerts":"fleet_exceptions", "/fleet/follow-ups":"fleet_exceptions",
  "/fleet/customer-portal":"fleet_portal", "/fleet/customer-notifications":"fleet_notifications",
  "/fleet/operational-reports":"fleet_reports", "/fleet/trip-reports":"fleet_reports", "/fleet/revenue-leakage":"fleet_reports",
  "/fleet/driver":"fleet_driver_app", "/fleet/driver-salaries":"fleet_driver_finance",
  "/fleet/finance-settings":"fleet_driver_finance", "/fleet/customer-invoices":"fleet_customer_billing",
  "/fleet/freight-reconciliation":"fleet_freight_reconciliation",
  "/settlements":"settlement_review",
};
const roles: Record<string, string[]> = {
  "/integrations/erp": financeReaders,
  "/settlements": financeReaders,
  "/users": ["OWNER"], "/branches": ["OWNER"],
  "/invoices": [...financeReaders, "APPROVER", "PURCHASE", "STORE"],
  "/email-intake": ["OWNER", "FINANCE"],
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
  "/fleet/geofences": ["OWNER", "FLEET"],
};

export function canShowNavigation(href: string, access: NavigationAccess | null): boolean {
  if (!access) return false;
  const path = href.split(/[?#]/)[0];
  const rolePath = Object.keys(roles).sort((a,b)=>b.length-a.length).find(route=>path===route||path.startsWith(`${route}/`));
  const featurePath = Object.keys(features).sort((a,b)=>b.length-a.length).find(route=>path===route||path.startsWith(`${route}/`));
  if (access.role === "DRIVER" && path !== "/fleet/driver") return false;
  if (rolePath && !roles[rolePath].includes(access.role)) return false;
  const modulePath=Object.keys(fleetModules).sort((a,b)=>b.length-a.length).find(route=>path===route||path.startsWith(`${route}/`));
  if(modulePath && access.entitlements?.features?.[fleetModules[modulePath]]?.enabled === false) return false;
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
