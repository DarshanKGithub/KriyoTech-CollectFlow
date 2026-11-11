"use client";

import { DateField } from "@/components/date-field";
import { UiMain, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiTh } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { Download, Fuel, ReceiptText, Truck } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Row = Record<string, string | number | null>;
type Filters = { report: string; from: string; to: string };
type Result = { rows: Row[]; filters: Filters; totals?: { expense_total: string; fuel_spend: string; fuel_litres: string } };
const initialFilters: Filters = { report: "trip-costs", from: "", to: "" };
const reports = [
  { id: "trip-costs", label: "Trip costs and fuel" }, { id: "salary-outstanding", label: "Outstanding driver salaries" },
  { id: "invoice-exceptions", label: "Invoice exceptions" }, { id: "payment-status", label: "Payment status" },
];
const tripColumns = [
  ["trip_number", "Trip"], ["truck", "Truck"], ["driver", "Driver"], ["date", "Trip created"],
  ["expense_total", "Trip costs"], ["fuel_spend", "Fuel spend"], ["fuel_litres", "Fuel used"], ["status", "Status"],
];
const moneyFields = new Set(["expense_total", "fuel_spend", "gross_salary", "trip_earnings", "gross_earnings", "advance_recovered", "net_payable", "paid", "remaining", "amount"]);
const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const quantity = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 });
const format = (value: string | number | null | undefined, key: string) => {
  if (value == null || value === "") return "—";
  if (moneyFields.has(key)) return currency.format(Number(value));
  if (key === "fuel_litres") return `${quantity.format(Number(value))} L`;
  if (key === "status") return String(value).toLowerCase().replaceAll("_", " ").replace(/^./, first => first.toUpperCase());
  return String(value);
};

function reportUrl(filters: Filters, csv = false) {
  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (csv) params.set("export", "csv");
  return `/fleet/operational-reports/${filters.report}?${params}`;
}

export default function FleetOperationalReportsPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [result, setResult] = useState<Result | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"run" | "export" | null>("run");

  const run = useCallback(async (next: Filters) => {
    if (next.from === "INVALID" || next.to === "INVALID" || (next.from && next.to && next.from > next.to)) {
      setError("Choose a valid date range before running the report.");
      return;
    }
    setBusy("run"); setError("");
    try {
      const response = await apiFetch(reportUrl(next));
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not run report.");
      setResult({ rows: data.rows || [], filters: next, totals: data.totals });
      setSearch("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not run report.");
    } finally {
      setBusy(null);
    }
  }, []);
  useEffect(() => { void run(initialFilters); }, [run]);

  async function exportCsv() {
    if (!result || busy) return;
    setBusy("export"); setError("");
    try {
      const response = await apiFetch(reportUrl(result.filters, true));
      if (!response.ok) throw new Error("Report export failed.");
      const href = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `kriyopay-${result.filters.report}.csv`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(href), 1000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Report export failed.");
    } finally {
      setBusy(null);
    }
  }

  const rows = result?.rows ?? [];
  const isTripReport = result?.filters.report === "trip-costs";
  const columns = isTripReport ? tripColumns : Object.keys(rows[0] || {}).map(key => [key, key.replaceAll("_", " ")]);
  const query = search.trim().toLowerCase();
  const filtered = rows.filter(row => Object.values(row).join(" ").toLowerCase().includes(query));
  const page = useListPagination(filtered, JSON.stringify([result?.filters, search]), "Operational report rows");
  const totals = result?.totals;
  const range = result?.filters;
  const rangeLabel = range?.from && range.to ? `${range.from} to ${range.to}` : range?.from ? `From ${range.from}` : range?.to ? `Through ${range.to}` : "All dates";

  return <UiMain className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Box component="header">
      <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Finance</Typography>
      <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Operational reports</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>See trip costs and fuel spend, or switch to a salary, invoice, or payment report.</Typography>
    </Box>

    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
      <Stack component="form" direction={{ xs: "column", sm: "row" }} useFlexGap spacing={1.5} sx={{ flexWrap: "wrap", alignItems: { sm: "flex-start" } }}
        onSubmit={event => { event.preventDefault(); if (!busy) void run(filters); }}>
        <TextField select size="small" label="Report" value={filters.report} disabled={Boolean(busy)} sx={{ minWidth: 230 }}
          onChange={event => setFilters(current => ({ ...current, report: event.target.value }))}>
          {reports.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
        </TextField>
        <Box sx={{ width: { xs: "100%", sm: 160 } }}><DateField label="From date" value={filters.from} onChange={value => setFilters(current => ({ ...current, from: value }))} disabled={Boolean(busy)}/></Box>
        <Box sx={{ width: { xs: "100%", sm: 160 } }}><DateField label="To date" value={filters.to} onChange={value => setFilters(current => ({ ...current, to: value }))} disabled={Boolean(busy)}/></Box>
        <Button type="submit" variant="contained" disabled={Boolean(busy)}>{busy === "run" ? "Running…" : "Run report"}</Button>
      </Stack>
    </Paper>
    {error && <Alert severity="error">{error}</Alert>}
    {busy === "run" && <LinearProgress aria-label="Loading operational report"/>}

    {isTripReport && <Box className="grid gap-3 sm:grid-cols-3">
      {[
        { label: "Total trip costs", value: format(totals?.expense_total, "expense_total"), icon: ReceiptText, detail: "Includes fuel and other recorded costs" },
        { label: "Net fuel spend", value: format(totals?.fuel_spend, "fuel_spend"), icon: Fuel, detail: "Fuel costs after refund credits" },
        { label: "Fuel used", value: format(totals?.fuel_litres, "fuel_litres"), icon: Truck, detail: "Litres recorded on fuel entries" },
      ].map(({ label, value, icon: Icon, detail }) => <Paper key={label} variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", color: "primary.main" }}><Icon size={17} aria-hidden="true"/><Typography variant="subtitle2">{label}</Typography></Stack>
        <Typography variant="h5" sx={{ mt: 1, fontWeight: 750, fontVariantNumeric: "tabular-nums" }}>{value}</Typography>
        <Typography variant="caption" color="text.secondary">{detail}</Typography>
      </Paper>)}
    </Box>}

    {result && <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", borderBottom: 1, borderColor: "divider", p: 2 }}>
        <Box>
          <Typography component="h2" variant="h6">{reports.find(item => item.id === range?.report)?.label}</Typography>
          <Typography variant="body2" color="text.secondary">{rangeLabel} · {filtered.length} of {rows.length} rows</Typography>
          {isTripReport && <Typography variant="caption" color="text.secondary">Dates refer to trip creation. Costs include draft and submitted entries and exclude estimates and rejected entries.</Typography>}
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "flex-start" } }}>
          <TextField size="small" label={isTripReport ? "Search trips" : "Search report"} placeholder={isTripReport ? "Trip, truck, or driver" : "Search records"} value={search} onChange={event => setSearch(event.target.value)}/>
          <Button variant="outlined" startIcon={<Download size={16}/>} disabled={Boolean(busy)} onClick={() => void exportCsv()}>{busy === "export" ? "Downloading…" : "Download report CSV"}</Button>
        </Stack>
      </Stack>
      {filtered.length ? <div className="overflow-x-auto">
        <UiTable className="w-full min-w-[700px] text-left text-sm">
          <UiTableHead className="bg-slate-50"><UiTableRow>{columns.map(([key, label]) => <UiTh key={key} scope="col" className="px-4 py-3 text-xs font-semibold capitalize text-slate-600">{label}</UiTh>)}</UiTableRow></UiTableHead>
          <UiTableBody>{page.rows.map((row, index) => <UiTableRow key={index} className="border-t border-line">
            {columns.map(([key]) => <UiTd key={key} className={`px-4 py-3 ${moneyFields.has(key) ? "whitespace-nowrap font-semibold tabular-nums" : ""}`}>{format(row[key], key)}</UiTd>)}
          </UiTableRow>)}</UiTableBody>
        </UiTable>
      </div> : <Typography variant="body2" color="text.secondary" sx={{ p: 5, textAlign: "center" }}>{query ? "No rows match your search." : "No records in this report for the selected dates."}</Typography>}
      {filtered.length > 10 && page.controls}
    </Paper>}
  </UiMain>;
}
