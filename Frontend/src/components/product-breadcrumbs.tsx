"use client";

import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import NextLink from "next/link";
import { usePathname } from "next/navigation";

const labels: Record<string, string> = { fleet: "Fleet & trips", "admin-console": "Administration", erp: "ERP connections", grns: "Goods receipts", "create-trip": "Create a trip", "driver-salaries": "Driver salaries", "customer-invoices": "Customer invoices", "trip-reports": "Trip reports", "email-intake": "Email intake", "ai-review": "Invoice review" };
export function ProductBreadcrumbs({ allowedPaths }: { allowedPaths?: string[] }) {
  const pathname = usePathname();
  const parts = pathname.split("/").filter(Boolean);
  const admin = parts[0] === "admin-console";
  const root = admin ? "/admin-console" : "/";
  return <Breadcrumbs aria-label="Page location" sx={{ fontSize: 12, minWidth: 0, "& ol": { flexWrap: "wrap" } }}>
    {allowedPaths && !allowedPaths.includes(root) ? <Typography variant="caption">Workspace</Typography> : <Link component={NextLink} href={root} underline="hover" color="inherit">{admin ? "Admin home" : "Overview"}</Link>}
    {parts.filter((part, index) => !(admin && index === 0)).map((part, index, entries) => {
      const actualIndex = admin ? index + 1 : index;
      const href = `/${parts.slice(0, actualIndex + 1).join("/")}`;
      const name = /^[0-9a-f]{8}-/i.test(part) ? "Record details" : labels[part] || part.replaceAll("-", " ").replace(/^./, char => char.toUpperCase());
      return index === entries.length - 1 || (allowedPaths && !allowedPaths.includes(href)) ? <Typography key={href} color="text.primary" sx={{ fontSize: 12 }} aria-current={index === entries.length - 1 ? "page" : undefined}>{name}</Typography> : <Link component={NextLink} key={href} href={href} underline="hover" color="inherit">{name}</Link>;
    })}
  </Breadcrumbs>;
}
