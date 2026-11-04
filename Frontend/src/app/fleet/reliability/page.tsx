"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Alert, Box, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { Activity, AlertTriangle, RefreshCw, Wrench } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Vehicle = { vehicle_id: string; registration_number: string; maintenance_cost: string; cost_per_km: string | null; downtime_hours: number; failure_counts: Record<string, number>; assignment_risk_reasons: string[]; basis: string; fuel_efficiency: { fill_record_count: number; undated_fill_count: number; interval_count: number; latest_efficiency_km_per_litre: string | null; status: "CALCULATED" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA"; intervals: { from_date: string; to_date: string; distance_km: string | null; fuel_litres: string | null; efficiency_km_per_litre: string | null; status: string }[]; basis: string }; odometer_integrity: { status: "CONSISTENT" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA"; event_count: number; latest_reading_km: string | null; issues: { evidence: string; previous_evidence: string; reading_km: string; previous_reading_km: string; message: string }[] } };
const money = (value: string) => `₹${Number(value).toLocaleString("en-IN")}`;

export default function Reliability() {
  const [rows, setRows] = useState<Vehicle[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
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
    event.preventDefault(); setBusy(true); setMessage("");
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    const id = data.vehicle_id; delete data.vehicle_id;
    try {
      const response = await apiFetch(`/fleet/vehicles/${id}`, { method: "PATCH", body: JSON.stringify(data) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not save vehicle compatibility.");
      await load(); setMessage("Vehicle compatibility saved. Assignment risk has been recalculated.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save vehicle compatibility."); }
    finally { setBusy(false); }
  }
  const atRisk = rows.filter(row => row.assignment_risk_reasons.length > 0).length;
  const maintenanceSpend = rows.reduce((sum, row) => sum + Number(row.maintenance_cost || 0), 0);
  const downtime = rows.reduce((sum, row) => sum + row.downtime_hours, 0);

  return <Box component="main" sx={{ width: "100%", maxWidth: 1760, mx: "auto", p: { xs: 2, sm: 3, lg: 4 } }}>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "flex-end" } }}>
      <Box><Typography variant="overline" color="primary" sx={{ fontWeight: 700, letterSpacing: ".14em" }}>FLEET HEALTH</Typography><Typography variant="h4">Reliability & assignment risk</Typography><Typography color="text.secondary" sx={{ mt: .75, maxWidth: 760 }}>Use service history, downtime and odometer records to spot vehicles that may need attention before dispatch.</Typography></Box>
      <Button variant="outlined" startIcon={<RefreshCw size={16}/>} onClick={() => void load()} disabled={loading}>Refresh analysis</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }} action={<Button color="inherit" size="small" onClick={() => void load()}>Retry</Button>}>{error}</Alert>}
    {message && <Alert severity="success" sx={{ mt: 2 }}>{message}</Alert>}
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(4, minmax(0, 1fr))" }, gap: 1.5, mt: 3 }}>
      {[
        { label: "Vehicles reviewed", value: rows.length, Icon: Activity },
        { label: "Assignment risks", value: atRisk, Icon: AlertTriangle },
        { label: "Maintenance spend", value: money(String(maintenanceSpend)), Icon: Wrench },
        { label: "Downtime recorded", value: `${downtime} hrs`, Icon: Activity },
      ].map(metric => <Paper key={metric.label} variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ justifyContent: "space-between" }}><Box><Typography variant="body2" color="text.secondary">{metric.label}</Typography><Typography variant="h5" sx={{ mt: .5, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{loading ? "—" : metric.value}</Typography></Box><metric.Icon size={18} color="#64748b"/></Stack></Paper>)}
    </Box>
    <Paper variant="outlined" sx={{ mt: 2.5, p: { xs: 2, sm: 2.5 } }}>
      <Typography variant="subtitle1">Vehicle assignment profile</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .25 }}>Set the vehicle type and load capacity used to check compatibility during dispatch.</Typography>
      <Box component="form" onSubmit={event => void configure(event)} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", xl: "repeat(5, minmax(0, 1fr))" }, gap: 1.5, alignItems: "center", mt: 2 }}>
        <TextField name="vehicle_id" select required label="Vehicle" defaultValue="">{rows.map(row => <MenuItem key={row.vehicle_id} value={row.vehicle_id}>{row.registration_number}</MenuItem>)}</TextField>
        <TextField select name="vehicle_type" required label="Vehicle type" defaultValue="">{["LCV", "RIGID", "TRAILER", "TANKER", "REFRIGERATED"].map(type => <MenuItem key={type} value={type}>{type}</MenuItem>)}</TextField>
        <TextField select name="capacity_unit" required label="Capacity unit" defaultValue="">{["TONNE", "KG", "CBM", "PALLET"].map(unit => <MenuItem key={unit} value={unit}>{unit}</MenuItem>)}</TextField>
        <TextField name="capacity" required label="Load capacity" type="number" slotProps={{ htmlInput: { min: .001, step: .001 } }}/>
        <Button type="submit" variant="contained" disabled={busy || rows.length === 0}>{busy ? "Saving…" : "Save vehicle profile"}</Button>
      </Box>
    </Paper>
    <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mt: 3, mb: 1.5 }}><Box><Typography variant="h6">Vehicle health</Typography><Typography variant="caption" color="text.secondary">Risk is based on recorded maintenance and odometer history.</Typography></Box><Chip size="small" label={`${atRisk} need attention`} color={atRisk ? "warning" : "success"}/></Stack>
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
      {rows.map(row => <Paper key={row.vehicle_id} variant="outlined" sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stack direction="row" spacing={2} sx={{ justifyContent: "space-between", alignItems: "flex-start" }}><Box><Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{row.registration_number}</Typography><Typography variant="caption" color="text.secondary">Fleet vehicle</Typography></Box><Chip size="small" icon={<Activity size={14}/>} label={row.assignment_risk_reasons.length ? "Review before dispatch" : "No recorded risk"} color={row.assignment_risk_reasons.length ? "warning" : "success"}/></Stack>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0,1fr))", md: "repeat(4, minmax(0,1fr))" }, gap: 1, mt: 2 }}>
          {[["Maintenance", money(row.maintenance_cost)], ["Cost per km", row.cost_per_km ? `₹${row.cost_per_km}` : "Insufficient data"], ["Fuel km/L", row.fuel_efficiency?.latest_efficiency_km_per_litre ? `${row.fuel_efficiency.latest_efficiency_km_per_litre} · full-fill` : "Insufficient data"], ["Downtime", `${row.downtime_hours} hrs`]].map(([label, value]) => <Box key={label} sx={{ p: 1.25, borderRadius: 2, bgcolor: "action.hover", minWidth: 0 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="subtitle2" sx={{ mt: .25, fontWeight: 700 }}>{value}</Typography></Box>)}
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>Recorded failures: {Object.entries(row.failure_counts).map(([code, count]) => `${code}: ${count}`).join(" · ") || "No coded failures"}</Typography>
        {row.odometer_integrity?.status === "REVIEW_REQUIRED" && <Alert severity="warning" sx={{ mt: 1 }}><strong>Odometer sequence needs review.</strong>{row.odometer_integrity.issues.slice(0, 3).map((issue, index) => <Typography key={`${issue.evidence}-${index}`} variant="body2" sx={{ mt: .5 }}>{issue.evidence}: {issue.reading_km} km follows {issue.previous_evidence} at {issue.previous_reading_km} km.</Typography>)}<Typography variant="caption" sx={{ display: "block", mt: .5 }}>Distance and cost-per-kilometre are withheld until the conflicting readings are reviewed.</Typography></Alert>}
        {row.odometer_integrity?.status === "INSUFFICIENT_DATA" && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Odometer history is not sufficient to check reading order.</Typography>}
        {row.fuel_efficiency?.status === "REVIEW_REQUIRED" && <Alert severity="info" sx={{ mt: 1 }}>Fuel efficiency is withheld for incomplete fill intervals. Record each fill as full or partial with litres, date, and odometer. {row.fuel_efficiency.interval_count} interval(s) need review.</Alert>}
        {row.fuel_efficiency?.status === "INSUFFICIENT_DATA" && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>Full-to-full fuel efficiency needs two recorded full fills with odometer readings and approved fuel records between them.</Typography>}
        {!!row.fuel_efficiency?.intervals.length && <Box sx={{ mt: 1.5 }}><Typography variant="caption" sx={{ fontWeight: 700 }}>Recent full-to-full intervals</Typography><Stack spacing={.5} sx={{ mt: .5 }}>{row.fuel_efficiency.intervals.slice().reverse().map((interval,index)=><Box key={`${interval.from_date}-${interval.to_date}-${index}`} sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 1, borderTop: "1px solid", borderColor: "divider", pt: .75 }}><Typography variant="caption" color="text.secondary">{interval.from_date} → {interval.to_date} · {interval.distance_km ?? "—"} km · {interval.fuel_litres ?? "—"} L</Typography><Typography variant="caption" sx={{ fontWeight: 700 }}>{interval.efficiency_km_per_litre ? `${interval.efficiency_km_per_litre} km/L` : "Review required"}</Typography></Box>)}</Stack></Box>}
        {row.assignment_risk_reasons.map(reason => <Alert key={reason} severity="warning" sx={{ mt: 1 }}>{reason}</Alert>)}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.25 }}>Analysis basis: {row.basis}</Typography>
      </Paper>)}
      {!loading && rows.length === 0 && <Paper variant="outlined" sx={{ gridColumn: "1/-1", p: 5, textAlign: "center" }}><Wrench size={24} color="#94a3b8"/><Typography variant="subtitle2" sx={{ mt: 1 }}>No vehicle health records</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>Add vehicles and record maintenance and odometer readings to build a reliability view.</Typography></Paper>}
    </Box>
  </Box>;
}
