"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { FileText, RefreshCw, Upload } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useListPagination } from "@/components/list-pagination";

type DocumentRow = {
  id: string;
  filename: string;
  kind: string;
  status: string;
  trip_id: string | null;
  trip_number: string;
  order_id: string | null;
  order_number: string;
  fields: Record<string, unknown>;
  confidence: Record<string, number>;
  warnings: string[];
  created_at: string;
};
type Trip = { id: string; trip_number: string; origin: string; destination: string };
type Order = { id: string; order_number: string; origin: string; destination: string };

const kinds: Record<string, string> = {
  EWAY_BILL: "E-way bill",
  CONSIGNMENT_NOTE: "Consignment note / lorry receipt",
  PROOF_OF_DELIVERY: "Proof of delivery",
};
const statuses: Record<string, { label: string; color: "info" | "warning" | "success" | "error" }> = {
  EXTRACTING: { label: "Reading file", color: "info" },
  NEEDS_REVIEW: { label: "Needs review", color: "warning" },
  FAILED: { label: "Could not read file", color: "error" },
  CONFIRMED: { label: "Confirmed", color: "success" },
};
const fieldLabel = (key: string) => key.replaceAll("_", " ").replace(/^./, first => first.toUpperCase());

export default function LogisticsDocumentsPage() {
  const [rows, setRows] = useState<DocumentRow[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const requestVersion = useRef(0);

  const loadDocuments = useCallback(async () => {
    const version = ++requestVersion.current;
    try {
      const response = await apiFetch("/fleet/logistics-documents");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not load documents.");
      if (version === requestVersion.current) {
        setRows(Array.isArray(result) ? result : []);
        setError("");
      }
    } catch (cause) {
      if (version === requestVersion.current) setError(cause instanceof Error ? cause.message : "Could not load documents.");
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadDocuments(),
        apiFetch("/fleet/trips").then(async response => {
          if (!response.ok) return;
          const result = await response.json();
          if (Array.isArray(result)) setTrips(result);
        }).catch(() => {}),
        apiFetch("/fleet/orders").then(async response => {
          if (!response.ok) return;
          const result = await response.json();
          if (Array.isArray(result)) setOrders(result);
        }).catch(() => {}),
      ]);
    } finally {
      setLoading(false);
    }
  }, [loadDocuments]);

  useEffect(() => { void refresh(); }, [refresh]);
  const extracting = rows.some(row => row.status === "EXTRACTING");
  useEffect(() => {
    if (!extracting || busy || loading) return;
    let checking = false;
    const timer = window.setInterval(async () => {
      if (checking) return;
      checking = true;
      try {
        await loadDocuments();
      } finally {
        checking = false;
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [extracting, busy, loading, loadDocuments]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setDialogError("");
    setNotice("");
    try {
      const response = await apiFetch("/fleet/documents", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not upload document.");
      setUploadOpen(false);
      setSearch(""); setKindFilter(""); setStatusFilter("");
      setNotice("Document uploaded. Check the list for its review status.");
      await loadDocuments();
    } catch (cause) {
      setDialogError(cause instanceof Error ? cause.message : "Could not upload document.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(event: FormEvent<HTMLFormElement>, row: DocumentRow) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    let fields: unknown;
    try {
      fields = JSON.parse(String(form.get("fields") || "{}"));
      if (!fields || typeof fields !== "object" || Array.isArray(fields)) throw new Error();
    } catch {
      setDialogError("Enter the document fields as a valid JSON object.");
      return;
    }
    if (!form.get("trip_id") && !form.get("order_id")) {
      setDialogError("Choose a trip or an order before confirming.");
      return;
    }
    setBusy(true);
    setDialogError("");
    setNotice("");
    try {
      const response = await apiFetch(`/fleet/logistics-documents/${row.id}/review`, {
        method: "POST",
        body: JSON.stringify({ trip_id: form.get("trip_id"), order_id: form.get("order_id"), fields, confirm: true }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not confirm document.");
      requestVersion.current++;
      setRows(current => current.map(item => item.id === row.id ? result : item));
      setSelectedId("");
      setNotice(result.kind === "PROOF_OF_DELIVERY" && result.trip_id ? "Document confirmed and attached to the trip as proof of delivery." : "Document confirmed.");
    } catch (cause) {
      setDialogError(cause instanceof Error ? cause.message : "Could not confirm document.");
    } finally {
      setBusy(false);
    }
  }

  const selected = rows.find(row => row.id === selectedId);
  const canConfirm = selected?.status === "NEEDS_REVIEW" || selected?.status === "FAILED";
  const query = search.trim().toLowerCase();
  const filtered = rows.filter(row =>
    (!kindFilter || row.kind === kindFilter) &&
    (!statusFilter || row.status === statusFilter || (statusFilter === "NEEDS_REVIEW" && row.status === "FAILED")) &&
    [row.filename, row.trip_number, row.order_number, kinds[row.kind]].join(" ").toLowerCase().includes(query));
  const page = useListPagination(filtered, `${search}:${kindFilter}:${statusFilter}`, "Logistics documents");
  const summaries = [
    { value: "", label: "All documents", count: rows.length },
    { value: "NEEDS_REVIEW", label: "Needs attention", count: rows.filter(row => ["NEEDS_REVIEW", "FAILED"].includes(row.status)).length },
    { value: "EXTRACTING", label: "Reading file", count: rows.filter(row => row.status === "EXTRACTING").length },
    { value: "CONFIRMED", label: "Confirmed", count: rows.filter(row => row.status === "CONFIRMED").length },
  ];

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Documents</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Logistics documents</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Find e-way bills, lorry receipts, and delivery proof linked to trips and orders.</Typography>
      </Box>
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button variant="outlined" startIcon={<RefreshCw size={16}/>} disabled={loading || busy} onClick={() => void refresh()}>Refresh</Button>
        <Button variant="contained" startIcon={<Upload size={16}/>} disabled={busy || loading} onClick={() => { setDialogError(""); setUploadOpen(true); }}>Upload document</Button>
      </Stack>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}

    <Box role="group" aria-label="Filter documents by status" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {summaries.map(item => <Button key={item.value} variant="outlined" aria-pressed={statusFilter === item.value}
        onClick={() => setStatusFilter(statusFilter === item.value ? "" : item.value)}
        sx={{ justifyContent: "space-between", gap: 1, p: 2, bgcolor: statusFilter === item.value ? "action.selected" : "background.paper", borderColor: statusFilter === item.value ? "primary.main" : "divider" }}>
        {item.label}<Typography component="span" sx={{ fontWeight: 750 }}>{loading && !rows.length ? "—" : item.count}</Typography>
      </Button>)}
    </Box>

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box>
          <Typography component="h2" variant="h6">Saved documents</Typography>
          <Typography variant="body2" color="text.secondary" aria-live="polite">{loading ? "Loading documents…" : `${filtered.length} shown · ${rows.length} total`}</Typography>
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Search documents" placeholder="File name, trip, or order" value={search} onChange={event => setSearch(event.target.value)}/>
          <TextField select size="small" label="Document type" value={kindFilter} onChange={event => setKindFilter(event.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">All types</MenuItem>
            {Object.entries(kinds).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
          </TextField>
        </Stack>
      </Stack>
      {page.rows.map(row => {
        const status = statuses[row.status];
        const needsReview = row.status === "NEEDS_REVIEW" || row.status === "FAILED";
        return <Stack component="article" key={row.id} direction={{ xs: "column", sm: "row" }} spacing={2}
          sx={{ p: 2, borderBottom: 1, borderColor: "divider", alignItems: { sm: "center" }, justifyContent: "space-between" }}>
          <Stack direction="row" spacing={1.5} sx={{ minWidth: 0 }}>
            <Box className="grid size-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-forest"><FileText size={18} aria-hidden="true"/></Box>
            <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
              <Stack direction="row" useFlexGap spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 700 }}>{row.filename}</Typography>
                <Chip size="small" label={status?.label || fieldLabel(row.status)} color={status?.color}/>
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {kinds[row.kind] || row.kind} · {[row.trip_number && `Trip ${row.trip_number}`, row.order_number && `Order ${row.order_number}`].filter(Boolean).join(" · ") || "No trip or order linked"}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Uploaded {new Date(row.created_at).toLocaleDateString()}{row.warnings?.length ? ` · ${row.warnings.length} ${row.warnings.length === 1 ? "review note" : "review notes"}` : ""}
              </Typography>
            </Box>
          </Stack>
          <Button size="small" variant={needsReview ? "outlined" : "text"} sx={{ alignSelf: { xs: "flex-start", sm: "center" }, flexShrink: 0 }}
            onClick={() => { setDialogError(""); setSelectedId(row.id); }}>{needsReview ? "Review document" : "View details"}</Button>
        </Stack>;
      })}
      {!loading && !error && !filtered.length && <Stack spacing={1} sx={{ p: 5, textAlign: "center", alignItems: "center" }}>
        <FileText size={24} aria-hidden="true"/>
        <Typography variant="subtitle2">{rows.length ? "No matching documents" : "No documents uploaded yet"}</Typography>
        <Typography variant="body2" color="text.secondary">{rows.length ? "Try a different search or filter." : "Upload an e-way bill, lorry receipt, or delivery proof to get started."}</Typography>
        {rows.length > 0 && <Button onClick={() => { setSearch(""); setKindFilter(""); setStatusFilter(""); }}>Clear filters</Button>}
      </Stack>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <Dialog open={uploadOpen} onClose={() => { if (!busy) setUploadOpen(false); }} fullWidth maxWidth="sm" aria-labelledby="logistics-upload-title">
      <DialogTitle id="logistics-upload-title">Upload a logistics document</DialogTitle>
      <DialogContent dividers>
        <Stack id="logistics-upload-form" component="form" onSubmit={upload} spacing={2}>
          {dialogError && <Alert severity="error">{dialogError}</Alert>}
          <TextField select required name="logistics_kind" label="Document type" defaultValue="">
            {Object.entries(kinds).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
          </TextField>
          <Typography component="label" variant="body2">
            Document file
            <input name="file" type="file" required accept=".pdf,.jpg,.jpeg,.png,.heic,.heif" className="mt-2 block w-full text-sm"/>
          </Typography>
          <Typography variant="caption" color="text.secondary">PDF, JPEG, PNG, HEIC, or HEIF. Up to 25 MB.</Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setUploadOpen(false)}>Cancel</Button>
        <Button variant="contained" type="submit" form="logistics-upload-form" disabled={busy}>{busy ? "Uploading…" : "Upload document"}</Button>
      </DialogActions>
    </Dialog>

    <Dialog open={Boolean(selected)} onClose={() => { if (!busy) setSelectedId(""); }} fullWidth maxWidth="md" aria-labelledby="logistics-review-title">
      <DialogTitle id="logistics-review-title">{canConfirm ? "Review document" : "Document details"}</DialogTitle>
      <DialogContent dividers>
        {selected && <Stack spacing={2} key={selected.id}>
          <Box sx={{ overflowWrap: "anywhere" }}>
            <Typography sx={{ fontWeight: 700 }}>{selected.filename}</Typography>
            <Typography variant="body2" color="text.secondary">{kinds[selected.kind] || selected.kind} · {statuses[selected.status]?.label || fieldLabel(selected.status)}</Typography>
            {!canConfirm && <Typography variant="body2" color="text.secondary">
              {[selected.trip_number && `Trip ${selected.trip_number}`, selected.order_number && `Order ${selected.order_number}`].filter(Boolean).join(" · ") || "No trip or order linked"}
            </Typography>}
          </Box>
          {dialogError && <Alert severity="error">{dialogError}</Alert>}
          {!!selected.warnings?.length && <Alert severity="warning">
            <Box component="ul" sx={{ m: 0, pl: 2 }}>{selected.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</Box>
          </Alert>}
          {selected.status === "EXTRACTING" ? <Typography variant="body2">The file is being read. Review will be available when it finishes.</Typography> :
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>Extracted fields</Typography>
              {Object.keys(selected.fields || {}).length ? <Box component="dl" className="m-0 grid gap-2 sm:grid-cols-2">
                {Object.entries(selected.fields).map(([key, value]) => <Box key={key} sx={{ p: 1.25, bgcolor: "action.hover", borderRadius: 2, minWidth: 0, overflowWrap: "anywhere" }}>
                  <Typography component="dt" variant="caption" color="text.secondary">{fieldLabel(key)}</Typography>
                  <Typography component="dd" variant="body2" sx={{ m: 0, fontWeight: 600 }}>{typeof value === "object" ? JSON.stringify(value) : String(value)}</Typography>
                  {typeof selected.confidence?.[key] === "number" && <Typography variant="caption" color="text.secondary">{Math.round(selected.confidence[key] * 100)}% extraction confidence</Typography>}
                </Box>)}
              </Box> : <Typography variant="body2" color="text.secondary">No fields were extracted.</Typography>}
            </Box>}
          {canConfirm && <Stack id="logistics-review-form" component="form" onSubmit={event => void confirm(event, selected)} spacing={2}>
            <Typography variant="subtitle2">Link to a trip or order</Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField select fullWidth name="trip_id" label="Trip" defaultValue={selected.trip_id || ""}>
                <MenuItem value="">No trip</MenuItem>
                {selected.trip_id && !trips.some(trip => trip.id === selected.trip_id) && <MenuItem value={selected.trip_id}>{selected.trip_number}</MenuItem>}
                {trips.map(trip => <MenuItem key={trip.id} value={trip.id}>{trip.trip_number} · {trip.origin || "—"} → {trip.destination || "—"}</MenuItem>)}
              </TextField>
              <TextField select fullWidth name="order_id" label="Transport order" defaultValue={selected.order_id || ""}>
                <MenuItem value="">No order</MenuItem>
                {selected.order_id && !orders.some(order => order.id === selected.order_id) && <MenuItem value={selected.order_id}>{selected.order_number}</MenuItem>}
                {orders.map(order => <MenuItem key={order.id} value={order.id}>{order.order_number} · {order.origin || "—"} → {order.destination || "—"}</MenuItem>)}
              </TextField>
            </Stack>
            <Box component="details">
              <Typography component="summary" variant="body2" sx={{ cursor: "pointer", fontWeight: 600 }}>Edit or add document fields</Typography>
              <TextField name="fields" label="Document fields (JSON)" fullWidth multiline minRows={4} defaultValue={JSON.stringify(selected.fields || {}, null, 2)} sx={{ mt: 1.5, "& textarea": { fontFamily: "monospace" } }}/>
            </Box>
          </Stack>}
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setSelectedId("")}>{canConfirm ? "Cancel" : "Close"}</Button>
        {canConfirm && <Button variant="contained" type="submit" form="logistics-review-form" disabled={busy}>{busy ? "Confirming…" : "Confirm document"}</Button>}
      </DialogActions>
    </Dialog>
  </Box>;
}
