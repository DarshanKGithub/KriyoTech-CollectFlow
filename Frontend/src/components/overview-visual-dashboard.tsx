"use client";

import type { ReactNode } from "react";
import NextLink from "next/link";
import { Alert, Box, Button, Chip, Skeleton, Stack, Typography } from "@mui/material";
import { createTheme, ThemeProvider, useTheme } from "@mui/material/styles";
import { financeTokens as baseFinanceTokens } from "@/lib/finance-design";
import { BarChart } from "@mui/x-charts/BarChart";
import { PieChart } from "@mui/x-charts/PieChart";
import { ArrowUpRight, CircleAlert } from "lucide-react";
import { OverviewPriorityChart } from "@/components/overview-priority-chart";
import { LiveData } from "@/components/live-data";
import type { DashboardAnalytics } from "@/components/overview-charts";
import { canShowNavigation, type NavigationAccess } from "@/lib/navigation-access";
import { decimalAmount, formatMoney, minorUnits } from "@/lib/finance";

export type OverviewSummary = {
  analytics?: DashboardAnalytics; by_status: Record<string, number>;
  monthly_volume: number; exceptions: number; pending_approvals: number;
  payment_ready: number; payment_ready_value: string | number;
};

function Panel({ children, area, label }: { children: ReactNode; area: string; label: string }) {
  return <Box component="section" aria-label={label} sx={{ gridArea: { md: area }, border: "1px solid", borderColor: "divider", borderRadius: "16px", p: { xs: 2, md: 2.25 }, minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column", bgcolor: "background.paper", boxShadow: "0 2px 8px #172b2705", position: "relative" }}>{children}</Box>;
}

export function OverviewVisualDashboard({ summary, profile, loading, refreshing, message, onRefresh }: {
  summary: OverviewSummary | null; profile: NavigationAccess | null; loading: boolean;
  refreshing: boolean; message: string; onRefresh: (silent?: boolean) => Promise<void>;
}) {
  const parentTheme = useTheme();
  const financeTokens = {
    ...baseFinanceTokens,
    brand: parentTheme.palette.primary.main,
    ink: parentTheme.palette.text.primary,
    muted: parentTheme.palette.text.secondary,
    border: parentTheme.palette.divider,
    warning: parentTheme.palette.warning.main,
    info: parentTheme.palette.info.main,
  };
  const theme = createTheme(parentTheme, {breakpoints:{values:{xs:0,sm:640,md:900,lg:1024,xl:1280}}});
  const finance = canShowNavigation("/payments", profile);
  const aging = finance ? summary?.analytics?.payable_aging : undefined;
  const outstanding = aging ? decimalAmount(aging.reduce((sum, row) => sum + minorUnits(row.amount), 0n)) : null;
  const overdue = aging ? decimalAmount(aging.filter(row => !["NOT_OVERDUE", "NO_DUE_DATE"].includes(row.bucket)).reduce((sum, row) => sum + minorUnits(row.amount), 0n)) : null;
  const uploads = summary?.analytics?.daily_uploads || [];
  const weeks = Array.from({ length: Math.ceil(uploads.length / 7) }, (_, index) => {
    const days = uploads.slice(index * 7, index * 7 + 7);
    return { date: days[0].date, count: days.reduce((sum, day) => sum + day.count, 0) };
  });
  const totalUploads = uploads.reduce((sum, day) => sum + day.count, 0);
  const previous = summary?.analytics?.previous_uploads;
  const change = previous ? Math.round((totalUploads - previous) / previous * 100) : null;
  const statuses = summary?.by_status || {};
  const groups = [
    { label: "Processing", keys: ["UPLOADED", "EXTRACTING"], color: financeTokens.info },
    { label: "Review / blocked", keys: ["REVIEW_REQUIRED", "EXTRACTION_FAILED", "EXCEPTION"], color: financeTokens.warning },
    { label: "Approval", keys: ["MATCHED", "APPROVAL_PENDING", "APPROVED"], color: "#6d9989" },
    { label: "Ready / exported", keys: ["PAYMENT_READY", "EXPORTED"], color: financeTokens.brand },
  ].map((group, id) => ({ id, label: group.label, color: group.color, value: group.keys.reduce((sum, key) => sum + (statuses[key] || 0), 0) }));
  const active = groups.reduce((sum, group) => sum + group.value, 0);
  const signIn = /sign in|session/i.test(message);

  return <ThemeProvider theme={theme}><Box component="main" sx={{ flex: 1, minHeight: 0, minWidth: 0, bgcolor: "background.default", color: "text.primary", p: { xs: 2, md: 2.5 }, display: "flex", flexDirection: "column", gap: 1.5, "@media (min-width:900px) and (max-height:720px)": { p: 1.5, gap: 1 }, "& .MuiChartsAxis-tickLabel": { fill: financeTokens.muted }, "& .MuiChartsAxis-line, & .MuiChartsAxis-tick": { stroke: financeTokens.border }, "& .MuiChartsGrid-line": { stroke: financeTokens.border, strokeDasharray: "3 5" }, "& .text-slate-500": { color: financeTokens.muted }, "& > .mt-3": { marginTop: 0, flexShrink: 0 } }}>
    <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", flexShrink: 0, gap: 1 }}>
      <Box><Typography component="h1" sx={{ fontSize: { xs: 22, md: 25 }, fontWeight: 600, letterSpacing: "-0.04em" }}>Workspace overview<span style={{ color: financeTokens.brand }}>.</span></Typography><Typography variant="caption" color="text.secondary">A clear view of your invoices and money.</Typography></Box>
      {canShowNavigation("/invoices", profile) && <Button component={NextLink} href="/invoices" variant="outlined" endIcon={<ArrowUpRight size={14} />}>Invoices</Button>}
    </Stack>
    {message && <Alert severity="warning" action={signIn ? <Button component={NextLink} href="/login">Sign in</Button> : <Button disabled={refreshing} onClick={() => void onRefresh()}>Retry</Button>}>{message}{summary ? " Showing previous data." : ""}</Alert>}
    {loading ? <Box sx={{ flex: 1, display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 1.5, minHeight: 0 }}>{[0, 1, 2, 3].map(key => <Skeleton key={key} variant="rounded" sx={{ height: "100%", minHeight: 100, bgcolor: "action.selected" }} />)}</Box> : summary && <>
      <Box sx={{ flex: 1, minHeight: 0, display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", md: "repeat(12,minmax(0,1fr))" }, gridTemplateRows: { md: "minmax(0,1fr) minmax(0,1fr)" }, gridTemplateAreas: { md: '"activity activity activity activity activity activity activity position position position position position" "attention attention attention workflow workflow workflow workflow aging aging aging aging aging"' }, "& > section": { minHeight: { xs: 240, md: 0 } } }}>
        <Panel area="activity" label="Invoice activity">
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}><Typography component="h2" variant="subtitle2">Invoice activity</Typography><Chip size="small" label="Last 30 days" sx={{ height: 24, bgcolor: "action.hover", color: "text.secondary", fontSize: 10 }} /></Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5 }}><Typography sx={{ fontSize: 25, fontWeight: 500 }}>{totalUploads}<Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>uploads</Typography></Typography>{change !== null && <Chip size="small" label={`${change > 0 ? "+" : ""}${change}% vs previous 30 days`} sx={{ height: 20, fontSize: 10, bgcolor: "action.selected", color: financeTokens.brand }} />}</Stack>
          <Box sx={{ flex: 1, minHeight: { xs: 160, md: 0 }, minWidth: 0 }}>{weeks.length ? <BarChart skipAnimation hideLegend borderRadius={7} series={[{ data: weeks.map(week => week.count), label: "Invoices uploaded", color: financeTokens.brand }]} xAxis={[{ scaleType: "band", data: weeks.map(week => week.date), categoryGapRatio: 0.45, valueFormatter: (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) }]} yAxis={[{ min: 0, tickMinStep: 1, ...(!totalUploads ? { max: 1 } : {}), width: 30 }]} margin={{ top: 8, right: 8, bottom: 0 }} /> : <Typography variant="caption">Upload history unavailable.</Typography>}</Box>
          <Typography variant="caption" color="text.secondary">Uploads grouped into seven-day periods; final period may be shorter.</Typography>
        </Panel>
        <Panel area="position" label="Financial position">
          <Typography component="h2" variant="subtitle2">{finance ? "Outstanding approved invoices" : "This month"}</Typography>
          <Typography sx={{ fontSize: { xs: 29, md: "clamp(24px,2.5vw,38px)" }, fontWeight: 500, letterSpacing: "-0.04em", my: 1, fontVariantNumeric: "tabular-nums", overflowWrap: "anywhere" }}>{finance ? outstanding === null ? "Unavailable" : formatMoney(outstanding) : summary.monthly_volume}</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, flex: 1, minHeight: 0 }}>
            {[{ label: finance ? "Ready for payment" : "Open exceptions", value: finance ? formatMoney(String(summary.payment_ready_value)) : String(summary.exceptions), color: financeTokens.brand }, { label: finance ? "Overdue balance" : "Pending approvals", value: finance ? overdue === null ? "Unavailable" : formatMoney(overdue) : String(summary.pending_approvals), color: financeTokens.warning }].map(item => <Box key={item.label} sx={{ p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: "12px", bgcolor: "action.hover", display: "flex", flexDirection: "column", justifyContent: "space-between" }}><Typography variant="caption" color="text.secondary">{item.label}</Typography><Typography sx={{ fontSize: { xs: 18, md: 21 }, color: item.color, fontVariantNumeric: "tabular-nums", overflowWrap: "anywhere" }}>{item.value}</Typography><Box sx={{ height: 3, width: "60%", bgcolor: item.color, opacity: 0.55, borderRadius: 2, mt: 1 }} /></Box>)}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>{finance ? "Recorded invoice balances · INR" : "Current workspace records"}</Typography>
        </Panel>
        <Panel area="attention" label="Needs attention">
          <Box sx={{ width: 44, height: 44, borderRadius: "50%", display: "grid", placeItems: "center", color: financeTokens.brand, bgcolor: "action.selected", mb: 1 }}><CircleAlert size={23} /></Box>
          <Typography component="h2" sx={{ fontSize: 19, fontWeight: 500 }}>Needs attention</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}><strong style={{ color: financeTokens.ink }}>{summary.exceptions}</strong> open exceptions</Typography>
          {canShowNavigation("/approvals", profile) && <Typography variant="body2" color="text.secondary"><strong style={{ color: financeTokens.ink }}>{summary.pending_approvals}</strong> pending approvals</Typography>}
          {canShowNavigation("/attention", profile) && <Button component={NextLink} href="/attention" variant="contained" size="small" sx={{ mt: "auto", alignSelf: "flex-start" }} endIcon={<ArrowUpRight size={13} />}>Review tasks</Button>}
        </Panel>
        <Panel area="workflow" label="Invoice workflow distribution">
          <Stack direction="row" sx={{ justifyContent: "space-between" }}><Typography component="h2" variant="subtitle2">Active workflow</Typography><Typography variant="caption" color="text.secondary">{active} invoices</Typography></Stack>
          <Box sx={{ flex: 1, minHeight: { xs: 140, md: 0 }, position: "relative" }}><PieChart skipAnimation hideLegend series={[{ data: active ? groups : [{ id: "empty", value: 1, color: financeTokens.border, label: "No active invoices" }], innerRadius: "65%", outerRadius: "90%", paddingAngle: 4, cornerRadius: 4, valueFormatter: item => active ? `${item.value} invoices` : "No active invoices" }]} margin={{ top: 8, bottom: 8, left: 8, right: 8 }} /><Box sx={{ position: "absolute", inset: 0, pointerEvents: "none", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}><Typography sx={{ fontSize: 24 }}>{active}</Typography><Typography variant="caption" color="text.secondary">active</Typography></Box></Box>
          <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0.5 }}>{groups.map(group => <Typography key={group.id} variant="caption" color="text.secondary" sx={{ fontSize: 10 }}><span style={{ color: group.color }}>●</span> {group.label} {group.value}</Typography>)}</Box>
        </Panel>
        <Panel area="aging" label="Invoice priorities"><OverviewPriorityChart aging={aging} byStatus={statuses} /></Panel>
      </Box>
      <LiveData compact onRefresh={() => onRefresh(true)} interval={30000} paused={refreshing} />
    </>}
  </Box></ThemeProvider>;
}
