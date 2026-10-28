"use client";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiMain, UiModal, UiSection, UiSpan, UiSpinner, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTextarea, UiTh } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { ShieldAlert } from "lucide-react";
type ExceptionRow = {
    id: string;
    invoice_id: string;
    invoice_number: string;
    code: string;
    severity: string;
    status: string;
    details: Record<string, unknown>;
};
type Profile = {
    role: string;
};
export default function ExceptionsPage() {
    const [rows, setRows] = useState<ExceptionRow[]>([]);
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<ExceptionRow | null>(null);
    const [override, setOverride] = useState(false);
    const [busy, setBusy] = useState(false);
    const [canOverride, setCanOverride] = useState(false);
    const load = useCallback(async (silent = false) => {
        if (!silent)
            setLoading(true);
        try {
            const [r, p] = await Promise.all([apiFetch("/exceptions"), apiFetch("/auth/me")]);
            if (!r.ok)
                throw new Error(r.status === 401 ? "Sign in to open the exception queue." : "Could not load exceptions.");
            const data = await r.json();
            setRows(data);
            if (p.ok) {
                const profile: Profile = await p.json();
                setCanOverride(["OWNER", "FINANCE"].includes(profile.role));
            }
        }
        catch (e) {
            if (silent)
                throw e;
            setMessage(e instanceof Error ? e.message : "Could not load exceptions.");
        }
        finally {
            if (!silent)
                setLoading(false);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    async function resolve(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!selected)
            return;
        const form = new FormData(event.currentTarget);
        setBusy(true);
        try {
            const response = await apiFetch(`/exceptions/${selected.id}/resolve`, { method: "POST", body: JSON.stringify({ override, resolution_note: String(form.get("note") || ""), override_reason: String(form.get("reason") || "") }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error?.message || "Could not resolve exception.");
            setSelected(null);
            setOverride(false);
            setMessage(`Exception marked ${data.status.toLowerCase()}.`);
            await load();
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not resolve exception.");
        }
        finally {
            setBusy(false);
        }
    }
    const pagination = useListPagination(rows, "");
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiBox className="mt-6 flex items-end justify-between"><UiBox><UiH1 className="text-2xl font-bold">Exception queue</UiH1><UiText className="mt-1 text-sm text-slate-500">Resolve discrepancies before invoices are submitted for approval.</UiText></UiBox><UiButton onClick={() => void load()} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Refresh</UiButton></UiBox>{message && <UiAlert role="status" className="mt-4 rounded-lg bg-amber-50 px-4 py-3 text-xs text-amber-800">{message}</UiAlert>}<LiveData onRefresh={() => load(true)} interval={15000} paused={Boolean(selected || busy || loading)}/><UiSection className="mt-6 overflow-hidden rounded-xl border border-line bg-white shadow-card">{loading ? <ContentSkeleton variant="table" label="Loading queue" /> : rows.length === 0 ? <UiBox className="p-12 text-center"><ShieldAlert className="mx-auto text-slate-300"/><UiText className="mt-3 text-sm font-semibold">No unresolved exceptions</UiText><UiText className="mt-1 text-xs text-slate-500">Matching issues will be listed here when they need attention.</UiText></UiBox> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[800px] text-left"><UiTableHead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><UiTableRow>{["Invoice", "Exception", "Severity", "Status", "Evidence", "Action"].map(x => <UiTh key={x} className="px-4 py-3">{x}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{pagination.rows.map(x => <UiTableRow key={x.id} className="border-t border-line text-xs"><UiTd className="px-4 py-4 font-semibold">{x.invoice_number || x.invoice_id.slice(0, 8)}</UiTd><UiTd className="px-4 py-4">{x.code.replaceAll("_", " ")}</UiTd><UiTd className="px-4 py-4"><UiSpan className="rounded-full bg-rose-50 px-2.5 py-1 text-[10px] font-semibold text-rose-700">{x.severity}</UiSpan></UiTd><UiTd className="px-4 py-4 text-slate-500">{x.status}</UiTd><UiTd className="max-w-[260px] truncate px-4 py-4 text-slate-500" title={JSON.stringify(x.details)}>{JSON.stringify(x.details)}</UiTd><UiTd className="px-4 py-4">{["OPEN", "ASSIGNED"].includes(x.status) ? <UiButton onClick={() => setSelected(x)} className="font-semibold text-forest">Resolve</UiButton> : <UiSpan className="text-slate-400">Closed</UiSpan>}</UiTd></UiTableRow>)}</UiTableBody></UiTable></UiBox>}{pagination.controls}</UiSection>
    {selected && <UiModal className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4" onClose={() => { setSelected(null); setOverride(false); }}><UiForm onSubmit={resolve} className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl"><UiH2 className="text-lg font-bold">Resolve {selected.code.replaceAll("_", " ")}</UiH2><UiText className="mt-1 text-xs text-slate-500">Invoice {selected.invoice_number || selected.invoice_id.slice(0, 8)}</UiText><UiLabel className="mt-5 block text-xs font-semibold">Resolution note<UiTextarea name="note" rows={3} className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-sm font-normal" placeholder="Describe how the discrepancy was resolved"/></UiLabel>{canOverride && <UiLabel className="mt-4 flex items-center gap-2 text-xs font-semibold"><UiInput type="checkbox" checked={override} onChange={e => setOverride(e.target.checked)}/>Override this blocking exception</UiLabel>}{override && <UiLabel className="mt-4 block text-xs font-semibold">Override reason<UiTextarea name="reason" rows={2} required className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-sm font-normal" placeholder="Reason required for audit"/></UiLabel>}<UiBox className="mt-6 flex justify-end gap-2"><UiButton type="button" onClick={() => { setSelected(null); setOverride(false); }} className="rounded-lg border border-line px-4 py-2 text-xs font-semibold">Cancel</UiButton><UiButton disabled={busy} className="inline-flex items-center gap-2 rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white">{busy && <UiSpinner className="animate-spin" size={14}/>}Confirm resolution</UiButton></UiBox></UiForm></UiModal>}</UiMain>;
}
