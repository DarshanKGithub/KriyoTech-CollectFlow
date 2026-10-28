"use client";
import { ContentSkeleton } from "@/components/content-skeleton";
import { requestConfirmation } from "@/components/product-dialogs";
import { UiAlert, UiBox, UiButton, UiH1, UiMain, UiSection, UiSpinner, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { AppLink as Link } from "@/components/product-ui";
import { Fragment, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Check, X } from "lucide-react";
type Invoice = {
    id: string;
    invoice_number: string;
    supplier_name?: string;
    vendor_name?: string;
    invoice_date?: string;
    invoice_total: string;
    status: string;
};
const money = (value: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
export default function ApprovalsPage() {
    const [rows, setRows] = useState<Invoice[]>([]);
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState("");
    const [history, setHistory] = useState<Record<string, {
        steps: Record<string, unknown>[];
        decisions: Record<string, unknown>[];
    }>>({});
    const load = useCallback(async (silent = false) => {
        if (!silent)
            setLoading(true);
        try {
            const r = await apiFetch("/approvals/pending");
            if (!r.ok)
                throw new Error(r.status === 401 ? "Sign in to view approvals." : "Could not load approval queue.");
            setRows(await r.json());
        }
        catch (e) {
            if (silent)
                throw e;
            setMessage(e instanceof Error ? e.message : "Could not load approvals.");
        }
        finally {
            if (!silent)
                setLoading(false);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    async function decide(invoice: Invoice, decision: "approve" | "reject") {
        if(!await requestConfirmation(`Record your ${decision === "approve" ? "approval" : "rejection"} for invoice ${invoice.invoice_number || invoice.id}?`))return;
        setBusy(invoice.id);
        setMessage("");
        try {
            const r = await apiFetch(`/invoices/${invoice.id}/${decision}/`, { method: "POST", body: JSON.stringify({}) });
            const data = await r.json();
            if (!r.ok)
                throw new Error(data.error?.message || `Could not ${decision} invoice.`);
            setMessage(`${invoice.invoice_number || "Invoice"} ${decision === "approve" ? "approved and payment-ready" : "rejected"}.`);
            await load();
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not record decision.");
        }
        finally {
            setBusy("");
        }
    }
    const pagination = useListPagination(rows, "");
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiBox className="mt-6"><UiH1 className="text-2xl font-bold">Approval queue</UiH1><UiText className="mt-1 text-sm text-slate-500">Only steps assigned to your user, role, or active delegation appear here.</UiText></UiBox>{message && <UiAlert role="status" className="mt-4 rounded-lg bg-amber-50 px-4 py-3 text-xs text-amber-800">{message}</UiAlert>}<LiveData onRefresh={() => load(true)} interval={15000} paused={Boolean(busy || loading)}/><UiSection className="mt-6 overflow-hidden rounded-xl border border-line bg-white shadow-card">{loading ? <ContentSkeleton variant="table" label="Loading approvals" /> : rows.length === 0 ? <UiBox className="p-12 text-center"><UiText className="text-sm font-semibold">No approval steps assigned to you</UiText><UiText className="mt-1 text-xs text-slate-500">Invoices appear when your approval step is current.</UiText></UiBox> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[860px] text-left"><UiTableHead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><UiTableRow>{["Supplier", "Invoice number", "Invoice date", "Amount", "Decision", "History"].map(x => <UiTh key={x} className="px-5 py-3">{x}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{pagination.rows.map(row => <Fragment key={row.id}><UiTableRow className="border-t border-line text-xs"><UiTd className="px-5 py-4 font-semibold">{row.vendor_name || row.supplier_name || "Supplier to review"}</UiTd><UiTd className="px-5 py-4 text-slate-500">{row.invoice_number || "—"}</UiTd><UiTd className="px-5 py-4 text-slate-500">{row.invoice_date || "—"}</UiTd><UiTd className="px-5 py-4 font-semibold">{money(row.invoice_total)}</UiTd><UiTd className="px-5 py-4"><UiBox className="flex gap-2"><UiButton disabled={busy === row.id} onClick={() => void decide(row, "approve")} className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-3 py-2 font-semibold text-emerald-800 disabled:opacity-50"><Check size={13}/>Approve</UiButton><UiButton disabled={busy === row.id} onClick={() => void decide(row, "reject")} className="inline-flex items-center gap-1 rounded-lg bg-rose-50 px-3 py-2 font-semibold text-rose-800 disabled:opacity-50"><X size={13}/>Reject</UiButton>{busy === row.id && <UiSpinner className="animate-spin text-slate-500" size={15}/>}</UiBox></UiTd><UiTd className="px-5 py-4"><UiButton onClick={async () => {
                    if (history[row.id]) {
                        setHistory(v => { const next = { ...v }; delete next[row.id]; return next; });
                        return;
                    }
                    const r = await apiFetch(`/invoices/${row.id}/approval-history`);
                    if (r.ok) {
                        const d = await r.json();
                        setHistory(v => ({ ...v, [row.id]: d }));
                    }
                }} className="font-semibold text-forest">{history[row.id] ? "Hide" : "View history"}</UiButton></UiTd></UiTableRow>{history[row.id] && <UiTableRow><UiTd colSpan={6} className="bg-slate-50 px-5 py-4"><pre className="whitespace-pre-wrap text-[10px]">{JSON.stringify(history[row.id], null, 2)}</pre></UiTd></UiTableRow>}</Fragment>)}</UiTableBody></UiTable></UiBox>}{pagination.controls}</UiSection></UiMain>;
}
