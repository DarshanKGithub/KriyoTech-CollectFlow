"use client";
import { Switch } from "@/components/ui/switch";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiMain, UiSpan, UiSpinner, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Save } from "lucide-react";
type MatchingSettings = {
    rate_tolerance_percent: string | number;
    rate_tolerance_amount: string | number;
    quantity_tolerance_percent: string | number;
    quantity_tolerance_amount: string | number;
    tax_tolerance_percent: string | number;
    over_receipt_tolerance_percent: string | number;
    matching_priority: string[];
    allow_partial_grn: boolean;
    require_service_acceptance: boolean;
};
const defaults: MatchingSettings = { rate_tolerance_percent: 0, rate_tolerance_amount: 0, quantity_tolerance_percent: 0, quantity_tolerance_amount: 0, tax_tolerance_percent: 0, over_receipt_tolerance_percent: 0, matching_priority: ["GSTIN", "NAME", "ALIAS", "EMAIL_DOMAIN"], allow_partial_grn: true, require_service_acceptance: true };
export default function SettingsPage() {
    const [workflowEnabled,setWorkflowEnabled]=useState(false);
    const [workflowLoaded,setWorkflowLoaded]=useState(false);
    const [settings, setSettings] = useState(defaults);
    const [canEdit, setCanEdit] = useState(false);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    useEffect(() => {
        Promise.all([apiFetch("/matching/settings"), apiFetch("/auth/me"),apiFetch("/settings")]).then(async ([r, p, workflow]) => {
            if (!r.ok)
                throw new Error(r.status === 401 ? "Sign in to view workspace settings." : "Could not load matching settings.");
            setSettings({ ...defaults, ...await r.json() });
            if(workflow.ok){setWorkflowEnabled((await workflow.json()).automatic_invoice_workflow_enabled===true);setWorkflowLoaded(true);}
            if (p.ok)
                setCanEdit(["OWNER", "FINANCE"].includes((await p.json()).role));
        }).catch(e => setMessage(e instanceof Error ? e.message : "Could not load settings.")).finally(() => setLoading(false));
    }, []);
    async function saveWorkflow(enabled:boolean){
        setBusy(true);setMessage("");
        try{const response=await apiFetch("/settings",{method:"PATCH",body:JSON.stringify({automatic_invoice_workflow_enabled:enabled})});const data=await response.json();if(!response.ok)throw new Error(data.error?.message||"Could not update automation.");setWorkflowEnabled(enabled);setMessage(enabled?"Automatic workflow enabled for future uploads and invoice corrections. Use Resume automation for an existing invoice.":"Automatic workflow paused. Existing approvals and payments are unchanged.");}
        catch(error){setMessage(error instanceof Error?error.message:"Could not update automation.");}finally{setBusy(false);}
    }
    async function save(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setBusy(true);
        setMessage("");
        try {
            const r = await apiFetch("/matching/settings", { method: "PATCH", body: JSON.stringify({ rate_tolerance_percent: Number(form.get("rate_tolerance_percent")), rate_tolerance_amount: Number(form.get("rate_tolerance_amount")), quantity_tolerance_percent: Number(form.get("quantity_tolerance_percent")), quantity_tolerance_amount: Number(form.get("quantity_tolerance_amount")), tax_tolerance_percent: Number(form.get("tax_tolerance_percent")), over_receipt_tolerance_percent: Number(form.get("over_receipt_tolerance_percent")), matching_priority: settings.matching_priority, allow_partial_grn: form.get("allow_partial_grn") === "on", require_service_acceptance: form.get("require_service_acceptance") === "on" }) });
            const d = await r.json();
            if (!r.ok)
                throw new Error(d.error?.message || "Could not save matching controls.");
            setSettings({ ...defaults, ...d });
            setMessage("Matching controls saved and recorded in the audit log.");
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not save matching controls.");
        }
        finally {
            setBusy(false);
        }
    }
    function toggleSignal(signal: string) { setSettings(s => ({ ...s, matching_priority: s.matching_priority.includes(signal) ? s.matching_priority.filter(x => x !== signal) : [...s.matching_priority, signal] })); }
    function moveSignal(signal: string, direction: -1 | 1) {
        setSettings(s => {
            const items = [...s.matching_priority];
            const index = items.indexOf(signal);
            const next = index + direction;
            if (index < 0 || next < 0 || next >= items.length)
                return s;
            [items[index], items[next]] = [items[next], items[index]];
            return { ...s, matching_priority: items };
        });
    }
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiH1 className="mt-6 text-2xl font-bold">Matching controls</UiH1><UiText className="mt-1 text-sm text-slate-500">Configure the tolerances and vendor signals used by future invoice matching runs.</UiText>{message && <UiAlert role="status" className="mt-5 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">{message}</UiAlert>}<UiBox className="mt-6 flex items-start justify-between gap-4 rounded-xl border border-line bg-white p-5"><UiBox><UiH2 className="text-sm font-bold">Automatic invoice workflow</UiH2><UiText className="mt-2 text-xs leading-6 text-slate-500">Extract → link a unique supplier by GSTIN → validate totals → match PO and receipts → route approval. Auto-approval requires an enabled supplier and amount policy. Uncertain fields and mismatches stay in Needs attention. No bank transfer is initiated.</UiText><Link href="/approval-rules" className="mt-2 inline-block text-xs font-semibold text-forest">Configure approval policies →</Link></UiBox><Switch aria-label="Automatic invoice workflow" checked={workflowEnabled} disabled={!canEdit||busy||!workflowLoaded} onCheckedChange={enabled=>void saveWorkflow(enabled)}/></UiBox>{loading ? <ContentSkeleton variant="form" label="Loading controls" /> : <UiForm onSubmit={save} className="mt-6 space-y-5 rounded-xl border border-line bg-white p-6 shadow-card"><UiH2 className="text-sm font-bold">Tolerance controls</UiH2><UiText className="text-xs leading-5 text-slate-500">A variance is accepted when it stays within either its percentage or absolute tolerance. Zero values preserve strict matching for that dimension.</UiText><UiBox className="grid gap-4 sm:grid-cols-2">{([["Rate variance (%)", "rate_tolerance_percent"], ["Rate variance (₹)", "rate_tolerance_amount"], ["Quantity variance (%)", "quantity_tolerance_percent"], ["Quantity variance (units)", "quantity_tolerance_amount"], ["GST variance (%)", "tax_tolerance_percent"], ["Over-receipt tolerance (%)", "over_receipt_tolerance_percent"]] as const).map(([label, name]) => <UiLabel key={name} className="text-xs font-semibold">{label}<UiInput name={name} type="number" min="0" max={name.endsWith("percent") ? "100" : undefined} step="0.001" defaultValue={settings[name]} disabled={!canEdit} className="mt-2 block w-full rounded-lg border border-line px-3 py-2.5 text-sm font-normal disabled:bg-slate-50"/></UiLabel>)}</UiBox><UiBox><UiH2 className="text-sm font-bold">Vendor matching signals</UiH2><UiText className="mt-1 text-xs text-slate-500">Signals run in this priority order. Choose signals and move them to set the priority.</UiText><UiBox className="mt-3 space-y-2">{["GSTIN", "NAME", "ALIAS", "EMAIL_DOMAIN"].map(signal => { const index = settings.matching_priority.indexOf(signal); return <UiBox key={signal} className="flex items-center gap-2 text-xs"><UiInput type="checkbox" checked={index >= 0} disabled={!canEdit} onChange={() => toggleSignal(signal)}/><UiSpan className="w-32">{signal.replaceAll("_", " ")}</UiSpan>{index >= 0 && <><UiSpan className="text-slate-400">Priority {index + 1}</UiSpan><UiButton type="button" disabled={!canEdit || index === 0} onClick={() => moveSignal(signal, -1)} className="rounded border border-line px-2 py-1">↑</UiButton><UiButton type="button" disabled={!canEdit || index === settings.matching_priority.length - 1} onClick={() => moveSignal(signal, 1)} className="rounded border border-line px-2 py-1">↓</UiButton></>}</UiBox>; })}</UiBox></UiBox><UiBox className="space-y-3"><UiLabel className="flex items-center gap-2 text-xs"><UiInput name="allow_partial_grn" type="checkbox" defaultChecked={settings.allow_partial_grn} disabled={!canEdit}/>Allow invoices with partial goods receipt to continue through review</UiLabel><UiLabel className="flex items-center gap-2 text-xs"><UiInput name="require_service_acceptance" type="checkbox" defaultChecked={settings.require_service_acceptance} disabled={!canEdit}/>Require service acceptance evidence for service invoices</UiLabel></UiBox>{canEdit ? <UiButton disabled={busy} className="inline-flex items-center gap-2 rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-60">{busy ? <UiSpinner className="animate-spin" size={14}/> : <Save size={14}/>}Save matching controls</UiButton> : <UiText className="text-xs text-slate-500">Only workspace owners and finance users can edit matching controls.</UiText>}</UiForm>}</UiMain>;
}
