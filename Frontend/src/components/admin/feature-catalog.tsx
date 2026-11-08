"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { useAdminIdentity } from "@/components/admin/admin-context";
import { Switch } from "@/components/ui/switch";

export const solutionNames = ["InvoiceFlow", "Procure", "Reconcile", "SettleView", "Transport", "DriverFinance"];
export type CatalogFeature = { key:string; name:string; description:string; solution_name?:string; monthly_price?:number|null; price_basis?:string };
export const featurePrice = (price?:number|null) => price == null ? "Not priced" : new Intl.NumberFormat("en-IN", {style:"currency",currency:"INR",maximumFractionDigits:2}).format(price/100);
export function groupFeatures<T extends {solution_name?:string}>(features:T[]) {
  return [...solutionNames, "Other"].map(name=>({name,features:features.filter(feature=>(feature.solution_name||"Other")===name)}));
}

export function GroupedFeatureAccess({features,busy,onToggle}:{features:(CatalogFeature&{enabled:boolean;source?:string})[];busy:boolean;onToggle:(key:string,enabled:boolean)=>void}){
  return <div className="mt-5 space-y-4">{groupFeatures(features).filter(group=>group.features.length).map(group=>{
    const enabled=group.features.filter(f=>f.enabled);
    const total=enabled.reduce((sum,f)=>sum+(f.monthly_price||0),0);
    const unpriced=enabled.filter(f=>f.monthly_price==null).length;
    return <details key={group.name} open={group.name==="Transport"||group.name==="DriverFinance"} className="overflow-hidden rounded-xl border border-line"><summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 bg-slate-50 px-4 py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest"><div><h3 className="text-sm font-semibold">{group.name}</h3><p className="text-[11px] text-slate-500">{enabled.length} of {group.features.length} enabled</p></div><p className="text-right text-xs font-medium">{featurePrice(total)} / month<span className="mt-0.5 block text-[10px] font-normal text-slate-500">Catalog estimate{unpriced?` · ${unpriced} unpriced`:""}</span></p></summary><div className="divide-y divide-line">{group.features.map(feature=><div key={feature.key} className="flex items-center gap-3 px-4 py-3"><Switch aria-label={`${feature.name} access`} checked={feature.enabled} disabled={busy} onCheckedChange={enabled=>onToggle(feature.key,enabled)}/><div className="min-w-0 flex-1"><p className="text-sm font-medium">{feature.name}</p><p className="mt-0.5 text-[10px] text-slate-500">{feature.key==="fleet_management"?"Master access for Transport and DriverFinance":feature.source||feature.description||feature.key}</p></div><p className="shrink-0 text-xs tabular-nums text-slate-600">{featurePrice(feature.monthly_price)}</p></div>)}</div></details>;
  })}</div>;
}

export function FeatureCatalogPricing({features,onSaved}:{features:CatalogFeature[];onSaved:()=>Promise<void>}) {
  const identity=useAdminIdentity();
  const [editing,setEditing]=useState<CatalogFeature|null>(null);
  const [price,setPrice]=useState("");const [solution,setSolution]=useState("");
  const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");
  const [active,setActive]=useState("Transport");
  async function save(event:React.FormEvent){
    event.preventDefault();if(!editing)return;
    const raw=price.trim();
    if(raw&&!/^\d{1,9}(\.\d{1,2})?$/.test(raw)){setMessage("Enter a non-negative rupee amount with at most two decimal places.");return;}
    const [whole,fraction=""]=raw.split(".");
    const paise=raw?Number(whole)*100+Number(fraction.padEnd(2,"0")):null;
    setBusy(true);setMessage("");
    try{const response=await apiFetch(`/admin/features/${editing.key}/pricing`,{method:"PATCH",body:JSON.stringify({solution_name:solution,monthly_price:paise,price_basis:"COMPANY",reason})});const body=await response.json();if(!response.ok)throw new Error(body.error||JSON.stringify(body));await onSaved();setEditing(null);setMessage("Catalog price saved. Existing invoices and checkout amounts are unchanged.");}catch(error){setMessage(error instanceof Error?error.message:"Could not save price.");}finally{setBusy(false);}
  }
  return <section className="mt-6 rounded-xl border border-line bg-white p-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">Solution & feature pricing</h2><p className="mt-1 text-xs leading-5 text-slate-500">Monthly catalog prices per company. Configure access separately below. These prices are commercial estimates; customer checkout currently uses the subscription plan price.</p></div><span className="rounded-full bg-mint px-3 py-1 text-xs font-medium text-forest">6 solutions · INR / company / month</span></div>
    {message&&<p role="status" className="mt-3 rounded-lg border border-line p-3 text-sm">{message}</p>}
    <div role="tablist" aria-label="Solution pricing" className="my-4 flex flex-wrap gap-2">{solutionNames.map(name=><button key={name} type="button" role="tab" aria-selected={active===name} onClick={()=>setActive(name)} className={`rounded-lg border px-3 py-2 text-xs font-semibold ${active===name?"border-forest bg-forest text-white":"border-line text-slate-600"}`}>{name}<span className="ml-2 opacity-70">{features.filter(f=>f.solution_name===name).length}</span></button>)}</div>
    <div className="divide-y divide-line">{features.filter(f=>f.solution_name===active).map(feature=><div key={feature.key} className="flex flex-wrap items-center gap-3 py-3"><div className="min-w-0 flex-1"><p className="text-sm font-semibold">{feature.name}</p><p className="mt-0.5 text-xs text-slate-500">{feature.description||feature.key}</p></div><div className="text-right"><p className="text-sm font-semibold tabular-nums">{featurePrice(feature.monthly_price)}</p><p className="text-[10px] text-slate-500">per company / month</p></div>{identity?.role==="SUPER_ADMIN"&&<button type="button" disabled={busy} onClick={()=>{setEditing(feature);setPrice(feature.monthly_price==null?"":(feature.monthly_price/100).toFixed(2));setSolution(feature.solution_name||active);setReason("");}} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold text-forest">Edit price</button>}</div>)}</div>
    {!features.some(f=>f.solution_name===active)&&<p className="py-6 text-center text-sm text-slate-500">No features assigned to this solution.</p>}
    {editing&&<form onSubmit={event=>void save(event)} className="mt-4 space-y-3 rounded-lg border border-line bg-slate-50 p-4"><h3 className="text-sm font-semibold">Edit {editing.name}</h3><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-medium">Solution<select value={solution} onChange={e=>setSolution(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-white p-2">{solutionNames.map(name=><option key={name}>{name}</option>)}</select></label><label className="text-xs font-medium">Monthly price (₹ / company)<input inputMode="decimal" value={price} onChange={e=>setPrice(e.target.value)} placeholder="Leave blank for not priced" className="mt-1 w-full rounded-lg border border-line bg-white p-2"/></label></div><label className="block text-xs font-medium">Reason for change<input required minLength={8} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-white p-2"/></label><div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={()=>setEditing(null)} className="rounded-lg border border-line px-3 py-2 text-xs">Cancel</button><button disabled={busy} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">{busy?"Saving…":"Save catalog price"}</button></div></form>}
  </section>;
}
