"use client";

import NextLink from "next/link";
import { Alert, Box, Button, Chip, Skeleton, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { createTheme, ThemeProvider, useTheme } from "@mui/material/styles";

import useMediaQuery from "@mui/material/useMediaQuery";
import { ArrowRight, Truck } from "lucide-react";
import { LiveData } from "@/components/live-data";
import { OverviewCharts, type DashboardAnalytics } from "@/components/overview-charts";
import { canShowNavigation, type NavigationAccess } from "@/lib/navigation-access";
import { decimalAmount, formatMoney, minorUnits } from "@/lib/finance";

export type OverviewSummary = {
  analytics?: DashboardAnalytics;
  by_status: Record<string, number>;
  monthly_volume: number;
  exceptions: number;
  exception_breakdown?: { code: string; count: number }[];
  pending_approvals: number;
};

export type FleetSnapshot = {
  active_vehicles: number;
  active_drivers: number;
  trips_in_progress: number;
  trips_awaiting_review: number;
  open_follow_ups: number;
  approved_trip_margin: string;
  tracking_available: boolean;
  live_locations: number | null;
  stale_locations: number | null;
  waiting_locations: number | null;
};

function Section({ title, action, children, priority = false }: {
  title: string;
  priority?: boolean;

  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return <Box component="section" sx={{ minWidth: 0, border: "1px solid", borderColor: "divider", borderRadius: 2, bgcolor: "background.paper", borderLeft: priority ? 3 : 1, borderLeftColor: priority ? "warning.main" : "divider", p: 1.5, display: "flex", flexDirection: "column" }}>
    <Box sx={{ position: "relative", display: "grid", alignItems: "center", minHeight: 22, mb: .5 }}>
      <Box><Typography component="h2" variant="body2" sx={{ fontWeight: 750, fontSize: 15 }}>{title}</Typography></Box>

    </Box>
    <Box sx={{ flex: 1 }}>{children}</Box>
    {action && <Box sx={{ display: "flex", justifyContent: "flex-end", mt: .5 }}>{action}</Box>}
  </Box>;
}

function Metric({ label, value, href }: { label: string; value: React.ReactNode; href?: string }) {
  const content = <Box sx={{ height: "100%", px: 1.5, py: .75, borderInlineStart: "1px solid #ffffff35", ...(href ? { "&:hover": { bgcolor: "#ffffff14" } } : {}) }}>
    <Typography sx={{ color: "#d4e7e0", fontSize: 13 }}>{label}</Typography>
    <Typography sx={{ mt: .25, fontSize: { xs: 22, sm: 28 }, lineHeight: 1.12, fontWeight: 750, fontVariantNumeric: "tabular-nums" }}>{value}</Typography>
  </Box>;
  return href ? <Box component={NextLink} href={href} sx={{ color: "inherit", textDecoration: "none", minWidth: 0 }}>{content}</Box> : content;
}

export function OverviewVisualDashboard({ summary, profile, fleet, fleetMessage, loading, refreshing, message, days, onDaysChange, onRefresh }: {
  summary: OverviewSummary | null;
  profile: NavigationAccess | null;
  loading: boolean;
  fleet: FleetSnapshot | null;
  fleetMessage: string;
  refreshing: boolean;
  message: string;
  days: 7 | 30 | 90;
  onDaysChange: (days: 7 | 30 | 90) => void;
  onRefresh: (silent?: boolean) => Promise<void>;
}) {
  const parentTheme = useTheme();
  const fillWindow = useMediaQuery("(min-width: 900px) and (min-height: 760px)");

  const theme = createTheme(parentTheme, { breakpoints: { values: { xs: 0, sm: 640, md: 900, lg: 1024, xl: 1280 } } });
  const hasFleet = canShowNavigation("/fleet", profile);
  const finance = canShowNavigation("/payments", profile);
  const aging = finance ? summary?.analytics?.payable_aging : undefined;
  const outstanding = aging ? decimalAmount(aging.reduce((sum, row) => sum + minorUnits(row.amount), 0n)) : null;
  const tracking = [
    { id: "live", label: "Live location", value: fleet?.live_locations ?? 0, color: parentTheme.palette.success.main },
    { id: "stale", label: "Location out of date", value: fleet?.stale_locations ?? 0, color: parentTheme.palette.warning.main },
    { id: "waiting", label: "No GPS yet", value: fleet?.waiting_locations ?? 0, color: parentTheme.palette.text.secondary },
  ];
  const trackedTrips = tracking.reduce((sum, row) => sum + row.value, 0);
  const canViewInvoices = canShowNavigation("/invoices", profile);
  const canReviewAttention = canShowNavigation("/attention", profile);
  const chartPaths = ["/invoices", "/payments", "/exceptions"].filter(path => canShowNavigation(path, profile));
  const analytics = summary?.analytics;
  const chartAnalytics = finance || !analytics ? analytics : { ...analytics, payable_aging: undefined };
  const invoiceStatuses = summary?.by_status || {};
  const pendingReview = (invoiceStatuses.REVIEW_REQUIRED || 0) + (invoiceStatuses.EXTRACTION_FAILED || 0) + (invoiceStatuses.EXCEPTION || 0);
  const signIn = /sign in|session/i.test(message);

  const tasks = summary ? [
    { label: "Invoice issues", count: summary.exceptions, href: "/exceptions" },
    ...(canShowNavigation("/approvals", profile) ? [{ label: "Invoices to approve", count: summary.pending_approvals, href: "/approvals" }] : []),
    ...(hasFleet && fleet ? [{ label: "Trips to review or follow up", count: fleet.trips_awaiting_review + fleet.open_follow_ups, href: "/attention" }] : []),
  ] : [];
  const attention = <Section title="Needs attention" priority>
    {!summary ? <Typography variant="body2" color="text.secondary">Loading tasks…</Typography>
      : tasks.every(task => task.count === 0) ? <Typography variant="body2" color="text.secondary">You’re all caught up.</Typography>
      : <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0 }}>
        {tasks.map(task => {
          const content = <>
            <Typography variant="body2" sx={{ flex: 1, fontWeight: 600 }}>{task.label}</Typography>
            <Chip size="small" color={task.count > 0 ? "warning" : "default"} variant="outlined" label={task.count} />
            {canShowNavigation(task.href, profile) && <ArrowRight size={14} aria-hidden />}
          </>;
          const rowStyle = { display: "flex", alignItems: "center", gap: 1, py: .65, px: .75, borderRadius: 1 };
          return <Box component="li" key={task.href}>
            {canShowNavigation(task.href, profile)
              ? <Box component={NextLink} href={task.href} sx={{ ...rowStyle, color: "inherit", textDecoration: "none", "&:hover": { bgcolor: "action.hover" } }}>{content}</Box>
              : <Box sx={rowStyle}>{content}</Box>}
          </Box>;
        })}
      </Box>}
  </Section>;

  const uploadRange = <ToggleButtonGroup size="small" exclusive value={days} aria-label="Invoice upload date range"
          disabled={refreshing && analytics?.days !== days} onChange={(_, value: 7 | 30 | 90 | null) => { if (value !== null) onDaysChange(value); }}>
          <ToggleButton value={7}>7 days</ToggleButton>
          <ToggleButton value={30}>30 days</ToggleButton>
          <ToggleButton value={90}>90 days</ToggleButton>
        </ToggleButtonGroup>;

  const statusCards = <>
    {attention}
    {hasFleet && <Section title="Truck tracking" action={canShowNavigation("/fleet/live-tracking", profile) && <Button component={NextLink} href="/fleet/live-tracking" size="small" aria-label="Open live tracking" endIcon={<ArrowRight size={13}/>}>Open live map</Button>}>
        {loading ? <Skeleton variant="rounded" height={110} /> : fleet?.tracking_available ? trackedTrips > 0
          ? <Box>
              <Typography sx={{ fontSize: 25, lineHeight: 1.2, fontWeight: 700 }}>{trackedTrips}</Typography>
              <Typography variant="caption" color="text.secondary">Trips with tracking enabled</Typography>
              <Box aria-hidden="true" sx={{ display: "flex", height: 7, borderRadius: 4, overflow: "hidden", my: 1.25 }}>
                {tracking.filter(row => row.value > 0).map(row => <Box key={row.id} sx={{ flex: row.value, bgcolor: row.color }} />)}
              </Box>
              <Box component="ul" aria-label="Trip location counts" sx={{ listStyle: "none", m: 0, p: 0 }}>
                {tracking.map(row => <Box component="li" key={row.id} sx={{ display: "flex", alignItems: "center", gap: .75, py: .35 }}>
                  <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: row.color }} />
                  <Typography variant="body2" sx={{ flex: 1 }}>{row.label}</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{row.value}</Typography>
                </Box>)}
              </Box>
            </Box>
          : <Typography variant="body2" color="text.secondary">No trips in the tracking feed.</Typography>
          : <Typography role="status" variant="body2" color="text.secondary">{fleetMessage || "Trip location status is unavailable."}</Typography>}
      </Section>}
  </>;

  return <ThemeProvider theme={theme}><Box component="main" sx={{ flex: 1, minWidth: 0, bgcolor: "background.default", color: "text.primary", p: { xs: 1, sm: 1.5 }, display: "flex", flexDirection: "column", gap: 1, "& .MuiChartsAxis-tickLabel": { fill: "currentColor", opacity: .82 }, "& .MuiChartsAxis-line, & .MuiChartsAxis-tick, & .MuiChartsGrid-line": { stroke: "currentColor", opacity: .14 } }}>
    {refreshing && analytics && analytics.days !== days && <span role="status" className="sr-only">Loading {days} days of invoice uploads</span>}
    {message && <Alert severity="warning" action={signIn ? <Button component={NextLink} href="/login">Sign in</Button> : <Button disabled={refreshing} onClick={() => void onRefresh()}>Try again</Button>}>{message}{summary ? " Showing the last loaded data." : ""}</Alert>}

    <Box component="header" sx={{ bgcolor: "#123e35", color: "#fff", borderRadius: 2.5, px: { xs: 1.5, sm: 2.25 }, py: 1.25 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, mb: .75, flexWrap: "wrap" }}>
        <Typography component="h1" sx={{ fontSize: { xs: 23, sm: 27 }, fontWeight: 750, letterSpacing: "-.025em" }}>Operations overview</Typography>
        {canShowNavigation("/fleet/create-trip", profile) && <Button component={NextLink} href="/fleet/create-trip" variant="contained" size="small" startIcon={<Truck size={15}/>} sx={{ bgcolor: "#dcf5e7", color: "#123e35", "&:hover": { bgcolor: "#c7eed9" } }}>Create trip</Button>}
        {!canShowNavigation("/fleet/create-trip", profile) && canViewInvoices && <Button component={NextLink} href="/invoices" size="small" variant="contained" sx={{ bgcolor: "#dcf5e7", color: "#123e35", "&:hover": { bgcolor: "#c7eed9" } }}>Open invoices</Button>}
      </Box>
    {loading ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(4,1fr)" }, gap: 1 }}>{[0, 1, 2, 3].map(key => <Skeleton key={key} variant="rounded" height={65}/>)}</Box> : <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(4,minmax(0,1fr))" }, gap: 1 }}>
      {hasFleet && <>

        <Metric label="Trips underway" value={fleet?.trips_in_progress ?? "—"} href={canShowNavigation("/fleet/trips", profile) ? "/fleet/trips" : undefined}/>
        <Metric label="Active vehicles" value={fleet?.active_vehicles ?? "—"} href={canShowNavigation("/fleet/trucks", profile) ? "/fleet/trucks" : undefined}/>
        <Metric label="Active drivers" value={fleet?.active_drivers ?? "—"} href={canShowNavigation("/fleet/drivers", profile) ? "/fleet/drivers" : undefined}/>
        {finance ? <Metric label="Supplier balance" value={outstanding === null ? "—" : formatMoney(outstanding)} href="/payments"/> : canViewInvoices && <Metric label="Invoices this month" value={summary?.monthly_volume ?? "—"} href="/invoices"/>}
      </>}
      {!hasFleet && <>
        <Metric label="Invoices this month" value={summary?.monthly_volume ?? "—"} href={canViewInvoices ? "/invoices" : undefined}/>
        <Metric label="Needs review" value={summary ? pendingReview : "—"} href={canReviewAttention ? "/attention" : undefined}/>
        <Metric label="Pending approvals" value={summary?.pending_approvals ?? "—"} href={canShowNavigation("/approvals", profile) ? "/approvals" : undefined}/>
        {finance && <Metric label="Outstanding balance" value={outstanding === null ? "—" : formatMoney(outstanding)} href="/payments"/>}
      </>}
    </Box>}

    </Box>

    <Box aria-label="Workspace overview" sx={{ display: "grid", minHeight: 0, gap: 1.25, gridTemplateColumns: { xs: "minmax(0,1fr)", md: summary && (canViewInvoices || finance) ? "minmax(215px, 24%) minmax(0, 1fr)" : "minmax(0,1fr)" }, ...(fillWindow && summary ? { flex: 1, gridTemplateRows: "minmax(0,1fr)" } : {}) }}>
      {(canViewInvoices || finance) && summary
        ? <OverviewCharts byStatus={invoiceStatuses} exceptions={summary.exception_breakdown ?? []} analytics={chartAnalytics} allowedPaths={chartPaths} uploadRange={uploadRange} fillWindow={fillWindow} statusCards={statusCards} />
        : statusCards}
    </Box>

    <LiveData compact onRefresh={() => onRefresh(true)} interval={30000} paused={refreshing}/>
  </Box></ThemeProvider>;
}
