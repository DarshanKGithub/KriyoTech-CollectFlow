"use client";

import { Box, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { BarChart } from "@mui/x-charts/BarChart";
import { LineChart } from "@mui/x-charts/LineChart";
import type { DashboardAnalytics } from "@/components/overview-charts";
import { formatMoney } from "@/lib/finance";

const buckets: Record<string, string> = {
  NOT_OVERDUE: "Not overdue", DAYS_1_7: "1–7 days overdue",
  DAYS_8_30: "8–30 days overdue", DAYS_31_PLUS: "31+ days overdue", NO_DUE_DATE: "No due date",
};

export function OverviewPriorityChart({ aging, byStatus }: {
  aging?: DashboardAnalytics["payable_aging"];
  byStatus: Record<string, number>;
}) {
  const theme = useTheme();
  const primary = theme.palette.primary.main;
  const secondary = theme.palette.mode === "dark" ? "#A4B697" : "#607D57";
  const rows = aging
    ? aging.map(item => ({ label: buckets[item.bucket] || item.bucket, value: Number(item.amount) }))
    : [
      { label: "Processing", statuses: ["UPLOADED", "EXTRACTING"] },
      { label: "Needs review", statuses: ["REVIEW_REQUIRED"] },
      { label: "Blocked", statuses: ["EXTRACTION_FAILED", "EXCEPTION"] },
      { label: "Approval", statuses: ["MATCHED", "APPROVAL_PENDING", "APPROVED"] },
      { label: "Payment ready", statuses: ["PAYMENT_READY"] },
    ].map(item => ({ label: item.label, value: item.statuses.reduce((sum, status) => sum + (byStatus[status] || 0), 0) }));
  const hasValues = rows.some(row => row.value > 0);
  return <Box component="section" aria-label={aging ? "Outstanding invoices by due date" : "Active invoice workflow"}
    sx={{ display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0, height: "100%" }}>
    <Typography component="h2" variant="subtitle2">{aging ? "Outstanding invoices by due date" : "Active invoice workflow"}</Typography>
    <Typography variant="caption" color="text.secondary" sx={{ mb: 1 }}>
      {aging ? "Unpaid approved balances · INR" : "Invoices currently waiting at each stage"}
    </Typography>
    <Box sx={{ flex: 1, minHeight: { xs: 220, md: 0 }, minWidth: 0 }}>
      <BarChart layout="horizontal" skipAnimation hideLegend
        yAxis={[{ scaleType: "band", data: rows.map(row => row.label), width: 132,
          colorMap: { type: "ordinal", colors: aging ? [secondary, "#d28b20", "#d36c35", "#c24145", theme.palette.text.secondary] : [secondary, "#d28b20", "#c24145", "#AA8B52", primary] } }]}
        xAxis={[{ min: 0, ...(!hasValues ? { max: 1 } : {}), ...(aging ? { valueFormatter: (value: number) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value) } : { tickMinStep: 1 }) }]}
        series={[{ data: rows.map(row => row.value), label: aging ? "Outstanding balance" : "Invoices",
          valueFormatter: value => aging ? formatMoney(String(value ?? 0)) : `${value ?? 0} invoices` }]}
        grid={{ vertical: true }} borderRadius={4} margin={{ top: 4, right: 20, bottom: 4 }}
      />
    </Box>
    {!hasValues && <Typography variant="caption" color="text.secondary">{aging ? "No approved balances outstanding — all categories are zero." : "No invoices waiting — all stages are zero."}</Typography>}
  </Box>;
}

export function OverviewActivityChart({ analytics }: { analytics?: DashboardAnalytics }) {
  const theme = useTheme();
  const uploads = analytics?.daily_uploads || [];
  return <Box component="section" aria-label="Invoice uploads over the last 30 days" sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0, minWidth: 0 }}>
    <Typography component="h2" variant="subtitle2">Invoice activity</Typography>
    <Typography variant="caption" color="text.secondary" sx={{ mb: 1 }}>Daily uploads · last 30 days</Typography>
    <Box sx={{ flex: 1, minWidth: 0, minHeight: { xs: 220, md: 0 } }}>
      {uploads.length ? <LineChart skipAnimation hideLegend
        xAxis={[{ scaleType: "point", data: uploads.map(item => item.date), tickLabelInterval: (_, index) => index % 7 === 0,
          valueFormatter: (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) }]}
        yAxis={[{ min: 0, tickMinStep: 1, ...(!uploads.some(item => item.count > 0) ? { max: 1 } : {}) }]}
        series={[{ data: uploads.map(item => item.count), label: "Invoices uploaded", color: theme.palette.primary.main, area: true, showMark: false, curve: "linear", valueFormatter: value => `${value ?? 0} invoices` }]}
        grid={{ horizontal: true }} margin={{ top: 8, right: 20, bottom: 4 }}
        sx={{ "& .MuiAreaElement-root": { fillOpacity: 0.15 } }}
      /> : <Typography variant="body2" color="text.secondary" sx={{ p: 3 }}>Upload history unavailable. Refresh to try again.</Typography>}
    </Box>
  </Box>;
}
