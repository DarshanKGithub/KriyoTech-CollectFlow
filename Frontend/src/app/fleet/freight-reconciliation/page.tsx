"use client";

import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { FileSpreadsheet, RefreshCw, Upload } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { PageSkeleton } from "@/components/content-skeleton";
import { useListPagination } from "@/components/list-pagination";
import { UiInput, UiLabel, UiSelect } from "@/components/product-ui";

type Row = {
  id: string; filename: string; row_number: number; trip_id: string | null; trip_number: string;
  kind: string; category: string; description: string; amount: string | null; is_refund: boolean;
  quantity_litres: string | null; fuel_fill_type: string; odometer_km: string | null;
  payment_reference: string; incurred_at: string | null; status: string; review_note: string;
  raw_data: Record<string, string | boolean>;
};
type Trip = { id: string; trip_number: string; origin: string; destination: string };

const statuses = [
  { value: "NEEDS_REVIEW", label: "Needs review", color: "warning" },
  { value: "RECONCILED", label: "Draft created", color: "success" },
  { value: "IGNORED", label: "Ignored", color: "default" },
] as const;
const categories = ["OTHER", "FUEL", "TOLL", "LOADING", "ALLOWANCE", "PERMIT", "REPAIR", "PARKING", "COMMISSION"];
const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

export default function FreightReconciliationPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [batchFile, setBatchFile] = useState<string | null>(null);
  const [selected, setSelected] = useState<Row | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const uploadInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [imports, tripList] = await Promise.all([apiFetch("/fleet/freight-imports"), apiFetch("/fleet/trips")]);
      const [importData, tripData] = await Promise.all([imports.json(), tripList.json()]);
      if (!imports.ok) throw new Error(importData.error || "Could not load imported rows.");
      if (!tripList.ok) throw new Error(tripData.error || "Could not load the trip list.");
      setRows(importData.rows || []);
      setTrips(Array.isArray(tripData) ? tripData : []);
      setBatchFile(null);
      setNotice("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load freight reconciliation.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    setBusy("upload"); setError(""); setNotice("");
    const form = new FormData();
    form.set("file", file);
    try {
      const response = await apiFetch("/fleet/freight-imports", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Import failed.");
      setRows(data.rows || []);
      setBatchFile(file.name);
      setSearch(""); setFilter("");
      setNotice(data.duplicate_upload ? "This file was already imported. Showing its existing rows." : `Imported ${data.rows?.length || 0} rows for review.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not import the file.");
    } finally {
      setBusy("");
    }
  }

  async function action(row: Row, which: "reconcile" | "ignore", form?: HTMLFormElement) {
    setBusy(which); setReviewError(""); setNotice("");
    const data = form ? Object.fromEntries(new FormData(form).entries()) : {};
    try {
      const response = await apiFetch(`/fleet/freight-import-rows/${row.id}/${which}`, { method: "POST", body: JSON.stringify(data) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not update this row.");
      setRows(current => current.map(item => item.id === row.id ? result : item));
      setSelected(null);
      setNotice(which === "reconcile" ? "Trip ledger draft created. It still needs approval." : "Row ignored.");
    } catch (cause) {
      setReviewError(cause instanceof Error ? cause.message : "Could not update this row.");
    } finally {
      setBusy("");
    }
  }

  const query = search.trim().toLowerCase();
  const filtered = rows.filter(row => (!filter || row.status === filter) &&
    [row.description, row.filename, row.trip_number, row.payment_reference, row.raw_data?.vehicle_registration]
      .join(" ").toLowerCase().includes(query));
  const page = useListPagination(filtered, `${batchFile}:${filter}:${search}`, "Imported freight rows");

  if (loading) return <PageSkeleton variant="table" label="Loading freight reconciliation"/>;

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={2} sx={{ alignItems: { sm: "flex-end" }, justifyContent: "space-between" }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Finance</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Freight reconciliation</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Import a freight file, match each row to a trip, and save it as a draft for approval.</Typography>
      </Box>
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button variant="outlined" startIcon={<RefreshCw size={16}/>} disabled={Boolean(busy)} onClick={() => void load()}>{batchFile ? "Show all imports" : "Refresh"}</Button>
        <Button variant="contained" startIcon={<Upload size={16}/>} disabled={Boolean(busy)} onClick={() => uploadInput.current?.click()}>{busy === "upload" ? "Importing…" : "Import CSV / Excel"}</Button>
        <input ref={uploadInput} type="file" accept=".csv,.xlsx,.xlsm" hidden onChange={upload}/>
      </Stack>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}
    <Box role="group" aria-label="Filter imported rows by status" className="grid gap-3 sm:grid-cols-3">
      {statuses.map(status => <Button key={status.value} variant="outlined" aria-pressed={filter === status.value}
        onClick={() => setFilter(filter === status.value ? "" : status.value)}
        sx={{ justifyContent: "space-between", p: 2, bgcolor: filter === status.value ? "action.selected" : "background.paper", borderColor: filter === status.value ? "primary.main" : "divider" }}>
        {status.label} <Typography component="span" sx={{ fontWeight: 750 }}>{rows.filter(row => row.status === status.value).length}</Typography>
      </Button>)}
    </Box>

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", md: "row" }} useFlexGap spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography component="h2" variant="h6">Imported rows</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{batchFile ? `${batchFile} · ` : ""}{filtered.length} shown · {rows.length} total</Typography>
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={1}>
          <TextField size="small" label="Search rows" placeholder="Trip, truck, file, or reference" value={search} onChange={event => setSearch(event.target.value)}/>
          <TextField select size="small" label="Status" value={filter} onChange={event => setFilter(event.target.value)} sx={{ minWidth: 150 }}>
            <MenuItem value="">All rows</MenuItem>{statuses.map(status => <MenuItem key={status.value} value={status.value}>{status.label}</MenuItem>)}
          </TextField>
        </Stack>
      </Stack>
      {page.rows.map(row => {
        const status = statuses.find(item => item.value === row.status);
        const truck = row.raw_data?.vehicle_registration;
        return <Box component="article" key={row.id} sx={{ p: 2, borderBottom: 1, borderColor: "divider", display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) auto" }, gap: 2, alignItems: "center" }}>
          <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
            <Stack direction="row" useFlexGap spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography sx={{ fontWeight: 700 }}>{row.description || "Imported freight entry"}</Typography>
              <Chip size="small" color={status?.color} label={status?.label || row.status}/>
              {row.is_refund && <Chip size="small" variant="outlined" label="Fuel refund"/>}
              {row.raw_data?.synthetic_demo && <Chip size="small" variant="outlined" label="Demo row"/>}
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>
              {row.trip_number ? `Trip ${row.trip_number}` : "No trip matched"}{typeof truck === "string" && truck ? ` · Truck ${truck}` : ""}{row.payment_reference ? ` · Ref ${row.payment_reference}` : ""}
            </Typography>
            <Typography variant="caption" color="text.secondary">{row.filename} · Row {row.row_number}</Typography>
            {row.review_note && <Typography variant="body2" sx={{ mt: .5 }} color={row.status === "NEEDS_REVIEW" ? "warning.dark" : "text.secondary"}>{row.review_note}</Typography>}
          </Box>
          <Stack direction="row" useFlexGap spacing={2} sx={{ alignItems: "center", flexWrap: "wrap", justifyContent: { md: "flex-end" } }}>
            <Typography variant="subtitle2">{row.amount ? money.format(Number(row.amount)) : "Amount missing"}</Typography>
            {row.status === "NEEDS_REVIEW" && <Button variant="outlined" disabled={Boolean(busy)} onClick={() => { setReviewError(""); setSelected(row); }}>Review row</Button>}
          </Stack>
        </Box>;
      })}
      {!filtered.length && !error && <Stack sx={{ p: 5, alignItems: "center", textAlign: "center" }} useFlexGap spacing={1}>
        <FileSpreadsheet size={24} aria-hidden="true"/>
        <Typography sx={{ fontWeight: 700 }}>{rows.length ? "No matching rows" : "No freight rows to show"}</Typography>
        <Typography variant="body2" color="text.secondary">{rows.length ? "Try another search or status." : "Import a CSV or Excel file to start reviewing freight entries."}</Typography>
        {rows.length > 0 && <Button onClick={() => { setSearch(""); setFilter(""); }}>Clear filters</Button>}
      </Stack>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <Dialog open={Boolean(selected)} onClose={() => { if (!busy) setSelected(null); }} fullWidth maxWidth="sm" aria-labelledby="freight-review-title">
      <DialogTitle id="freight-review-title">Review freight row</DialogTitle>
      <DialogContent dividers>
        {selected && <form key={selected.id} id="freight-row-form" onSubmit={event => { event.preventDefault(); void action(selected, "reconcile", event.currentTarget); }} className="grid gap-4 sm:grid-cols-2">
          <Box className="sm:col-span-2">
            <Typography sx={{ fontWeight: 700 }}>{selected.description || "Imported freight entry"}</Typography>
            <Typography variant="body2" color="text.secondary">{selected.filename} · Row {selected.row_number}</Typography>
          </Box>
          {reviewError && <Alert className="sm:col-span-2" severity="error">{reviewError}</Alert>}
          {selected.review_note && <Alert className="sm:col-span-2" severity="info">{selected.review_note}</Alert>}
          <UiLabel className="text-sm sm:col-span-2">Trip<UiSelect name="trip_id" defaultValue={selected.trip_id || ""} required className="mt-1 w-full"><option value="">Choose trip</option>{trips.map(trip => <option key={trip.id} value={trip.id}>{trip.trip_number} · {trip.origin || "—"} → {trip.destination || "—"}</option>)}</UiSelect></UiLabel>
          <UiLabel className="text-sm">Type<UiSelect name="kind" defaultValue={selected.kind} required className="mt-1 w-full"><option value="">Choose type</option><option value="REVENUE">Freight income</option><option value="EXPENSE">Trip expense</option></UiSelect></UiLabel>
          <UiLabel className="text-sm">Category<UiSelect name="category" defaultValue={selected.category || "OTHER"} className="mt-1 w-full">{categories.map(category => <option key={category} value={category}>{category.charAt(0) + category.slice(1).toLowerCase()}</option>)}</UiSelect></UiLabel>
          <UiLabel className="text-sm">Amount (₹)<UiInput name="amount" type="number" min="0.01" step="0.01" defaultValue={selected.amount || ""} required className="mt-1 w-full"/></UiLabel>
          <UiLabel className="text-sm">Transaction date<UiInput name="incurred_at" type="date" defaultValue={selected.incurred_at || ""} className="mt-1 w-full"/></UiLabel>
          <details className="rounded-lg border border-line px-3 py-2 sm:col-span-2" open={selected.category === "FUEL" || selected.is_refund ? true : undefined}>
            <summary className="cursor-pointer text-sm font-semibold">Fuel details and transaction reference</summary>
            <Box className="mt-3 grid gap-3 sm:grid-cols-2">
              <UiLabel className="text-sm">Fuel litres<UiInput name="quantity_litres" type="number" min="0.01" step="0.01" defaultValue={selected.quantity_litres || ""} className="mt-1 w-full"/></UiLabel>
              <UiLabel className="text-sm">Fill type<UiSelect name="fuel_fill_type" defaultValue={selected.fuel_fill_type || "UNKNOWN"} className="mt-1 w-full"><option value="UNKNOWN">Unknown</option><option value="FULL">Full tank</option><option value="PARTIAL">Partial fill</option></UiSelect></UiLabel>
              <UiLabel className="text-sm">Truck reading (km)<UiInput name="odometer_km" type="number" min="0" step="0.1" defaultValue={selected.odometer_km || ""} className="mt-1 w-full"/></UiLabel>
              <UiLabel className="text-sm">Transaction reference<UiInput name="payment_reference" maxLength={120} defaultValue={selected.payment_reference || ""} className="mt-1 w-full"/></UiLabel>
            </Box>
          </details>
        </form>}
      </DialogContent>
      <DialogActions sx={{ flexWrap: "wrap", gap: .5 }}>
        <Button disabled={Boolean(busy)} onClick={() => setSelected(null)}>Cancel</Button>
        <Button color="inherit" disabled={Boolean(busy) || !selected} onClick={() => { if (selected) void action(selected, "ignore"); }}>{busy === "ignore" ? "Ignoring…" : "Ignore row"}</Button>
        <Button type="submit" form="freight-row-form" variant="contained" disabled={Boolean(busy) || !selected}>{busy === "reconcile" ? "Saving…" : "Match and create draft"}</Button>
      </DialogActions>
    </Dialog>
  </Box>;
}
