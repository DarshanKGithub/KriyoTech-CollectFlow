"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { UiAlert, UiBox, UiButton, UiH1, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiText } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
import { AlertTriangle, CalendarDays, CheckCircle2, ClipboardList, RefreshCw, Search, Wrench } from "lucide-react";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";

type Vehicle = { id: string; registration_number: string; make_model?: string };
type Work = { id: string; vehicle_id: string; registration_number: string; category_label: string; description: string; service_date: string; odometer_km: string | null; cost: string; vendor: string; next_due_date: string | null; next_due_odometer_km: string | null; receipt_filename: string | null; notes: string; breakdown_at: string | null; returned_to_service_at: string | null; downtime_hours: number | null; failure_code: string };
const input = "mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-forest";
const formatDate = (value: string | null) => value ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString() : "Not scheduled";

export default function TruckMaintenancePage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [rows, setRows] = useState<Work[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [repairReasons, setRepairReasons] = useState<Record<string, string>>({});
  const [addOpen, setAddOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [vehicleFilter, setVehicleFilter] = useState("");

  const load = useCallback(async () => {
    const [vr, mr] = await Promise.all([apiFetch("/fleet/vehicles"), apiFetch("/fleet/maintenance")]);
    const vd = await vr.json(); const md = await mr.json();
    if (!vr.ok || !mr.ok) throw new Error(vd.error || md.error || "Could not load maintenance records.");
    setVehicles(vd); setRows(md);
  }, []);
  useEffect(() => { void load().catch(error => setMessage(error.message)).finally(() => setLoading(false)); }, [load]);

  async function returnToService(id: string) {
    setBusy(true);
    try {
      const response = await apiFetch(`/fleet/maintenance/${id}/return-to-service`, { method: "POST", body: JSON.stringify({ reason: repairReasons[id] }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.error);
      await load(); setMessage("Truck return to service recorded.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not update breakdown."); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; setBusy(true); setMessage("");
    try {
      const payload = new FormData(form);
      for (const key of ["breakdown_at", "returned_to_service_at"]) { const value = String(payload.get(key) || ""); if (value) payload.set(key, new Date(value).toISOString()); }
      const response = await apiFetch("/fleet/maintenance", { method: "POST", body: payload });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || Object.values(data).flat().join(" ") || "Could not save maintenance record.");
      form.reset(); setAddOpen(false); setMessage(`Maintenance saved for ${data.registration_number}.`); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not save maintenance record."); }
    finally { setBusy(false); }
  }

  const openBreakdowns = rows.filter(row => row.breakdown_at && !row.returned_to_service_at);
  const now = Date.now();
  const dueSoon = rows.filter(row => row.next_due_date && new Date(`${row.next_due_date}T23:59:59`).getTime() >= now && new Date(`${row.next_due_date}T00:00:00`).getTime() <= now + 30 * 86400000);
  const overdue = rows.filter(row => row.next_due_date && new Date(`${row.next_due_date}T23:59:59`).getTime() < now);
  const filteredRows = useMemo(() => rows.filter(row => (!vehicleFilter || row.vehicle_id === vehicleFilter) && `${row.registration_number} ${row.description} ${row.category_label} ${row.vendor || ""} ${row.failure_code || ""}`.toLowerCase().includes(search.trim().toLowerCase())).sort((a, b) => b.service_date.localeCompare(a.service_date)), [rows, search, vehicleFilter]);

  return <UiMain className="mx-auto w-full min-w-0 max-w-[1500px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
    <header className="flex flex-wrap items-end justify-between gap-4"><UiBox><UiText className="text-xs font-semibold uppercase tracking-wider text-forest">Fleet records</UiText><UiH1 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">Truck maintenance</UiH1><UiText className="mt-1 max-w-2xl text-sm text-slate-500">See trucks that need repair, track service costs, and set the next service date.</UiText></UiBox><UiBox className="flex gap-2"><UiButton type="button" onClick={() => setAddOpen(true)} className="inline-flex items-center gap-2 rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white"><Wrench size={15}/>Add service record</UiButton><UiButton type="button" onClick={() => { setBusy(true); void load().catch(error => setMessage(error.message)).finally(() => setBusy(false)); }} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"><RefreshCw size={14}/>{busy ? "Refreshing…" : "Refresh"}</UiButton></UiBox></header>
    {message && <UiAlert role="status" className="rounded-lg border border-line px-4 py-3 text-sm">{message}</UiAlert>}

    <UiBox className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[{ label: "Service records", value: rows.length, note: "Saved for your trucks", icon: ClipboardList, tone: "bg-slate-100 text-slate-700" }, { label: "Breakdowns", value: openBreakdowns.length, note: "Trucks not back in service", icon: AlertTriangle, tone: "bg-rose-50 text-rose-700" }, { label: "Service due soon", value: dueSoon.length, note: "Due in the next 30 days", icon: CalendarDays, tone: "bg-amber-50 text-amber-800" }, { label: "Overdue service", value: overdue.length, note: "Past the scheduled date", icon: Wrench, tone: "bg-rose-50 text-rose-700" }].map(item => { const Icon = item.icon; return <UiBox key={item.label} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4"><span className={`grid size-10 shrink-0 place-items-center rounded-lg ${item.tone}`}><Icon size={18}/></span><UiBox><UiText className="text-xs font-medium text-slate-500">{item.label}</UiText><UiText className="mt-1 text-2xl font-bold leading-none tabular-nums text-slate-900">{item.value}</UiText><UiText className="mt-1 text-[11px] text-slate-500">{item.note}</UiText></UiBox></UiBox>; })}</UiBox>

    {openBreakdowns.length > 0 && <UiSection aria-label="Trucks awaiting repair" className="overflow-hidden rounded-xl border border-rose-200 bg-white"><UiBox className="flex items-center gap-2 border-b border-rose-100 bg-rose-50 px-4 py-3"><AlertTriangle size={16} className="text-rose-700"/><UiText className="text-sm font-semibold text-rose-900">Trucks waiting for repair · {openBreakdowns.length}</UiText></UiBox><UiBox className="grid gap-3 p-3 md:grid-cols-2">{openBreakdowns.map(row => <UiBox key={row.id} className="rounded-lg border border-rose-100 p-4"><UiBox className="flex flex-wrap items-center justify-between gap-2"><UiText className="text-sm font-bold text-slate-900">{row.registration_number}</UiText><UiText className="rounded-full bg-rose-50 px-2.5 py-1 text-[10px] font-semibold text-rose-700">Off road</UiText></UiBox><UiText className="mt-1 text-sm text-slate-700">{row.failure_code || row.description}</UiText><UiText className="mt-1 text-xs text-slate-500">Down for {row.downtime_hours ?? "—"} hours · Since {new Date(row.breakdown_at!).toLocaleString()}</UiText><UiBox className="mt-3 flex flex-wrap gap-2"><UiInput value={repairReasons[row.id] || ""} onChange={event => setRepairReasons({ ...repairReasons, [row.id]: event.target.value })} aria-label={`Repair notes for ${row.registration_number}`} placeholder="Repair done and checks completed" className="min-w-52 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm"/><UiButton disabled={busy || !repairReasons[row.id]?.trim()} onClick={() => void returnToService(row.id)} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">Back in service</UiButton></UiBox></UiBox>)}</UiBox></UiSection>}

    <UiSection aria-label="Maintenance history" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><UiBox className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-100 p-4 sm:px-5"><UiBox><UiText className="text-base font-semibold text-slate-900">Service and repair history</UiText><UiText className="mt-1 text-xs text-slate-500">{filteredRows.length} shown · {rows.length} total</UiText></UiBox><UiBox className="flex w-full flex-wrap gap-2 sm:w-auto"><label className="relative min-w-0 flex-1 sm:w-60 sm:flex-none"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><UiInput value={search} onChange={event => setSearch(event.target.value)} aria-label="Search maintenance" placeholder="Search truck or repair" className="h-10 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-sm"/></label><UiSelect value={vehicleFilter} onChange={event => setVehicleFilter(event.target.value)} aria-label="Filter by truck" className="min-w-40 rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="">All trucks</option>{vehicles.map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration_number}</option>)}</UiSelect></UiBox></UiBox>
      {loading ? <UiBox className="p-6 text-sm text-slate-500">Loading maintenance records…</UiBox> : filteredRows.length === 0 ? <UiBox className="px-5 py-12 text-center"><Wrench className="mx-auto text-slate-300" size={28}/><UiText className="mt-3 text-sm font-semibold text-slate-800">{rows.length ? "No matching records" : "No service records yet"}</UiText><UiText className="mt-1 text-xs text-slate-500">{rows.length ? "Try another truck or search." : "Add a service or repair record to start the maintenance history."}</UiText>{(search || vehicleFilter) && <UiButton type="button" onClick={() => { setSearch(""); setVehicleFilter(""); }} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">Clear filters</UiButton>}</UiBox> : <UiBox className="grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-3 sm:p-4">{filteredRows.map(row => <UiBox key={row.id} className="flex min-w-0 flex-col rounded-xl border border-slate-200 p-4 transition hover:border-slate-300 hover:shadow-sm"><UiBox className="flex items-start justify-between gap-3"><UiBox className="min-w-0"><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{row.category_label}</UiText><UiText className="mt-1 text-sm font-bold text-slate-900">{row.registration_number}</UiText></UiBox><UiText className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">{formatDate(row.service_date)}</UiText></UiBox><UiText className="mt-3 text-sm font-medium leading-5 text-slate-800">{row.description}</UiText><UiBox className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3"><UiBox><UiText className="text-[10px] text-slate-500">Cost</UiText><UiText className="mt-1 text-sm font-semibold text-slate-900">₹{Number(row.cost).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</UiText></UiBox><UiBox><UiText className="text-[10px] text-slate-500">Odometer</UiText><UiText className="mt-1 text-sm font-semibold text-slate-900">{row.odometer_km ? `${row.odometer_km} km` : "Not recorded"}</UiText></UiBox></UiBox><UiText className="mt-3 text-xs text-slate-600">Next service: {row.next_due_date ? formatDate(row.next_due_date) : row.next_due_odometer_km ? `${row.next_due_odometer_km} km` : "Not scheduled"}</UiText>{row.vendor && <UiText className="mt-1 text-xs text-slate-500">Workshop · {row.vendor}</UiText>}{row.receipt_filename && <UiText className="mt-2 truncate border-t border-slate-100 pt-2 text-[11px] text-slate-500">Receipt saved · {row.receipt_filename}</UiText>}{row.notes && <UiText className="mt-2 line-clamp-2 text-xs text-slate-500">{row.notes}</UiText>}</UiBox>)}</UiBox>}
    </UiSection>

    <Dialog open={addOpen} onClose={() => { if (!busy) setAddOpen(false); }} fullWidth maxWidth="md" aria-labelledby="add-maintenance-title"><DialogTitle id="add-maintenance-title">Add service or repair</DialogTitle><DialogContent dividers><UiText className="mb-4 text-sm text-slate-500">Record the work completed and set a reminder for the next service.</UiText><form onSubmit={submit} encType="multipart/form-data" className="grid gap-4 p-1 sm:grid-cols-2 lg:grid-cols-3">
      <UiLabel className="text-xs font-semibold text-slate-600">Truck<UiSelect name="vehicle_id" className={input} required defaultValue=""><option value="" disabled>Select a truck</option>{vehicles.map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration_number}{vehicle.make_model ? ` · ${vehicle.make_model}` : ""}</option>)}</UiSelect></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Work type<UiSelect name="category" className={input} defaultValue="SERVICE"><option value="SERVICE">Routine service</option><option value="REPAIR">Repair</option><option value="TYRE">Tyres</option><option value="ENGINE">Engine</option><option value="BRAKES">Brakes</option><option value="ELECTRICAL">Electrical</option><option value="OTHER">Other</option></UiSelect></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">What work was done?<UiInput name="description" maxLength={240} required className={input} placeholder="e.g. Scheduled service"/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Service date<UiInput name="service_date" type="date" required className={input}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Breakdown reason <span className="font-normal text-slate-400">(optional)</span><UiInput name="failure_code" maxLength={64} className={input} placeholder="e.g. Brake issue"/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Breakdown started <span className="font-normal text-slate-400">(optional)</span><UiInput name="breakdown_at" type="datetime-local" className={input}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Truck back in service <span className="font-normal text-slate-400">(optional)</span><UiInput name="returned_to_service_at" type="datetime-local" className={input}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Truck reading (km)<UiInput name="odometer_km" type="number" min="0" step="0.01" className={input} placeholder="Optional"/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Repair cost (₹)<UiInput name="cost" type="number" min="0" step="0.01" defaultValue="0" className={input}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Workshop name<UiInput name="vendor" maxLength={180} className={input} placeholder="Optional"/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Next service date<UiInput name="next_due_date" type="date" className={input}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Next service at (km)<UiInput name="next_due_odometer_km" type="number" min="0" step="0.01" className={input} placeholder="Optional"/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Receipt or work order<UiInput name="receipt" type="file" accept=".pdf,image/jpeg,image/png,image/heic,image/heif" className={input}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600 sm:col-span-2">Notes <span className="font-normal text-slate-400">(optional)</span><UiInput name="notes" maxLength={5000} className={input} placeholder="Parts replaced or checks completed"/></UiLabel>
      {!vehicles.length && <UiText className="text-xs text-amber-800 sm:col-span-2 lg:col-span-3">Add a truck before creating a maintenance record.</UiText>}
      <UiBox className="flex items-end lg:col-span-3"><UiButton disabled={busy || !vehicles.length} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save record"}</UiButton></UiBox>
    </form></DialogContent><DialogActions><UiButton type="button" disabled={busy} onClick={() => setAddOpen(false)} className="mr-2 rounded-lg border border-line px-4 py-2 text-sm">Cancel</UiButton></DialogActions></Dialog>
  </UiMain>;
}
