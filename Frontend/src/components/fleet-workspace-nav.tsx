"use client";

import { AppLink } from "@/components/product-ui";
import { usePathname } from "next/navigation";
import { ChartNoAxesColumn, Fuel, LayoutDashboard, MapPin, Route, Truck, UsersRound } from "lucide-react";

const modules = [
  { label: "Overview", href: "/fleet", icon: LayoutDashboard, matches: (path: string) => path === "/fleet" },
  { label: "Live tracking", href: "/fleet/live-tracking", icon: MapPin, matches: (path: string) => path.startsWith("/fleet/live-tracking") },
  { label: "Dispatch", href: "/fleet/dispatch", icon: Route, matches: (path: string) => ["/fleet/dispatch", "/fleet/dispatch-planner", "/fleet/orders", "/fleet/dock-schedule", "/fleet/create-trip", "/fleet/trips", "/fleet/alerts", "/fleet/follow-ups", "/fleet/return-loads", "/fleet/driver"].some(route => path === route || path.startsWith(`${route}/`)) },
  { label: "Fleet assets", href: "/fleet/trucks", icon: Truck, matches: (path: string) => ["/fleet/trucks", "/fleet/truck-documents", "/fleet/maintenance", "/fleet/geofences", "/fleet/reliability", "/fleet/settings"].some(route => path === route || path.startsWith(`${route}/`)) },
  { label: "Customers", href: "/fleet/customers", icon: UsersRound, matches: (path: string) => ["/fleet/customers", "/fleet/booking-history", "/fleet/customer-invoices", "/fleet/customer-portal", "/fleet/customer-notifications", "/fleet/freight-reconciliation", "/fleet/documents", "/fleet/exception-center"].some(route => path === route || path.startsWith(`${route}/`)) },
  { label: "Finance & insights", href: "/fleet/operational-reports", icon: ChartNoAxesColumn, matches: (path: string) => ["/fleet/operational-reports", "/fleet/trip-reports", "/fleet/driver-salaries", "/fleet/finance-settings", "/fleet/revenue-leakage", "/fleet/fuel"].some(route => path === route || path.startsWith(`${route}/`)) },
];

export function FleetWorkspaceNav() {
  const pathname = usePathname();
  const current = modules.find(item => item.matches(pathname));
  return <div className="fleet-module-bar border-b border-slate-200/80 bg-white/90 px-4 sm:px-6 lg:px-8">
    <div className="mx-auto flex min-h-14 max-w-[1680px] items-center justify-between gap-5">
      <nav aria-label="Fleet workspace modules" className="flex min-w-0 items-center gap-1 overflow-x-auto py-2">
        {modules.map(item => {
          const Icon = item.icon;
          const active = item === current;
          return <AppLink key={item.href} href={item.href} aria-current={active && pathname === item.href ? "page" : undefined} className={`inline-flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-xs font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest ${active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"}`}>
            <Icon size={15} aria-hidden="true" />{item.label}
          </AppLink>;
        })}
      </nav>
      <div className="hidden shrink-0 text-[10px] font-semibold uppercase tracking-[.16em] text-slate-400 md:block">
        Fleet operations
      </div>
    </div>
  </div>;
}
