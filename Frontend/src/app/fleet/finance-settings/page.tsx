"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { Plus, RefreshCw } from "lucide-react";
import { AppLink } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { apiFetch } from "@/lib/api";

type Driver = { id: string; name: string; status: string };
type Policy = {
  id: string; driver: Driver; basis: "MONTHLY" | "PER_TRIP" | "PER_KILOMETRE";
  rate: string; effective_from: string; effective_to: string | null;
};
const bases = {
  MONTHLY: { label: "Monthly salary", unit: "month" },
  PER_TRIP: { label: "Per trip", unit: "trip" },
  PER_KILOMETRE: { label: "Per kilometre", unit: "km" },
};
const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const today = () => new Intl.DateTimeFormat("sv-SE", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const displayDate = (date: string) => new Date(`${date}T00:00:00`).toLocaleDateString("en-IN", { dateStyle: "medium" });
function policyStatus(policy: Policy, date: string) {
  if (policy.effective_to && policy.effective_to < date) return "Ended";
  return policy.effective_from > date ? "Scheduled" : "Active";
}
function errorMessage(result: Record<string, unknown> | null, fallback: string) {
  if (!result) return fallback;
  if (typeof result.error === "string") return result.error;
  if (typeof result.detail === "string") return result.detail;
  return Object.values(result).flat().filter(value => typeof value === "string").join(" ") || fallback;
}

export default function DriverFinanceSettingsPage() {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [adding, setAdding] = useState(false);
  const [closing, setClosing] = useState<Policy | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [driverResponse, policyResponse, profileResponse] = await Promise.all([
        apiFetch("/fleet/drivers"), apiFetch("/fleet/driver-pay-policies"), apiFetch("/auth/me"),
      ]);
      if (!driverResponse.ok || !policyResponse.ok) throw new Error("Could not load driver finance settings.");
      const [driverData, policyData, profile] = await Promise.all([
        driverResponse.json(), policyResponse.json(), profileResponse.ok ? profileResponse.json() : null,
      ]);
      setDrivers(driverData);
      setPolicies(policyData);
      setCanEdit(["OWNER", "FINANCE", "FLEET"].includes(profile?.role));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load driver finance settings.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEdit || busy || (!adding && !closing)) return;
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    if (!data.effective_to) delete data.effective_to;
    setBusy(true); setDialogError(""); setMessage("");
    try {
      const response = await apiFetch(closing ? `/fleet/driver-pay-policies/${closing.id}` : "/fleet/driver-pay-policies", {
        method: closing ? "PATCH" : "POST", body: JSON.stringify(data),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(errorMessage(result, "Could not save this pay policy."));
      setMessage(closing ? "Policy end date saved." : "Pay policy added.");
      setAdding(false); setClosing(null);
      await load();
    } catch (cause) {
      setDialogError(cause instanceof Error ? cause.message : "Could not save this pay policy.");
    } finally {
      setBusy(false);
    }
  }

  const date = today();
  const statusOptions = ["Active", "Scheduled", "Ended"];
  const query = search.trim().toLowerCase();
  const filtered = policies.filter(policy => (!filter || policyStatus(policy, date) === filter) &&
    [policy.driver.name, bases[policy.basis]?.label].join(" ").toLowerCase().includes(query));
  const page = useListPagination(filtered, `${filter}:${search}`, "Driver pay policies");
  const activeDrivers = drivers.filter(driver => driver.status === "ACTIVE");

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Finance settings</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Driver pay policies</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>See how each driver is paid and when their rate applies.</Typography>
      </Box>
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button variant="outlined" startIcon={<RefreshCw size={16}/>} disabled={loading || busy} onClick={() => void load()}>Refresh</Button>
        {canEdit && <Button variant="contained" startIcon={<Plus size={16}/>} disabled={loading || busy || !activeDrivers.length}
          onClick={() => { setDialogError(""); setAdding(true); }}>Add pay policy</Button>}
      </Stack>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {message && <Alert severity="success">{message}</Alert>}
    {!loading && !error && !canEdit && <Alert severity="info">Workspace owners, finance users, and fleet operators can change pay policies.</Alert>}
    {!loading && canEdit && !activeDrivers.length && <Alert severity="info">Add or activate a driver before creating a pay policy.</Alert>}

    <Box role="group" aria-label="Pay policy filters" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {["", ...statusOptions].map(value => <Button key={value} variant="outlined" aria-pressed={filter === value}
        onClick={() => setFilter(value)}
        sx={{ p: 1.75, gap: 1, justifyContent: "space-between", bgcolor: filter === value ? "action.selected" : "background.paper", borderColor: filter === value ? "primary.main" : "divider" }}>
        {value || "All policies"}
        <Typography component="span" sx={{ fontWeight: 750 }}>{loading && !policies.length ? "—" : value ? policies.filter(policy => policyStatus(policy, date) === value).length : policies.length}</Typography>
      </Button>)}
    </Box>

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ p: 2, justifyContent: "space-between", borderBottom: 1, borderColor: "divider" }}>
        <Box>
          <Typography component="h2" variant="h6">Policy history</Typography>
          <Typography variant="body2" color="text.secondary" aria-live="polite">{loading ? "Loading policies…" : `${filtered.length} matching policies`}</Typography>
        </Box>
        <TextField size="small" label="Search policies" placeholder="Driver or pay basis" value={search} onChange={event => setSearch(event.target.value)}/>
      </Stack>
      {page.rows.map(policy => {
        const status = policyStatus(policy, date);
        const basis = bases[policy.basis];
        return <Box component="article" key={policy.id} sx={{ p: 2, borderBottom: 1, borderColor: "divider", display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) auto" }, gap: 2, alignItems: "center" }}>
          <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
            <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 700 }}>{policy.driver.name}</Typography>
            <Chip size="small" color={status === "Active" ? "success" : status === "Scheduled" ? "info" : "default"} label={status}/>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">{basis?.label || policy.basis}</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{currency.format(Number(policy.rate))} / {basis?.unit || "period"}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">Effective dates</Typography>
            <Typography variant="body2">{displayDate(policy.effective_from)} · {policy.effective_to ? displayDate(policy.effective_to) : "No end date"}</Typography>
          </Box>
          {canEdit && !policy.effective_to && <Button size="small" variant="outlined" disabled={loading || busy} sx={{ justifySelf: "start" }}
            onClick={() => { setDialogError(""); setClosing(policy); }}>Set end date</Button>}
        </Box>;
      })}
      {!loading && !error && !filtered.length && <Stack spacing={1} sx={{ p: 5, textAlign: "center", alignItems: "center" }}>
        <Typography variant="subtitle2">{policies.length ? "No matching policies" : "No pay policies yet"}</Typography>
        <Typography variant="body2" color="text.secondary">{policies.length ? "Try another driver or status." : "Add a monthly, per-trip, or per-kilometre rate to get started."}</Typography>
        {!!policies.length && <Button onClick={() => { setFilter(""); setSearch(""); }}>Clear filters</Button>}
      </Stack>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <div className="flex flex-wrap gap-4 text-sm font-semibold text-forest">
      <AppLink href="/fleet/driver-salaries">Salary settlements and ledger</AppLink>
      <AppLink href="/fleet/settings">Fleet reminders</AppLink>
    </div>

    <Dialog open={adding || Boolean(closing)} onClose={() => { if (!busy) { setAdding(false); setClosing(null); } }} fullWidth maxWidth="sm" aria-labelledby="pay-policy-title">
      <DialogTitle id="pay-policy-title">{closing ? "Set policy end date" : "Add pay policy"}</DialogTitle>
      <DialogContent dividers>
        {(adding || closing) && <Stack key={closing?.id || "new"} id="pay-policy-form" component="form" spacing={2} onSubmit={savePolicy}>
          {dialogError && <Alert severity="error">{dialogError}</Alert>}
          {closing ? <>
            <Typography variant="body2">{closing.driver.name} · {bases[closing.basis]?.label}</Typography>
            <TextField required name="effective_to" type="date" label="Last day this rate applies" defaultValue={date < closing.effective_from ? closing.effective_from : date}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { min: closing.effective_from } }}/>
          </> : <>
            <Typography variant="body2" color="text.secondary">A driver can have one policy on any date. End an open policy before adding a replacement rate.</Typography>
            <TextField required select name="driver_id" label="Driver" defaultValue="">
              {activeDrivers.map(driver => <MenuItem key={driver.id} value={driver.id}>{driver.name}</MenuItem>)}
            </TextField>
            <TextField required select name="basis" label="Pay basis" defaultValue="MONTHLY">
              {Object.entries(bases).map(([value, basis]) => <MenuItem key={value} value={value}>{basis.label}</MenuItem>)}
            </TextField>
            <TextField required name="rate" type="number" label="Amount or rate (₹)" slotProps={{ htmlInput: { min: .01, step: .01 } }}/>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField required fullWidth name="effective_from" type="date" label="First day" defaultValue={date} slotProps={{ inputLabel: { shrink: true } }}/>
              <TextField fullWidth name="effective_to" type="date" label="Last day (optional)" slotProps={{ inputLabel: { shrink: true } }}/>
            </Stack>
          </>}
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => { setAdding(false); setClosing(null); }}>Cancel</Button>
        <Button variant="contained" type="submit" form="pay-policy-form" disabled={busy || !canEdit}>{busy ? "Saving…" : closing ? "Save end date" : "Save pay policy"}</Button>
      </DialogActions>
    </Dialog>
  </Box>;
}
