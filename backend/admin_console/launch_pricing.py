"""Recommended India SME launch rates, reviewed 6 November 2026.

Monthly/quarterly/annual amounts are in paise. Annual billing costs ten monthly
payments. Usage limits and entitlements are configured separately.
"""
PLAN_PRICES = {
    "trial": (0, 0, 0),
    "starter": (149900, 449700, 1499000),
    "growth": (349900, 1049700, 3499000),
    "control": (599900, 1799700, 5999000),
    "reconcile": (49900, 149700, 499000),
    "settleview": (49900, 149700, 499000),
    "transport": (249900, 749700, 2499000),
    "driverfinance": (79900, 239700, 799000),
}
SOLUTION_PLANS = {
    "reconcile": {"name": "Reconcile", "description": "Bank reconciliation and payment tracking. Settlement report review is a separate package.",
        "features": {"payment_tracking"}},
    "settleview": {"name": "SettleView", "description": "Settlement report review, including the shared payment workspace required for reconciliation evidence.",
        "features": {"payment_tracking", "settlement_review"}},
    "transport": {"name": "Transport", "description": "Transport operations package with tracking, dispatch, trips, fuel, maintenance and customer shipment tools. DriverFinance is separate.",
        "features": {"fleet_management", "fleet_tracking", "fleet_geofencing", "fleet_dispatch", "fleet_trips", "fleet_assets", "fleet_fuel", "fleet_maintenance", "fleet_documents", "fleet_orders", "fleet_return_loads", "fleet_docks", "fleet_exceptions", "fleet_portal", "fleet_notifications", "fleet_reports", "fleet_driver_app"}},
    "driverfinance": {"name": "DriverFinance", "description": "Driver salaries, advances and settlements, customer invoicing/collections, and freight expense reconciliation. Uses shared fleet records; transport execution is a separate package.",
        "features": {"fleet_management", "fleet_driver_finance", "fleet_customer_billing", "fleet_freight_reconciliation"}},
}
REVIEW_DATE = "2026-11-06"
REASON = "India SME launch pricing reviewed against official Zoho Books, Zoho Expense, Fleetio, Simply Fleet and SuperProcure pricing pages."
