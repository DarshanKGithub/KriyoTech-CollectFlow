"use client";

import { useCallback, useEffect, useState } from "react";
import { UiAlert, UiBox, UiButton, UiH1, UiInput, UiLabel, UiMain, UiSelect, UiText } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";

type Vehicle = { id: string; registration_number: string; make_model?: string };
type Work = { id: string; vehicle_id: string; registration_number: string; category_label: string; description: string; service_date: string; odometer_km: string | null; cost: string; vendor: string; next_due_date: string | null; next_due_odometer_km: string | null; receipt_filename: string | null; notes: string; breakdown_at:string|null; returned_to_service_at:string|null; downtime_hours:number|null; failure_code:string };
const input = "mt-1 block w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm";

export default function TruckMaintenancePage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]); const [rows, setRows] = useState<Work[]>([]);
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState("");
  const [repairReasons,setRepairReasons] = useState<Record<string,string>>({});
  async function returnToService(id:string){setBusy(true);try{const r=await apiFetch(`/fleet/maintenance/${id}/return-to-service`,{method:"POST",body:JSON.stringify({reason:repairReasons[id]})});const d=await r.json();if(!r.ok)throw new Error(d.error);await load();setMessage("Truck return to service recorded.");}catch(e){setMessage(e instanceof Error?e.message:"Could not update breakdown.");}finally{setBusy(false);}}
  const load = useCallback(async () => {
    const [vr, mr] = await Promise.all([apiFetch("/fleet/vehicles"), apiFetch("/fleet/maintenance")]);
    const vd = await vr.json(); const md = await mr.json();
    if (!vr.ok || !mr.ok) throw new Error(vd.error || md.error || "Could not load maintenance records.");
    setVehicles(vd); setRows(md);
  }, []);
  useEffect(() => { void load().catch(e => setMessage(e.message)); }, [load]);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; setBusy(true); setMessage("");
    try {
      const payload = new FormData(form);
      for (const key of ["breakdown_at", "returned_to_service_at"]) { const value = String(payload.get(key) || ""); if(value) payload.set(key,new Date(value).toISOString()); }
      const response = await apiFetch("/fleet/maintenance", { method: "POST", body: payload });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || Object.values(data).flat().join(" ") || "Could not save maintenance record.");
      form.reset(); setMessage(`Maintenance saved for ${data.registration_number}.`); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Could not save maintenance record."); }
    finally { setBusy(false); }
  }
  return <UiMain className="w-full min-w-0 space-y-5 px-4 py-6 sm:px-6 lg:px-8">
    <header><UiText className="text-xs font-semibold uppercase tracking-wider text-forest">Fleet records</UiText><UiH1 className="mt-1 text-2xl font-bold">Truck maintenance</UiH1><UiText className="mt-1 text-sm text-slate-500">Log services and repairs, track spend, and set the next date or odometer reminder for each truck.</UiText></header>
    {message && <UiAlert className="rounded-lg border border-line px-4 py-3 text-sm">{message}</UiAlert>}
    {rows.filter(r=>r.breakdown_at&&!r.returned_to_service_at).map(r=><section key={r.id} className="rounded-xl border border-line p-4"><UiText className="font-semibold">Open breakdown · {r.registration_number} · {r.failure_code||r.description}</UiText><UiText className="text-sm">Recorded downtime: {r.downtime_hours} hours</UiText><UiInput placeholder="Repair completed and inspection notes" value={repairReasons[r.id]||""} onChange={e=>setRepairReasons({...repairReasons,[r.id]:e.target.value})} className={input}/><UiButton disabled={busy||!repairReasons[r.id]?.trim()} onClick={()=>void returnToService(r.id)}>Record return to service</UiButton></section>)}
    <form onSubmit={submit} encType="multipart/form-data" className="grid gap-4 rounded-xl border border-line p-4 md:grid-cols-3">
      <UiLabel className="text-sm font-medium">Truck<UiSelect name="vehicle_id" className={input} required defaultValue=""><option value="" disabled>Select truck</option>{vehicles.map(v => <option key={v.id} value={v.id}>{v.registration_number}{v.make_model ? ` · ${v.make_model}` : ""}</option>)}</UiSelect></UiLabel>
      <UiLabel className="text-sm font-medium">Work type<UiSelect name="category" className={input} defaultValue="SERVICE"><option value="SERVICE">Routine service</option><option value="REPAIR">Repair</option><option value="TYRE">Tyres</option><option value="ENGINE">Engine</option><option value="BRAKES">Brakes</option><option value="ELECTRICAL">Electrical</option><option value="OTHER">Other</option></UiSelect></UiLabel>
      <UiLabel className="text-sm font-medium">Description<UiInput name="description" maxLength={240} required className={input} placeholder="e.g. 40,000 km scheduled service" /></UiLabel>
      <UiLabel className="text-sm font-medium">Service date<UiInput name="service_date" type="date" required className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium">Failure code<UiInput name="failure_code" maxLength={64} className={input} placeholder="e.g. BRAKE-01" /></UiLabel>
      <UiLabel className="text-sm font-medium">Breakdown started<UiInput name="breakdown_at" type="datetime-local" className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium">Returned to service<UiInput name="returned_to_service_at" type="datetime-local" className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium">Odometer at service (km)<UiInput name="odometer_km" type="number" min="0" step="0.01" className={input} placeholder="Optional" /></UiLabel>
      <UiLabel className="text-sm font-medium">Cost (₹)<UiInput name="cost" type="number" min="0" step="0.01" defaultValue="0" className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium">Workshop / vendor<UiInput name="vendor" maxLength={180} className={input} placeholder="Workshop name" /></UiLabel>
      <UiLabel className="text-sm font-medium">Next service date<UiInput name="next_due_date" type="date" className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium">Next service at (km)<UiInput name="next_due_odometer_km" type="number" min="0" step="0.01" className={input} placeholder="Optional" /></UiLabel>
      <UiLabel className="text-sm font-medium">Receipt / work order<UiInput name="receipt" type="file" accept=".pdf,image/jpeg,image/png,image/heic,image/heif" className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium md:col-span-2">Notes<UiInput name="notes" maxLength={5000} className={input} placeholder="Parts replaced, findings, warranty…" /></UiLabel>
      <UiBox className="flex items-end"><UiButton disabled={busy || !vehicles.length} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save maintenance record"}</UiButton></UiBox>
    </form>
    <section className="overflow-hidden rounded-xl border border-line"><div className="border-b border-line px-4 py-3 font-semibold">Maintenance history <span className="ml-2 text-xs text-slate-500">{rows.length}</span></div>{!rows.length ? <p className="p-6 text-sm text-slate-500">No service or repair records yet.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm"><thead><tr className="bg-slate-50 text-xs text-slate-500"><th className="p-3">Truck</th><th className="p-3">Work</th><th className="p-3">Service date</th><th className="p-3">Odometer</th><th className="p-3">Cost</th><th className="p-3">Vendor</th><th className="p-3">Next due</th><th className="p-3">Receipt</th></tr></thead><tbody>{rows.map(row => <tr key={row.id} className="border-t border-line"><td className="p-3 font-medium">{row.registration_number}</td><td className="p-3"><div>{row.description}</div><div className="text-xs text-slate-500">{row.category_label}</div></td><td className="p-3">{row.service_date}</td><td className="p-3">{row.odometer_km ? `${row.odometer_km} km` : "—"}</td><td className="p-3">₹{Number(row.cost).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td><td className="p-3">{row.vendor || "—"}</td><td className="p-3">{row.next_due_date || (row.next_due_odometer_km ? `${row.next_due_odometer_km} km` : "Not scheduled")}</td><td className="p-3">{row.receipt_filename || "—"}</td></tr>)}</tbody></table></div>}</section>
  </UiMain>;
}
