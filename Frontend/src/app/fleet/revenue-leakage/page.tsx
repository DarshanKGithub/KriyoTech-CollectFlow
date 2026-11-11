"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, LinearProgress, Paper, Stack, TextField, Typography } from "@mui/material";
import { Clock3, FileText, RefreshCw, Search, TriangleAlert } from "lucide-react";
import { AppLink } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { apiFetch } from "@/lib/api";

type LeakageItem = {
  id: string; issue: string; message: string; next_action: string;
  trip_number: string; vehicle: string; customer: string; order_number: string;
  expected_amount?: string | null; approved_trip_revenue?: string; invoice_number?: string | null;
  invoice_amount?: string; paid_amount?: string; outstanding_amount?: string; collection_amount?: string;
  due_date?: string; reasons?: string[];
};
type Report = { as_of: string; delivered_trip_count: number; exception_count: number; counts: Record<string, number>; items: LeakageItem[] };
const missingInvoice = "UNBILLED_DELIVERY";
const overduePayment = "OVERDUE_RECEIVABLE";
const otherIssues = "other";
const views = [
  { value: missingInvoice, label: "Missing invoices", icon: FileText, tone: "bg-amber-50 text-amber-800" },
  { value: overduePayment, label: "Overdue payments", icon: Clock3, tone: "bg-rose-50 text-rose-700" },
  { value: otherIssues, label: "Other issues", icon: TriangleAlert, tone: "bg-slate-100 text-slate-700" },
] as const;
type IssueView = typeof views[number]["value"];
const issueLabels: Record<string, string> = {
  FREIGHT_REVENUE_VARIANCE: "Freight revenue differs",
  MISSING_APPROVED_FREIGHT_REVENUE: "Approved revenue missing",
  INVOICE_AMOUNT_VARIANCE: "Invoice amount differs",
  PARTIAL_CUSTOMER_COLLECTION: "Partly paid invoice",
  COLLECTION_NOT_BANK_RECONCILED: "Bank payment needs matching",
};
const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const money = (value?: string | null) => value == null ? "Not set" : currency.format(Number(value));
const dateLabel = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", { dateStyle: "medium" });
const isOther = (item: LeakageItem) => item.issue !== missingInvoice && item.issue !== overduePayment;

function amountFor(item: LeakageItem): [string, string | null | undefined] {
  switch (item.issue) {
    case missingInvoice: return ["Expected invoice amount", item.expected_amount];
    case overduePayment:
    case "PARTIAL_CUSTOMER_COLLECTION": return ["Still due", item.outstanding_amount];
    case "INVOICE_AMOUNT_VARIANCE": return ["Invoice amount", item.invoice_amount];
    case "COLLECTION_NOT_BANK_RECONCILED": return ["Payment received", item.collection_amount];
    default: return ["Approved trip revenue", item.approved_trip_revenue];
  }
}

export default function FleetRevenueLeakagePage() {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [view, setView] = useState<IssueView>(missingInvoice);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/fleet/revenue-leakage?view=billing");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || data.detail || "Could not load revenue leakage review.");
      setReport(data);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load revenue leakage review.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const missingCount = report?.counts[missingInvoice] ?? 0;
  const overdueCount = report?.counts[overduePayment] ?? 0;
  const counts = {
    [missingInvoice]: missingCount,
    [overduePayment]: overdueCount,
    [otherIssues]: (report?.exception_count ?? 0) - missingCount - overdueCount,
  };
  const query = search.trim().toLowerCase();
  const viewRows = (report?.items ?? []).filter(item => view === otherIssues ? isOther(item) : item.issue === view);
  const filtered = viewRows.filter(item => [item.customer, item.trip_number, item.order_number, item.invoice_number, item.vehicle, issueLabels[item.issue]]
    .join(" ").toLowerCase().includes(query));
  const page = useListPagination(filtered, `${view}:${search}`, "Revenue issues");
  const currentView = views.find(item => item.value === view);
  const missingView = view === missingInvoice;
  const overdueView = view === overduePayment;
  const total = counts[view];

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Finance</Typography>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 750 }}>Revenue leakage</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Find delivered trips that need invoices and customer payments that are past due.</Typography>
      </Box>
      <Button variant="outlined" onClick={() => void load()} disabled={loading} startIcon={<RefreshCw size={16}/>}>Refresh</Button>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {loading && <LinearProgress aria-label="Loading revenue leakage report"/>}
    {report && <>
      <Box role="group" aria-label="Revenue issue views" className="grid gap-3 sm:grid-cols-3">
        {views.map(({ value, label, icon: Icon, tone }) => <Button key={value} variant="outlined" aria-pressed={view === value}
          onClick={() => { setView(value); setSearch(""); }}
          sx={{ justifyContent: "space-between", gap: 1, p: 2, bgcolor: view === value ? "action.selected" : "background.paper", borderColor: view === value ? "primary.main" : "divider" }}>
          <Box component="span" className={`grid size-8 shrink-0 place-items-center rounded-lg ${tone}`}><Icon size={17} aria-hidden="true"/></Box>
          <Box component="span" sx={{ flex: 1, textAlign: "left" }}>{label}</Box>
          <Typography component="span" sx={{ fontWeight: 750, fontVariantNumeric: "tabular-nums" }}>{counts[value]}</Typography>
        </Button>)}
      </Box>

      <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
          <Box>
            <Typography component="h2" variant="h6">{currentView?.label}</Typography>
            <Typography variant="body2" color="text.secondary" aria-live="polite">
              {filtered.length} matching {filtered.length === 1 ? "item" : "items"} · {total} in this view
            </Typography>
          </Box>
          <TextField size="small" label="Search issues" placeholder="Customer, trip, order, or invoice" value={search} onChange={event => setSearch(event.target.value)} sx={{ minWidth: { md: 280 } }}/>
        </Stack>
        {viewRows.length < total && <Alert severity="info">Showing {viewRows.length} of {total} issues in this view. Search covers the issues shown here.</Alert>}
        {page.rows.map(item => {
          const [amountLabel, amount] = amountFor(item);
          const waitingForDetails = missingView && Boolean(item.reasons?.length);
          return <Box component="article" key={item.id} sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) minmax(180px, .55fr)" }, alignItems: "start", gap: 2 }}>
              <Box sx={{ overflowWrap: "anywhere", minWidth: 0 }}>
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
                  <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 700 }}>{item.customer}</Typography>
                  <Chip size="small" color={overdueView ? "error" : missingView ? "warning" : "default"} label={
                    overdueView ? "Past due" : missingView ? waitingForDetails ? "Missing billing details" : "Ready to invoice" : issueLabels[item.issue] || item.issue.replaceAll("_", " ").toLowerCase()
                  }/>
                </Stack>
                <Typography variant="body2" sx={{ mt: .5, fontWeight: 600 }}>Trip {item.trip_number} · Order {item.order_number}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {[item.invoice_number && `Invoice ${item.invoice_number}`, item.vehicle && `Truck ${item.vehicle}`].filter(Boolean).join(" · ")}
                </Typography>
                {waitingForDetails && <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2.5, fontSize: 14 }}>{item.reasons?.map(reason => <li key={reason}>{reason}</li>)}</Box>}
                {view === otherIssues && <Typography variant="body2" sx={{ mt: 1 }}>{item.message}</Typography>}
              </Box>
              <Box sx={{ bgcolor: "action.hover", borderRadius: 2, p: 1.5, overflowWrap: "anywhere" }}>
                <Typography variant="caption" color="text.secondary">{amountLabel}</Typography>
                <Typography variant="h6" color={overdueView ? "error.main" : "text.primary"} sx={{ fontWeight: 750, fontVariantNumeric: "tabular-nums" }}>{money(amount)}</Typography>
                {item.due_date && <Typography variant="body2" color="error.main">Due {dateLabel(item.due_date)}</Typography>}
                {item.paid_amount != null && <Typography variant="caption" color="text.secondary">Received {money(item.paid_amount)}</Typography>}
                {view === otherIssues && item.expected_amount != null && <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>Expected {money(item.expected_amount)}</Typography>}
              </Box>
            </Box>
            <Typography variant="body2" sx={{ mt: 1.25 }}><strong>Next step</strong> · {item.next_action}</Typography>
            {view === otherIssues && Boolean(item.reasons?.length) && <Box component="details" sx={{ mt: 1, fontSize: 14 }}>
              <Box component="summary" sx={{ cursor: "pointer", color: "primary.main" }}>Review notes</Box>
              <Box component="ul" sx={{ pl: 2.5, mb: 0 }}>{item.reasons?.map(reason => <li key={reason}>{reason}</li>)}</Box>
            </Box>}
          </Box>;
        })}
        {!filtered.length && <Stack spacing={1} sx={{ p: 5, textAlign: "center", alignItems: "center" }}>
          <Search size={24} aria-hidden="true"/>
          <Typography variant="subtitle2">{query ? "No matching issues" : missingView ? "No missing invoices" : overdueView ? "No overdue payments" : "No other issues found"}</Typography>
          {query && <Button onClick={() => setSearch("")}>Clear search</Button>}
        </Stack>}
        {filtered.length > 10 && page.controls}
      </Paper>
      <Typography variant="caption" color="text.secondary">As of {dateLabel(report.as_of)} · {report.delivered_trip_count} delivered trips reviewed</Typography>
    </>}
    <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap" }}>
      <AppLink href="/fleet/customer-invoices" className="text-sm font-semibold text-forest">Open customer invoices</AppLink>
      <AppLink href="/bank-reconciliation" className="text-sm font-semibold text-forest">Open bank reconciliation</AppLink>
    </Stack>
  </Box>;
}
