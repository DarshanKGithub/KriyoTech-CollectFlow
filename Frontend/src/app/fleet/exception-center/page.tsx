"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Pagination, Paper, Stack, TextField, Typography } from "@mui/material";
import { AlertTriangle, ClipboardList, Download, ScanSearch } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Case = {
  id: string; category: string; status: string; owner_id: string | null; owner: string | null;
  due_at: string | null; overdue: boolean; review_note: string; public_resolution: string; updated_at: string;
  evidence: { message?: string; trip_number?: string; order_number?: string; next_action?: string } & Record<string, unknown>;
};
type History = { action: string; actor: string | null; at: string; details: { note?: string; previous_note?: string } };
type Owner = { id: string; email: string };
const queues = [
  { value: "active", label: "Needs attention" }, { value: "overdue", label: "Overdue" },
  { value: "unassigned", label: "Unassigned" }, { value: "closed", label: "Closed" },
] as const;
const decisions = { assign: "Assign owner", confirm: "Confirm issue", dismiss: "Dismiss case", resolve: "Resolve case", reopen: "Reopen case" } as const;
type Decision = keyof typeof decisions;
const statusLabels: Record<string, string> = { OPEN: "Open", CONFIRMED: "Confirmed", DISMISSED: "Dismissed", RESOLVED: "Resolved" };
const evidenceFields = [
  "trip_number", "order_number", "vehicle", "registration_number", "customer", "reference_sample_count", "distance_km", "load_kg",
  "litres_per_km", "baseline_litres_per_km", "efficiency_km_per_litre", "baseline_km_per_litre", "fuel_litres", "monthly_budget",
  "trip_budget", "trip_fuel_spend", "expected_efficiency_km_per_litre", "monthly_spend", "approved_monthly_spend", "over_budget_amount",
  "month", "reference_interval_count", "from_date", "to_date", "synthetic_demo", "reference_trips", "expected_amount",
  "approved_trip_revenue", "invoice_amount", "paid_amount", "outstanding_amount", "collection_amount", "reasons", "next_action",
];
const label = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/^./, first => first.toUpperCase());
const date = (value: string | null) => value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "No deadline";
const activeCase = (row: Case) => row.status === "OPEN" || row.status === "CONFIRMED";
const decisionLabel = (action: Decision, row: Case) => action === "confirm" && row.category.includes("FUEL_") ? "Confirm review signal" : decisions[action];

export default function ExceptionCenter() {
  const [rows, setRows] = useState<Case[]>([]);
  const [owners, setOwners] = useState<Owner[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [queue, setQueue] = useState("active");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Case | null>(null);
  const [history, setHistory] = useState<History[] | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [saving, setSaving] = useState(false);
  const [action, setAction] = useState<Decision | "">("");
  const [note, setNote] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const [publicReply, setPublicReply] = useState("");
  const listVersion = useRef(0);
  const detailVersion = useRef(0);

  const load = useCallback(async () => {
    const version = ++listVersion.current;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "50", queue, status, search });
      const response = await apiFetch(`/fleet/exceptions?${params}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load cases.");
      if (version !== listVersion.current) return;
      const lastPage = Math.max(1, Math.ceil(data.count / 50));
      if (page > lastPage) { setPage(lastPage); return; }
      setRows(data.items);
      setOwners(data.owners);
      setCount(data.count);
      setSummary(data.summary || {});
    } catch (cause) {
      if (version === listVersion.current) setError(cause instanceof Error ? cause.message : "Could not load cases.");
    } finally {
      if (version === listVersion.current) setLoading(false);
    }
  }, [page, queue, status, search]);

  useEffect(() => { void load(); }, [load]);

  async function sync() {
    setScanning(true); setError(""); setNotice("");
    try {
      const response = await apiFetch("/fleet/exceptions", { method: "POST", body: "{}" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not scan for exceptions.");
      setNotice(data.created ? `Scan complete. New cases added: ${data.created}.` : "Scan complete. No new cases were added.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not scan for exceptions.");
    } finally {
      setScanning(false);
    }
  }

  async function open(row: Case) {
    const version = ++detailVersion.current;
    setSelected(row); setDetailLoading(true); setDetailError(""); setHistory(null); setAction(""); setNote("");
    try {
      const response = await apiFetch(`/fleet/exceptions/${row.id}`);
      const data: Case & { history: History[]; error?: string } = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load case details.");
      if (version !== detailVersion.current) return;
      setSelected(data);
      setHistory(data.history);
      setOwner(data.owner_id || "");
      const deadline = data.due_at ? new Date(data.due_at) : null;
      setDue(deadline ? new Date(deadline.getTime() - deadline.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");
      setPublicReply(data.public_resolution || "");
    } catch (cause) {
      if (version === detailVersion.current) setDetailError(cause instanceof Error ? cause.message : "Could not load case details.");
    } finally {
      if (version === detailVersion.current) setDetailLoading(false);
    }
  }

  function closeReview() {
    detailVersion.current++;
    setSelected(null);
  }

  const needsPublicReply = action === "resolve" && selected?.category === "CUSTOMER_DELIVERY_DISPUTE";
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !action || !history || saving) return;
    setSaving(true); setDetailError(""); setNotice("");
    try {
      const response = await apiFetch(`/fleet/exceptions/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          action, note: note.trim(), expected_updated_at: selected.updated_at,
          ...(action === "assign" ? { owner_id: owner, due_at: new Date(due).toISOString() } : {}),
          ...(needsPublicReply ? { public_resolution: publicReply.trim() } : {}),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save the case.");
      closeReview();
      setNotice("Case updated.");
      await load();
    } catch (cause) {
      setDetailError(cause instanceof Error ? cause.message : "Could not save the case.");
    } finally {
      setSaving(false);
    }
  }

  async function download() {
    try {
      const response = await apiFetch("/fleet/exceptions?export=csv");
      if (!response.ok) throw new Error("Could not export cases.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url; link.download = "fleet-exceptions.csv"; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not export cases.");
    }
  }

  function changeQueue(value: string) {
    setQueue(value); setStatus(""); setPage(1);
  }

  const availableActions: Decision[] = selected && activeCase(selected)
    ? ["assign", "confirm", "resolve", "dismiss", ...(selected.status === "CONFIRMED" ? ["reopen" as const] : [])]
    : ["reopen", "assign"];

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Operations</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Exception center</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Review trip, fuel, billing, and delivery issues in one place.</Typography>
      </Box>
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button variant="outlined" startIcon={<Download size={16}/>} onClick={() => void download()}>Export all cases</Button>
        <Button variant="contained" startIcon={<ScanSearch size={16}/>} disabled={scanning || loading} onClick={() => void sync()}>{scanning ? "Scanning…" : "Find new exceptions"}</Button>
      </Stack>
    </Stack>
    {error && <Alert severity="error" action={<Button size="small" color="inherit" onClick={() => void load()}>Refresh cases</Button>}>{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}

    <Box role="group" aria-label="Exception queues" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {queues.map(item => <Button key={item.value} variant="outlined" aria-pressed={queue === item.value} disabled={scanning || saving}
        onClick={() => changeQueue(queue === item.value ? "" : item.value)}
        sx={{ justifyContent: "space-between", gap: 1, p: 2, bgcolor: queue === item.value ? "action.selected" : "background.paper", borderColor: queue === item.value ? "primary.main" : "divider" }}>
        {item.label}<Typography component="span" sx={{ fontWeight: 750 }}>{summary[item.value] ?? "—"}</Typography>
      </Button>)}
    </Box>

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", lg: "row" }} spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box>
          <Typography component="h2" variant="h6">{queues.find(item => item.value === queue)?.label || "All exceptions"}</Typography>
          <Typography variant="body2" color="text.secondary" aria-live="polite">{loading ? "Loading cases…" : `${count} matching ${count === 1 ? "case" : "cases"}`}</Typography>
        </Box>
        <Stack component="form" direction={{ xs: "column", sm: "row" }} spacing={1} onSubmit={event => { event.preventDefault(); setSearch(query.trim()); setPage(1); }}>
          <TextField size="small" label="Search cases" placeholder="Trip, order, issue, or owner" value={query} onChange={event => setQuery(event.target.value)} slotProps={{ htmlInput: { maxLength: 200 } }}/>
          <Button type="submit" variant="outlined" disabled={scanning || saving}>Search</Button>
          <TextField select size="small" label="Case status" value={status} disabled={scanning || saving} onChange={event => { setQueue(""); setStatus(event.target.value); setPage(1); }} sx={{ minWidth: 145 }}>
            <MenuItem value="">All statuses</MenuItem>
            {Object.entries(statusLabels).map(([value, text]) => <MenuItem key={value} value={value}>{text}</MenuItem>)}
          </TextField>
          {(query || search || status || queue) && <Button type="button" disabled={scanning || saving} onClick={() => { setQuery(""); setSearch(""); changeQueue(""); }}>Show all cases</Button>}
        </Stack>
      </Stack>

      {!loading && rows.map(row => <Box component="article" key={row.id} sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1.6fr) minmax(0, 1fr) auto" }, gap: 2, alignItems: "start" }}>
          <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
            <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap", alignItems: "center" }}>
              <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 700 }}>{label(row.category)}</Typography>
              <Chip size="small" label={statusLabels[row.status] || label(row.status)} color={row.status === "OPEN" ? "warning" : row.status === "CONFIRMED" ? "info" : row.status === "RESOLVED" ? "success" : "default"}/>
              {row.overdue && <Chip size="small" color="error" variant="outlined" label="Overdue"/>}
              {Boolean(row.evidence.synthetic_demo) && <Chip size="small" variant="outlined" label="Simulation"/>}
            </Stack>
            {row.evidence.message && <Typography variant="body2" sx={{ mt: .75 }}>{row.evidence.message}</Typography>}
            {(row.evidence.trip_number || row.evidence.order_number) && <Typography variant="caption" color="text.secondary">
              {[row.evidence.trip_number && `Trip ${row.evidence.trip_number}`, row.evidence.order_number && `Order ${row.evidence.order_number}`].filter(Boolean).join(" · ")}
            </Typography>}
          </Box>
          <Box sx={{ bgcolor: "action.hover", borderRadius: 2, p: 1.25, overflowWrap: "anywhere" }}>
            <Typography variant="caption" color="text.secondary">Owner</Typography>
            <Typography variant="body2" sx={{ fontWeight: 650 }}>{row.owner || "Unassigned"}</Typography>
            <Typography variant="caption" color={row.overdue ? "error.main" : "text.secondary"}>{row.due_at ? `Due ${date(row.due_at)}` : "No deadline"}</Typography>
          </Box>
          <Button variant="outlined" size="small" startIcon={<ClipboardList size={15}/>} sx={{ justifySelf: "start" }} disabled={scanning || saving} onClick={() => void open(row)}>{activeCase(row) ? "Review case" : "View case"}</Button>
        </Box>
        {activeCase(row) && row.evidence.next_action && <Typography variant="body2" color="text.secondary" sx={{ mt: 1.25 }}>
          <strong>Suggested next step</strong> · {row.evidence.next_action}
        </Typography>}
      </Box>)}

      {!loading && !error && !rows.length && <Stack spacing={1} sx={{ p: 5, textAlign: "center", alignItems: "center" }}>
        <AlertTriangle size={24} aria-hidden="true"/>
        <Typography variant="subtitle2">No cases in this view</Typography>
        <Typography variant="body2" color="text.secondary">Choose another queue, clear your search, or scan for new exceptions.</Typography>
      </Stack>}
      {!loading && count > 50 && <Pagination sx={{ p: 2 }} aria-label="Exception pages" count={Math.ceil(count / 50)} page={page} disabled={scanning || saving} onChange={(_, value) => setPage(value)}/>}
    </Paper>

    <Dialog open={Boolean(selected)} onClose={() => { if (!saving) closeReview(); }} fullWidth maxWidth="md" aria-labelledby="exception-review-title">
      <DialogTitle id="exception-review-title">{selected ? label(selected.category) : "Review exception"}</DialogTitle>
      <DialogContent dividers>
        {selected && <Stack spacing={2}>
          <Typography variant="body2">{selected.evidence.message || "Review the case details and choose a next step."}</Typography>
          {selected.review_note && <Typography variant="body2" color="text.secondary">Last review note · {selected.review_note}</Typography>}
          {selected.category.includes("FUEL_") && <Alert severity="warning">Check the receipt, truck reading, route, load, vehicle, and credits before making a decision. The signal alone does not establish theft.</Alert>}
          {detailError && <Alert severity="error" action={<Button size="small" color="inherit" disabled={saving} onClick={() => void open(selected)}>Reload case</Button>}>{detailError}</Alert>}
          <Box component="details">
            <Typography component="summary" variant="subtitle2" sx={{ cursor: "pointer" }}>Case evidence</Typography>
            <Box component="dl" className="mb-0 mt-3 grid gap-2 sm:grid-cols-2">
              {Object.entries(selected.evidence).filter(([key]) => evidenceFields.includes(key)).map(([key, value]) => <Box key={key} sx={{ p: 1, bgcolor: "action.hover", borderRadius: 2, overflowWrap: "anywhere" }}>
                <Typography component="dt" variant="caption" color="text.secondary">{label(key)}</Typography>
                <Typography component="dd" variant="body2" sx={{ m: 0 }}>{Array.isArray(value) ? value.join(" · ") : String(value ?? "Not recorded")}</Typography>
              </Box>)}
            </Box>
          </Box>
          {detailLoading && <Typography variant="body2" color="text.secondary">Loading case history…</Typography>}
          {history && <>
            <Stack id="exception-review-form" component="form" spacing={2} onSubmit={save}>
              <TextField select label="What would you like to do?" value={action} disabled={saving}
                onChange={event => setAction(event.target.value as Decision | "")}>
                <MenuItem value="">Choose an action</MenuItem>
                {availableActions.map(value => <MenuItem key={value} value={value}>{decisionLabel(value, selected)}</MenuItem>)}
              </TextField>
              {action === "assign" && <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField select fullWidth required label="Owner" value={owner} onChange={event => setOwner(event.target.value)}>
                  {owner && !owners.some(item => item.id === owner) && <MenuItem disabled value={owner}>{selected.owner || "Unavailable owner"}</MenuItem>}
                  {owners.map(item => <MenuItem key={item.id} value={item.id}>{item.email}</MenuItem>)}
                </TextField>
                <TextField required fullWidth type="datetime-local" label="Deadline" value={due} onChange={event => setDue(event.target.value)} slotProps={{ inputLabel: { shrink: true } }}/>
              </Stack>}
              {action && <TextField required multiline minRows={2} label="Review note" value={note} onChange={event => setNote(event.target.value)} slotProps={{ htmlInput: { maxLength: 1000 } }}/>}
              {needsPublicReply && <TextField required multiline minRows={2} label="Response for the customer" helperText="The customer can see this response after you resolve the case." value={publicReply} onChange={event => setPublicReply(event.target.value)} slotProps={{ htmlInput: { maxLength: 1000 } }}/>}
            </Stack>
            <Box component="details">
              <Typography component="summary" variant="subtitle2" sx={{ cursor: "pointer" }}>Case history ({history.length})</Typography>
              <Stack spacing={1.25} sx={{ mt: 1.5 }}>
                {history.map((entry, index) => <Box key={index}>
                  <Typography variant="body2" sx={{ fontWeight: 650 }}>{label(entry.action.replace(/^FLEET_EXCEPTION_/, ""))}</Typography>
                  <Typography variant="caption" color="text.secondary">{entry.actor || "Automation"} · {date(entry.at)}</Typography>
                  {(entry.details.note || entry.details.previous_note) && <Typography variant="body2">{entry.details.note || entry.details.previous_note}</Typography>}
                </Box>)}
                {!history.length && <Typography variant="body2" color="text.secondary">No decisions recorded.</Typography>}
              </Stack>
            </Box>
          </>}
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button disabled={saving} onClick={closeReview}>Close</Button>
        {action && selected && <Button type="submit" form="exception-review-form" variant="contained"
          disabled={saving || detailLoading || !note.trim() || (action === "assign" && (!owners.some(item => item.id === owner) || !due)) || (needsPublicReply && !publicReply.trim())}>
          {saving ? "Saving…" : decisionLabel(action, selected)}
        </Button>}
      </DialogActions>
    </Dialog>
  </Box>;
}
