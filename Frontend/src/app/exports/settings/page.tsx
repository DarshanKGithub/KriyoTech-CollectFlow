"use client";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Vendor = {
    id: string;
    name: string;
};
type Mapping = {
    id: string;
    dimension: string;
    source_key: string;
    ledger_name: string;
    active: boolean;
};
const dimensions = ["VENDOR_LEDGER", "PURCHASE_LEDGER", "GST_LEDGER", "TDS_LEDGER", "COST_CENTER", "VOUCHER_TYPE"];
const labels: Record<string, string> = { VENDOR_LEDGER: "Vendor ledger", PURCHASE_LEDGER: "Purchase ledger", GST_LEDGER: "GST ledger", TDS_LEDGER: "TDS ledger", COST_CENTER: "Cost center", VOUCHER_TYPE: "Voucher type" };
export default function TallySettingsPage() {
    const [rows, setRows] = useState<Mapping[]>([]);
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [dimension, setDimension] = useState("PURCHASE_LEDGER");
    const [sourceKey, setSourceKey] = useState("default");
    const [ledgerName, setLedgerName] = useState("");
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState(false);
    const [canEdit, setCanEdit] = useState(false);
    const load = useCallback(async () => {
        const [mappingResponse, vendorResponse, profileResponse] = await Promise.all([apiFetch("/tally-mappings"), apiFetch("/vendors"), apiFetch("/auth/me")]);
        if (mappingResponse.ok)
            setRows(await mappingResponse.json());
        if (vendorResponse.ok)
            setVendors(await vendorResponse.json());
        if (profileResponse.ok) {
            const profile = await profileResponse.json();
            setCanEdit(["OWNER", "FINANCE"].includes(profile.role));
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    async function save(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setNotice("");
        const response = await apiFetch("/tally-mappings", { method: "POST", body: JSON.stringify({ dimension, source_key: sourceKey.trim(), ledger_name: ledgerName }) });
        const data = await response.json();
        setNotice(response.ok ? "Mapping saved and audited. New exports will use it." : data.error || "Could not save this mapping.");
        if (response.ok) {
            setLedgerName("");
            await load();
        }
        setBusy(false);
    }
    async function remove(row: Mapping) {
        const response = await apiFetch(`/tally-mappings/${row.id}`, { method: "DELETE" });
        setNotice(response.ok ? "Mapping removed. Exports will use the fallback mapping." : "Could not remove this mapping.");
        if (response.ok)
            await load();
    }
    const hint = dimension === "GST_LEDGER" ? "default or GST rate, e.g. 18" : dimension === "TDS_LEDGER" ? "default or TDS section, e.g. 194C" : dimension === "PURCHASE_LEDGER" ? "default or invoice category, e.g. SERVICES" : dimension === "COST_CENTER" ? "default, category:SERVICES, or vendor:<vendor UUID>" : "default";
    return <UiMain className="w-full min-w-0 space-y-6 px-5 py-8">
    <UiHeader><Link href="/exports" className="text-xs font-semibold text-forest">← Tally export</Link><UiText className="mt-5 text-xs font-bold uppercase tracking-[.14em] text-forest">Accounting setup</UiText><UiH1 className="mt-1 text-2xl font-bold">Tally ledger mappings</UiH1><UiText className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">Map KriyoPay vendors, invoice categories, GST rates, TDS sections, and cost centers to the names in your Tally company. Existing fallback names remain in use until you add a mapping. Changes apply to future CSV exports only.</UiText>{!canEdit && <UiText className="mt-2 text-xs text-slate-500">Only workspace owners and finance users can change these mappings.</UiText>}</UiHeader>
    {notice && <UiAlert role="status" className="rounded-lg bg-mint px-4 py-3 text-sm text-forest">{notice}</UiAlert>}
    <UiForm onSubmit={save} className="grid gap-3 rounded-xl border border-line bg-white p-5 md:grid-cols-4">
      <UiLabel className="text-xs font-semibold">Mapping type<UiSelect value={dimension} onChange={event => { setDimension(event.target.value); setSourceKey(event.target.value === "VENDOR_LEDGER" ? "" : "default"); }} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2 text-sm">{dimensions.map(value => <option key={value} value={value}>{labels[value]}</option>)}</UiSelect></UiLabel>
      {dimension === "VENDOR_LEDGER" ? <UiLabel className="text-xs font-semibold">Vendor<UiSelect required value={sourceKey} onChange={event => setSourceKey(event.target.value)} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2 text-sm"><option value="">Select vendor</option>{vendors.map(vendor => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</UiSelect></UiLabel> : <UiLabel className="text-xs font-semibold">Source key<UiInput required value={sourceKey} onChange={event => setSourceKey(event.target.value)} placeholder={hint} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2 text-sm"/></UiLabel>}
      <UiLabel className="text-xs font-semibold">Tally name<UiInput required maxLength={120} value={ledgerName} onChange={event => setLedgerName(event.target.value)} placeholder="Name in Tally" className="mt-1.5 w-full rounded-lg border border-line px-3 py-2 text-sm"/></UiLabel>
      <UiButton disabled={!canEdit || busy || !sourceKey.trim() || !ledgerName.trim()} className="self-end rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save mapping"}</UiButton>
      <UiText className="text-[11px] leading-5 text-slate-400 md:col-span-4">Use <code>default</code> for a dimension-wide fallback. GST keys are percentages. Cost center keys can be <code>category:SERVICES</code> or <code>vendor:&lt;vendor UUID&gt;</code>. Voucher type accepts only <code>default</code>.</UiText>
    </UiForm>
    <UiSection className="overflow-hidden rounded-xl border border-line bg-white"><UiBox className="border-b border-line px-5 py-4"><UiH2 className="text-sm font-bold">Current mappings</UiH2><UiText className="mt-1 text-xs text-slate-500">Mappings are workspace-specific and included in the generated export.</UiText></UiBox><UiBox className="divide-y divide-line">{rows.map(row => <UiBox key={row.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm"><UiBox><UiText className="font-semibold">{labels[row.dimension] || row.dimension} <UiSpan className="font-normal text-slate-500">{row.source_key}</UiSpan></UiText><UiText className="mt-0.5 text-xs text-slate-500">→ {row.ledger_name}{!row.active && " · inactive"}</UiText></UiBox>{canEdit && <UiButton onClick={() => void remove(row)} className="rounded border border-line px-3 py-1.5 text-xs">Remove</UiButton>}</UiBox>)}{!rows.length && <UiText className="px-5 py-8 text-center text-sm text-slate-500">No custom mappings yet. Your current fallback ledger names remain active.</UiText>}</UiBox></UiSection>
  </UiMain>;
}
