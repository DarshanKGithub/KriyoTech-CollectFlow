"use client";

import Link from "next/link";
import { useContext } from "react";
import { WorkspaceAccessContext } from "@/components/workspace-access-context";
import { canShowNavigation } from "@/lib/navigation-access";
import { usePathname } from "next/navigation";
import { ChartNoAxesColumn, LayoutDashboard, MapPin, Route, Truck, UsersRound } from "lucide-react";

const modules = [
  { label: "Overview", href: "/fleet", icon: LayoutDashboard, matches: (path: string) => path === "/fleet" },
  { label: "Live tracking", href: "/fleet/live-tracking", icon: MapPin, matches: (path: string) => path.startsWith("/fleet/live-tracking") },
  { label: "Dispatch", href: "/fleet/dispatch", icon: Route, matches: (path: string) => ["/fleet/dispatch", "/fleet/dispatch-planner", "/fleet/orders", "/fleet/lrs", "/fleet/dock-schedule", "/fleet/create-trip", "/fleet/trips", "/fleet/alerts", "/fleet/follow-ups", "/fleet/return-loads", "/fleet/driver"].some(route => path === route || path.startsWith(`${route}/`)) },
  { label: "Fleet assets", href: "/fleet/trucks", icon: Truck, matches: (path: string) => ["/fleet/trucks", "/fleet/truck-documents", "/fleet/maintenance", "/fleet/geofences", "/fleet/reliability", "/fleet/settings"].some(route => path === route || path.startsWith(`${route}/`)) },
  { label: "Customers", href: "/fleet/customers", icon: UsersRound, matches: (path: string) => ["/fleet/customers", "/fleet/booking-history", "/fleet/customer-invoices", "/fleet/customer-portal", "/fleet/customer-notifications", "/fleet/freight-reconciliation", "/fleet/documents", "/fleet/exception-center"].some(route => path === route || path.startsWith(`${route}/`)) },
  { label: "Finance & insights", href: "/fleet/operational-reports", icon: ChartNoAxesColumn, matches: (path: string) => ["/fleet/operational-reports", "/fleet/trip-reports", "/fleet/driver-salaries", "/fleet/finance-settings", "/fleet/revenue-leakage", "/fleet/fuel"].some(route => path === route || path.startsWith(`${route}/`)) },
];

export function FleetWorkspaceNav() {
  const pathname = usePathname();
  const access = useContext(WorkspaceAccessContext);
  const current = modules.find(item => item.matches(pathname));
  return <div className="fleet-module-bar w-full border-b px-2 sm:px-4">
      <nav aria-label="Fleet workspace modules" className="flex w-full min-w-0 items-stretch gap-1 overflow-x-auto py-1.5">
        {modules.filter(item=>canShowNavigation(item.href,access)).map(item => {
          const Icon = item.icon;
          const active = item === current;
          return <Link key={item.href} href={item.href} aria-current={active ? pathname === item.href ? "page" : "location" : undefined} className="fleet-module-link">
            <Icon size={15} aria-hidden="true" />{item.label}
          </Link>;
        })}
      </nav>
  </div>;
}
