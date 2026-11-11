"use client";

import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";

const labels: Record<string, string> = { fleet: "Fleet & trips", "admin-console": "Administration", erp: "ERP connections", grns: "Goods receipts", "create-trip": "Create a trip", "driver-salaries": "Driver salaries", "customer-invoices": "Customer invoices", "trip-reports": "Trip reports", "email-intake": "Email intake", "ai-review": "Invoice review" };
export function ProductBreadcrumbs({ allowedPaths, compact = false }: { allowedPaths?: string[]; compact?: boolean }) {
  const pathname = usePathname();
  const parts = pathname.split("/").filter(Boolean);
  const admin = parts[0] === "admin-console";
  const root = admin ? "/admin-console" : "/";
  const rootLabel = admin ? "Admin home" : "Overview";
  const isRoot = pathname === root;
  return <Breadcrumbs aria-label="Page location" separator={compact ? <ChevronRight size={14} aria-hidden /> : undefined} sx={compact ? {
    fontSize: 13, color: "text.secondary", minWidth: 0,
    "& ol": { flexWrap: "nowrap" },
    "& .MuiBreadcrumbs-li": { minWidth: 0 },
    "& .MuiBreadcrumbs-separator": { mx: .75 },
    "@media (max-width: 639px)": { "& .MuiBreadcrumbs-li:not(:last-child), & .MuiBreadcrumbs-separator": { display: "none" } },
  } : { fontSize: 12, minWidth: 0, "& ol": { flexWrap: "wrap" } }}>
    {compact && isRoot ? <Typography aria-current="page" sx={{ fontSize: 15, fontWeight: 700, color: "text.primary" }}>{rootLabel}</Typography>
      : allowedPaths && !allowedPaths.includes(root) ? <Typography variant="caption">Workspace</Typography>
      : <Link component={NextLink} href={root} underline="hover" color="inherit" sx={compact ? { display: "inline-flex", alignItems: "center", gap: .65, whiteSpace: "nowrap" } : undefined}>{compact && <Home size={15} aria-hidden />}{rootLabel}</Link>}
    {parts.filter((part, index) => !(admin && index === 0)).map((part, index, entries) => {
      const actualIndex = admin ? index + 1 : index;
      const href = `/${parts.slice(0, actualIndex + 1).join("/")}`;
      const name = /^[0-9a-f]{8}-/i.test(part) ? "Record details" : labels[part] || part.replaceAll("-", " ").replace(/^./, char => char.toUpperCase());
      const current = index === entries.length - 1;
      return current || (allowedPaths && !allowedPaths.includes(href)) ? <Typography key={href} color={current ? "text.primary" : "text.secondary"} noWrap={compact} sx={{ fontSize: compact && current ? 15 : 12, fontWeight: compact && current ? 700 : undefined }} aria-current={current ? "page" : undefined}>{name}</Typography> : <Link component={NextLink} key={href} href={href} underline="hover" color="inherit" sx={compact ? { display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } : undefined}>{name}</Link>;
    })}
  </Breadcrumbs>;
}
