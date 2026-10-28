"use client";

import { useCallback, useEffect, useState } from "react";
import { UiAlert, UiBox, UiButton, UiH1, UiInput, UiLabel, UiMain, UiSelect, UiText } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";

type Vehicle = { id: string; registration_number: string; make_model?: string };
type TruckDocument = { id: string; vehicle_id: string; registration_number: string; filename: string; kind_label: string; document_number: string; issued_on: string | null; expires_on: string | null; days_until_expiry: number | null; status: string; notes: string };
const input = "mt-1 block w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm";

export default function TruckDocumentsPage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [rows, setRows] = useState<TruckDocument[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => {
    const [vr, dr] = await Promise.all([apiFetch("/fleet/vehicles"), apiFetch("/fleet/vehicle-documents")]);
    const vd = await vr.json(); const dd = await dr.json();
    if (!vr.ok || !dr.ok) throw new Error(vd.error || dd.error || "Could not load truck documents.");
    setVehicles(vd); setRows(dd);
  }, []);
  useEffect(() => { void load().catch(e => setMessage(e.message)); }, [load]);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const form = new FormData(event.currentTarget);
      const response = await apiFetch("/fleet/vehicle-documents", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || Object.values(data).flat().join(" ") || "Could not save truck document.");
      event.currentTarget.reset(); setMessage(`Saved ${data.kind_label} for ${data.registration_number}.`); await load();
    } catch (e) { setMessage(e instanceof Error ? e.message : "Could not save truck document."); }
    finally { setBusy(false); }
  }
  async function download(id: string, filename: string) {
    const response = await apiFetch(`/fleet/vehicle-documents/${id}/download`);
    if (!response.ok) { setMessage("Could not download this document."); return; }
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
  }
  return <UiMain className="w-full min-w-0 space-y-5 px-4 py-6 sm:px-6 lg:px-8">
    <header><UiText className="text-xs font-semibold uppercase tracking-wider text-forest">Fleet records</UiText><UiH1 className="mt-1 text-2xl font-bold">Truck documents</UiH1><UiText className="mt-1 text-sm text-slate-500">Keep each truck’s PUC, insurance, permits, registration and certificates together. Expiry alerts appear in Fleet alerts.</UiText></header>
    {message && <UiAlert className="rounded-lg border border-line px-4 py-3 text-sm">{message}</UiAlert>}
    <form onSubmit={submit} className="grid gap-4 rounded-xl border border-line p-4 md:grid-cols-3">
      <UiLabel className="text-sm font-medium">Truck<UiSelect name="vehicle_id" className={input} required defaultValue=""><option value="" disabled>Select truck</option>{vehicles.map(v => <option key={v.id} value={v.id}>{v.registration_number}{v.make_model ? ` · ${v.make_model}` : ""}</option>)}</UiSelect></UiLabel>
      <UiLabel className="text-sm font-medium">Document type<UiSelect name="kind" className={input} required defaultValue="PUC"><option value="PUC">PUC certificate</option><option value="INSURANCE">Insurance</option><option value="REGISTRATION">Registration certificate</option><option value="PERMIT">Permit</option><option value="FITNESS">Fitness certificate</option><option value="TAX">Road tax</option><option value="OTHER">Other</option></UiSelect></UiLabel>
      <UiLabel className="text-sm font-medium">Document file<UiInput name="file" type="file" accept=".pdf,image/jpeg,image/png,image/heic,image/heif" className={input} required /></UiLabel>
      <UiLabel className="text-sm font-medium">Document number (optional)<UiInput name="document_number" maxLength={100} className={input} placeholder="Policy or certificate number" /></UiLabel>
      <UiLabel className="text-sm font-medium">Issue date<UiInput name="issued_on" type="date" className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium">Expiry date<UiInput name="expires_on" type="date" className={input} /></UiLabel>
      <UiLabel className="text-sm font-medium md:col-span-2">Notes<UiInput name="notes" maxLength={5000} className={input} placeholder="Insurer, agent, renewal note…" /></UiLabel>
      <UiBox className="flex items-end"><UiButton disabled={busy || !vehicles.length} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save truck document"}</UiButton></UiBox>
    </form>
    <section className="overflow-hidden rounded-xl border border-line"><div className="border-b border-line px-4 py-3 font-semibold">Saved documents <span className="ml-2 text-xs text-slate-500">{rows.length}</span></div>{!rows.length ? <p className="p-6 text-sm text-slate-500">No truck documents yet. Add a certificate above to start tracking its expiry.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="bg-slate-50 text-xs text-slate-500"><th className="p-3">Truck</th><th className="p-3">Document</th><th className="p-3">Number</th><th className="p-3">Expires</th><th className="p-3">Status</th><th className="p-3">File</th></tr></thead><tbody>{rows.map(row => <tr key={row.id} className="border-t border-line"><td className="p-3 font-medium">{row.registration_number}</td><td className="p-3">{row.kind_label}</td><td className="p-3">{row.document_number || "—"}</td><td className="p-3">{row.expires_on || "No expiry recorded"}</td><td className="p-3"><span className={row.status === "EXPIRED" ? "font-semibold text-rose-600" : row.status === "DUE_SOON" ? "font-semibold text-amber-600" : "text-emerald-700"}>{row.status === "EXPIRED" ? "Expired" : row.status === "DUE_SOON" ? `Due in ${row.days_until_expiry} days` : row.status === "VALID" ? "Valid" : "No expiry"}</span></td><td className="p-3"><button onClick={() => void download(row.id, row.filename)} className="font-semibold text-forest hover:underline">{row.filename}</button></td></tr>)}</tbody></table></div>}</section>
  </UiMain>;
}
