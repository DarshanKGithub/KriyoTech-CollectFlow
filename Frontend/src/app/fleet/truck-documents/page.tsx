"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { UiAlert, UiBox, UiButton, UiH1, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiText } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
import { AlertTriangle, CalendarDays, CheckCircle2, FileText, RefreshCw, Search, Truck, Upload } from "lucide-react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";

type Vehicle = { id: string; registration_number: string; make_model?: string };
type TruckDocument = { id: string; vehicle_id: string; registration_number: string; filename: string; kind_label: string; document_number: string; issued_on: string | null; expires_on: string | null; days_until_expiry: number | null; status: string; notes: string };
const input = "mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-forest";
const statusText = (row: TruckDocument) => row.status === "EXPIRED" ? "Expired" : row.status === "DUE_SOON" ? `Due in ${row.days_until_expiry} days` : row.status === "VALID" ? "Valid" : "No expiry date";
const statusTone = (status: string) => status === "EXPIRED" ? "bg-rose-50 text-rose-700" : status === "DUE_SOON" ? "bg-amber-50 text-amber-800" : status === "VALID" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600";

export default function TruckDocumentsPage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [rows, setRows] = useState<TruckDocument[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const load = useCallback(async () => {
    const [vr, dr] = await Promise.all([apiFetch("/fleet/vehicles"), apiFetch("/fleet/vehicle-documents")]);
    const vd = await vr.json(); const dd = await dr.json();
    if (!vr.ok || !dr.ok) throw new Error(vd.error || dd.error || "Could not load truck documents.");
    setVehicles(vd); setRows(dd);
  }, []);
  useEffect(() => { void load().catch(e => setMessage(e.message)).finally(() => setLoading(false)); }, [load]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    const formElement = event.currentTarget;
    try {
      const form = new FormData(formElement);
      const response = await apiFetch("/fleet/vehicle-documents", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || Object.values(data).flat().join(" ") || "Could not save truck document.");
      formElement.reset(); setAddDialogOpen(false); setMessage(`Saved ${data.kind_label} for ${data.registration_number}.`); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Could not save truck document."); }
    finally { setBusy(false); }
  }
  async function download(id: string, filename: string) {
    const response = await apiFetch(`/fleet/vehicle-documents/${id}/download`);
    if (!response.ok) { setMessage("Could not download this document."); return; }
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  const filteredRows = useMemo(() => rows.filter(row => (!statusFilter || row.status === statusFilter) && `${row.registration_number} ${row.kind_label} ${row.document_number} ${row.filename}`.toLowerCase().includes(search.trim().toLowerCase())).sort((a, b) => ({ EXPIRED: 0, DUE_SOON: 1, VALID: 2 }[a.status] ?? 3) - ({ EXPIRED: 0, DUE_SOON: 1, VALID: 2 }[b.status] ?? 3)), [rows, search, statusFilter]);
  const expiredCount = rows.filter(row => row.status === "EXPIRED").length;
  const dueSoonCount = rows.filter(row => row.status === "DUE_SOON").length;
  const validCount = rows.filter(row => row.status === "VALID").length;

  return <UiMain className="mx-auto w-full min-w-0 max-w-[1500px] space-y-6 px-4 py-6 sm:px-6 lg:px-8">
    <header className="flex flex-wrap items-end justify-between gap-4"><UiBox><UiText className="text-xs font-semibold uppercase tracking-wider text-forest">Fleet records</UiText><UiH1 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">Truck documents</UiH1><UiText className="mt-1 max-w-2xl text-sm text-slate-500">Keep insurance, permits, PUC and certificates together. We’ll flag documents that are expired or nearly due.</UiText></UiBox><UiBox className="flex flex-wrap gap-2"><UiButton type="button" onClick={() => setAddDialogOpen(true)} className="inline-flex items-center gap-2 rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800"><Upload size={15}/>Add document</UiButton><UiButton type="button" onClick={() => { setBusy(true); void load().catch(error => setMessage(error.message)).finally(() => setBusy(false)); }} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"><RefreshCw size={14}/>{busy ? "Refreshing…" : "Refresh"}</UiButton></UiBox></header>
    {message && <UiAlert role="status" className="rounded-lg border border-line px-4 py-3 text-sm">{message}</UiAlert>}

    <UiSection aria-label="Truck document status" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {[{ label: "All documents", value: rows.length, hint: "Saved for your trucks", icon: FileText, tone: "bg-slate-100 text-slate-700" }, { label: "Expired", value: expiredCount, hint: "Renew these now", icon: AlertTriangle, tone: "bg-rose-50 text-rose-700" }, { label: "Due soon", value: dueSoonCount, hint: "Plan a renewal", icon: CalendarDays, tone: "bg-amber-50 text-amber-800" }, { label: "Up to date", value: validCount, hint: "No action needed", icon: CheckCircle2, tone: "bg-emerald-50 text-emerald-700" }].map(item => { const Icon = item.icon; return <UiBox key={item.label} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4"><span className={`grid size-10 shrink-0 place-items-center rounded-lg ${item.tone}`}><Icon size={18}/></span><UiBox><UiText className="text-xs font-medium text-slate-500">{item.label}</UiText><UiText className="mt-1 text-2xl font-bold leading-none tabular-nums text-slate-900">{item.value}</UiText><UiText className="mt-1 text-[11px] text-slate-500">{item.hint}</UiText></UiBox></UiBox>; })}
    </UiSection>

    <Dialog open={addDialogOpen} onClose={() => { if (!busy) setAddDialogOpen(false); }} fullWidth maxWidth="md" aria-labelledby="add-truck-document-title"><DialogTitle id="add-truck-document-title">Add a truck document</DialogTitle><DialogContent dividers><UiText className="mb-4 text-sm text-slate-500">Choose the truck, attach its file, and add the expiry date so reminders work.</UiText>
      <form onSubmit={submit} className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3 sm:p-5">
        <UiLabel className="text-xs font-semibold text-slate-600">Truck<UiSelect name="vehicle_id" className={input} required defaultValue=""><option value="" disabled>Select a truck</option>{vehicles.map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration_number}{vehicle.make_model ? ` · ${vehicle.make_model}` : ""}</option>)}</UiSelect></UiLabel>
        <UiLabel className="text-xs font-semibold text-slate-600">Document type<UiSelect name="kind" className={input} required defaultValue="PUC"><option value="PUC">PUC certificate</option><option value="INSURANCE">Insurance</option><option value="REGISTRATION">Registration certificate</option><option value="PERMIT">Permit</option><option value="FITNESS">Fitness certificate</option><option value="TAX">Road tax</option><option value="OTHER">Other</option></UiSelect></UiLabel>
        <UiLabel className="text-xs font-semibold text-slate-600">Choose file<UiInput name="file" type="file" accept=".pdf,image/jpeg,image/png,image/heic,image/heif" className={input} required/></UiLabel>
        <UiLabel className="text-xs font-semibold text-slate-600">Document number <span className="font-normal text-slate-400">(optional)</span><UiInput name="document_number" maxLength={100} className={input} placeholder="Policy or certificate number"/></UiLabel>
        <UiLabel className="text-xs font-semibold text-slate-600">Issue date <span className="font-normal text-slate-400">(optional)</span><UiInput name="issued_on" type="date" className={input}/></UiLabel>
        <UiLabel className="text-xs font-semibold text-slate-600">Expiry date <span className="font-normal text-slate-400">(needed for reminders)</span><UiInput name="expires_on" type="date" className={input}/></UiLabel>
        <UiLabel className="text-xs font-semibold text-slate-600 lg:col-span-2">Notes <span className="font-normal text-slate-400">(optional)</span><UiInput name="notes" maxLength={5000} className={input} placeholder="Insurer, agent, or renewal note"/></UiLabel>
        <UiBox className="flex items-end"><UiButton disabled={busy || !vehicles.length} className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"><Upload size={15}/>{busy ? "Saving…" : "Save document"}</UiButton></UiBox>
        {!vehicles.length && <UiText className="text-xs text-amber-800 sm:col-span-2 lg:col-span-3">Add a truck before uploading its documents.</UiText>}
      </form>
    </DialogContent><DialogActions><UiButton type="button" disabled={busy} onClick={() => setAddDialogOpen(false)} className="mr-2 rounded-lg border border-line px-4 py-2 text-sm">Cancel</UiButton></DialogActions></Dialog>

    <UiSection aria-label="Saved truck documents" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><UiBox className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-100 p-4 sm:px-5"><UiBox><UiText className="text-base font-semibold text-slate-900">Saved documents</UiText><UiText className="mt-1 text-xs text-slate-500">{filteredRows.length} shown · {rows.length} total</UiText></UiBox><UiBox className="flex w-full flex-wrap gap-2 sm:w-auto"><label className="relative min-w-0 flex-1 sm:w-60 sm:flex-none"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><UiInput value={search} onChange={event => setSearch(event.target.value)} aria-label="Search truck documents" placeholder="Search truck or document" className="h-10 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-sm"/></label><UiSelect value={statusFilter} onChange={event => setStatusFilter(event.target.value)} aria-label="Filter by document status" className="min-w-36 rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="">All statuses</option><option value="EXPIRED">Expired</option><option value="DUE_SOON">Due soon</option><option value="VALID">Up to date</option></UiSelect></UiBox></UiBox>
      {loading ? <UiBox className="p-6 text-sm text-slate-500">Loading documents…</UiBox> : filteredRows.length === 0 ? <UiBox className="px-5 py-12 text-center"><FileText className="mx-auto text-slate-300" size={28}/><UiText className="mt-3 text-sm font-semibold text-slate-800">{rows.length ? "No matching documents" : "No documents saved yet"}</UiText><UiText className="mt-1 text-xs text-slate-500">{rows.length ? "Try another search or status filter." : "Add the truck’s insurance, PUC, permit, or registration above."}</UiText>{(search || statusFilter) && <UiButton type="button" onClick={() => { setSearch(""); setStatusFilter(""); }} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">Clear filters</UiButton>}</UiBox> : <UiBox className="grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-3 sm:p-4">{filteredRows.map(row => <UiBox key={row.id} className="flex min-w-0 flex-col rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm"><UiBox className="flex items-start justify-between gap-3"><UiBox className="min-w-0"><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{row.kind_label}</UiText><UiText className="mt-1 truncate text-sm font-semibold text-slate-900">{row.registration_number}</UiText></UiBox><UiText className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusTone(row.status)}`}>{statusText(row)}</UiText></UiBox><UiBox className="mt-4 space-y-2 rounded-lg bg-slate-50 p-3"><UiBox className="flex justify-between gap-2 text-xs"><span className="text-slate-500">Document number</span><span className="truncate text-right font-medium text-slate-800">{row.document_number || "Not added"}</span></UiBox><UiBox className="flex justify-between gap-2 text-xs"><span className="text-slate-500">Expires</span><span className="text-right font-medium text-slate-800">{row.expires_on ? new Date(`${row.expires_on}T00:00:00`).toLocaleDateString() : "No date recorded"}</span></UiBox>{row.notes && <UiText className="line-clamp-2 border-t border-slate-200 pt-2 text-xs text-slate-600">{row.notes}</UiText>}</UiBox><UiButton type="button" onClick={() => void download(row.id, row.filename)} className="mt-3 inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"><FileText size={14}/><span className="max-w-full truncate">Download · {row.filename}</span></UiButton></UiBox>)}</UiBox>}
    </UiSection>
  </UiMain>;
}
