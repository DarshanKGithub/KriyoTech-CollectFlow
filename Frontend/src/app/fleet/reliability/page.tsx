"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { AlertTriangle, RefreshCw, Truck, Wrench } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useListPagination } from "@/components/list-pagination";

type Vehicle = { vehicle_id: string; registration_number: string; maintenance_cost: string; cost_per_km: string | null; downtime_hours: number; failure_counts: Record<string, number>; assignment_risk_reasons: string[]; basis: string; fuel_efficiency: { fill_record_count: number; undated_fill_count: number; interval_count: number; latest_efficiency_km_per_litre: string | null; status: "CALCULATED" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA"; intervals: { from_date: string; to_date: string; distance_km: string | null; fuel_litres: string | null; efficiency_km_per_litre: string | null; status: string }[]; basis: string }; odometer_integrity: { status: "CONSISTENT" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA"; event_count: number; latest_reading_km: string | null; issues: { evidence: string; previous_evidence: string; reading_km: string; previous_reading_km: string; message: string }[] } };
const money = (value: string) => `₹${Number(value).toLocaleString("en-IN")}`;
type TruckProfile = Vehicle & { vehicle_type?: string; capacity?: string | null; capacity_unit?: string };
const filters = [
  { value: "attention", label: "Needs attention" },
  { value: "dispatch", label: "Dispatch risks" },
  { value: "all", label: "All trucks" },
] as const;
type Filter = typeof filters[number]["value"];

function reasonsFor(row: Vehicle) {
  const reasons = [...row.assignment_risk_reasons];
  if (row.odometer_integrity?.status === "REVIEW_REQUIRED" && !reasons.some(reason => /out of sequence/i.test(reason))) {
    reasons.push("Truck readings are out of sequence.");
  }
  if (row.fuel_efficiency?.status === "REVIEW_REQUIRED") reasons.push("Fuel fill records are incomplete. Check litres, fill type, date, and truck reading.");
  return reasons;
}

export default function Reliability() {
  const [rows, setRows] = useState<TruckProfile[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<Filter>("attention");
  const [search, setSearch] = useState("");
  const [profileId, setProfileId] = useState("");
  const [profileError, setProfileError] = useState("");
  const profile = rows.find(row => row.vehicle_id === profileId);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/fleet/reliability");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load reliability data.");
      setRows(data.vehicles);
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load reliability data."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  async function configure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); setProfileError("");
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    const id = data.vehicle_id; delete data.vehicle_id;
    try {
      const response = await apiFetch(`/fleet/vehicles/${id}`, { method: "PATCH", body: JSON.stringify(data) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not save vehicle compatibility.");
      setProfileId(""); setMessage("Truck assignment profile saved."); await load();
    } catch (cause) { setProfileError(cause instanceof Error ? cause.message : "Could not save vehicle compatibility."); }
    finally { setBusy(false); }
  }
  const trucks = rows.map(row => ({ row, reasons: reasonsFor(row) }));
  const counts = { attention: trucks.filter(item => item.reasons.length).length, dispatch: rows.filter(row => row.assignment_risk_reasons.length).length, all: rows.length };
  const query = search.trim().toLowerCase();
  const filtered = trucks.filter(({ row, reasons }) =>
    (filter === "all" || (filter === "dispatch" ? row.assignment_risk_reasons.length > 0 : reasons.length > 0)) &&
    [row.registration_number, ...reasons].join(" ").toLowerCase().includes(query))
    .sort((a, b) => Number(b.reasons.length > 0) - Number(a.reasons.length > 0));
  const page = useListPagination(filtered, `${filter}:${search}`, "Truck reliability records");

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Truck health</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Fleet reliability</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>See which trucks need attention and what to check before dispatch.</Typography>
      </Box>
      <Button variant="outlined" startIcon={<RefreshCw size={16}/>} onClick={() => void load()} disabled={loading || busy}>Refresh</Button>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {message && <Alert severity="success">{message}</Alert>}
    <Box role="group" aria-label="Truck health filters" className="grid gap-3 sm:grid-cols-3">
      {filters.map(item => <Button key={item.value} variant="outlined" aria-pressed={filter === item.value} onClick={() => setFilter(item.value)}
        sx={{ justifyContent: "space-between", gap: 1, p: 2, bgcolor: filter === item.value ? "action.selected" : "background.paper", borderColor: filter === item.value ? "primary.main" : "divider" }}>
        {item.label}<Typography component="span" sx={{ fontWeight: 750 }}>{loading && !rows.length ? "—" : counts[item.value]}</Typography>
      </Button>)}
    </Box>
    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ p: 2, borderBottom: 1, borderColor: "divider", justifyContent: "space-between" }}>
        <Box>
          <Typography component="h2" variant="h6">{filters.find(item => item.value === filter)?.label}</Typography>
          <Typography variant="body2" color="text.secondary" aria-live="polite">{loading ? "Loading trucks…" : `${filtered.length} matching trucks`}</Typography>
        </Box>
        <TextField size="small" label="Search trucks" placeholder="Registration or reason" value={search} onChange={event => setSearch(event.target.value)}/>
      </Stack>
      {page.rows.map(({ row, reasons }) => <Box component="article" key={row.vehicle_id} sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}>
          <Box sx={{ minWidth: 0 }}>
            <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap", alignItems: "center" }}>
              <Truck size={18} aria-hidden="true"/>
              <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 750 }}>{row.registration_number}</Typography>
              <Chip size="small" label={row.assignment_risk_reasons.length ? "Review before dispatch" : reasons.length ? "Check fuel or truck readings" : "No issues flagged"}
                color={row.assignment_risk_reasons.length ? "warning" : reasons.length ? "info" : "default"}/>
            </Stack>
            {!!reasons.length && <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5, color: "text.primary" }}>
              {reasons.map(reason => <Typography component="li" key={reason} variant="body2" sx={{ mb: .5 }}>{reason}</Typography>)}
            </Box>}
          </Box>
          <Button variant="outlined" size="small" startIcon={<Wrench size={15}/>} disabled={loading || busy} sx={{ alignSelf: { xs: "flex-start", sm: "center" }, flexShrink: 0 }}
            onClick={() => { setProfileError(""); setProfileId(row.vehicle_id); }}>Assignment profile</Button>
        </Stack>
        <Box component="details" sx={{ mt: 1.5 }}>
          <Typography component="summary" variant="body2" sx={{ cursor: "pointer", color: "primary.main", fontWeight: 650 }}>View maintenance, fuel, and reading details</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0,1fr))", md: "repeat(4, minmax(0,1fr))" }, gap: 1, mt: 2 }}>
          {[["Maintenance", money(row.maintenance_cost)], ["Cost per km", row.cost_per_km ? `₹${row.cost_per_km}` : "Insufficient data"], ["Fuel km/L", row.fuel_efficiency?.latest_efficiency_km_per_litre ? `${row.fuel_efficiency.latest_efficiency_km_per_litre} · full-fill` : "Insufficient data"], ["Downtime", `${row.downtime_hours} hrs`]].map(([label, value]) => <Box key={label} sx={{ p: 1.25, borderRadius: 2, bgcolor: "action.hover", minWidth: 0 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="subtitle2" sx={{ mt: .25, fontWeight: 700 }}>{value}</Typography></Box>)}
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>Recorded failures: {Object.entries(row.failure_counts).map(([code, count]) => `${code}: ${count}`).join(" · ") || "No coded failures"}</Typography>
        {row.odometer_integrity?.status === "REVIEW_REQUIRED" && <Alert severity="warning" sx={{ mt: 1 }}><strong>Odometer sequence needs review.</strong>{row.odometer_integrity.issues.slice(0, 3).map((issue, index) => <Typography key={`${issue.evidence}-${index}`} variant="body2" sx={{ mt: .5 }}>{issue.evidence}: {issue.reading_km} km follows {issue.previous_evidence} at {issue.previous_reading_km} km.</Typography>)}<Typography variant="caption" sx={{ display: "block", mt: .5 }}>Distance and cost-per-kilometre are withheld until the conflicting readings are reviewed.</Typography></Alert>}
        {row.odometer_integrity?.status === "INSUFFICIENT_DATA" && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Odometer history is not sufficient to check reading order.</Typography>}
        {row.fuel_efficiency?.status === "REVIEW_REQUIRED" && <Alert severity="info" sx={{ mt: 1 }}>Fuel efficiency is withheld for incomplete fill intervals. Record each fill as full or partial with litres, date, and odometer. {row.fuel_efficiency.interval_count} interval(s) need review.</Alert>}
        {row.fuel_efficiency?.status === "INSUFFICIENT_DATA" && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Full-to-full fuel efficiency needs two recorded full fills with odometer readings and approved fuel records between them.</Typography>}
        {!!row.fuel_efficiency?.intervals.length && <Box sx={{ mt: 1.5 }}><Typography variant="caption" sx={{ fontWeight: 700 }}>Recent full-to-full intervals</Typography><Stack spacing={.5} sx={{ mt: .5 }}>{row.fuel_efficiency.intervals.slice().reverse().map((interval,index)=><Box key={`${interval.from_date}-${interval.to_date}-${index}`} sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 1, borderTop: "1px solid", borderColor: "divider", pt: .75 }}><Typography variant="caption" color="text.secondary">{interval.from_date} → {interval.to_date} · {interval.distance_km ?? "—"} km · {interval.fuel_litres ?? "—"} L</Typography><Typography variant="caption" sx={{ fontWeight: 700 }}>{interval.efficiency_km_per_litre ? `${interval.efficiency_km_per_litre} km/L` : "Review required"}</Typography></Box>)}</Stack></Box>}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.25 }}>Analysis basis · {row.basis}</Typography>
        </Box>
      </Box>)}
      {!loading && !error && !filtered.length && <Stack spacing={1} sx={{ p: 5, alignItems: "center", textAlign: "center" }}>
        <AlertTriangle size={24} aria-hidden="true"/>
        <Typography variant="subtitle2">{!rows.length ? "No truck records yet" : search ? "No matching trucks" : "No trucks flagged in this view"}</Typography>
        <Typography variant="body2" color="text.secondary">{!rows.length ? "Add trucks and record maintenance and readings to see their health here." : "Open All trucks to review the full fleet."}</Typography>
        {!!rows.length && <Button onClick={() => { setSearch(""); setFilter("all"); }}>Show all trucks</Button>}
      </Stack>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <Dialog open={Boolean(profile)} onClose={() => { if (!busy) setProfileId(""); }} fullWidth maxWidth="sm" aria-labelledby="truck-profile-title">
      <DialogTitle id="truck-profile-title">Truck assignment profile</DialogTitle>
      <DialogContent dividers>
        {profile && <Stack key={profile.vehicle_id} id="truck-profile-form" component="form" onSubmit={configure} spacing={2}>
          {profileError && <Alert severity="error">{profileError}</Alert>}
          <Typography variant="subtitle2">{profile.registration_number}</Typography>
          <Typography variant="body2" color="text.secondary">Set the truck type and capacity used when planning loads.</Typography>
          <input type="hidden" name="vehicle_id" value={profile.vehicle_id}/>
          <TextField select name="vehicle_type" required label="Vehicle type" defaultValue={profile.vehicle_type || ""}>
            {["LCV", "RIGID", "TRAILER", "TANKER", "REFRIGERATED"].map(type => <MenuItem key={type} value={type}>{type}</MenuItem>)}
          </TextField>
          <TextField name="capacity" required label="Load capacity" type="number" defaultValue={profile.capacity ?? ""} slotProps={{ htmlInput: { min: .001, step: .001 } }}/>
          <TextField select name="capacity_unit" required label="Capacity unit" defaultValue={profile.capacity_unit || ""}>
            {["TONNE", "KG", "CBM", "PALLET"].map(unit => <MenuItem key={unit} value={unit}>{unit}</MenuItem>)}
          </TextField>
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setProfileId("")}>Cancel</Button>
        <Button type="submit" form="truck-profile-form" variant="contained" disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button>
      </DialogActions>
    </Dialog>
  </Box>;
}
