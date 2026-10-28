"use client";

import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiBox, UiButton, UiH1, UiMain, UiSection, UiSpan, UiSpinner, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { ListPagination } from "@/components/list-pagination";
import { AppLink as Link } from "@/components/product-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { ArrowDownToLine } from "lucide-react";
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
export default function ExportsPage() {
    const [rows, setRows] = useState<Invoice[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [page, setPage] = useState(0);
    const [pageSize, setPageSize] = useState(25);
    const [total, setTotal] = useState(0);
    const sequence = useRef(0);
    const load = useCallback(async () => {
        const request = ++sequence.current;
        setLoading(true);
        try {
            const response = await apiFetch(`/invoices/?status=PAYMENT_READY&page=${page + 1}&page_size=${pageSize}`);
            if (request !== sequence.current)
                return;
            if (response.status === 404 && page > 0) {
                setPage(0);
                return;
            }
            if (!response.ok)
                throw new Error(response.status === 401 ? "Sign in to view payment-ready invoices." : "Could not load export queue.");
            const data = await response.json();
            if (request !== sequence.current)
                return;
            setTotal(data.count || 0);
            setRows(data.results || []);
        }
        catch (e) {
            if (request !== sequence.current)
                return;
            setMessage(e instanceof Error ? e.message : "Could not load export queue.");
        }
        finally {
            if (request === sequence.current)
                setLoading(false);
        }
    }, [page, pageSize]);
    useEffect(() => { void load(); }, [load]);
    async function exportReady() {
        setBusy(true);
        setMessage("");
        try {
            const r = await apiFetch("/exports/tally-csv", { method: "POST", body: JSON.stringify({ invoice_ids: rows.map(row => row.id) }) });
            if (!r.ok) {
                const data = await r.json();
                throw new Error(data.error?.message || "Tally export failed.");
            }
            const blob = await r.blob();
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = "kriyopay-tally-export.csv";
            anchor.click();
            URL.revokeObjectURL(url);
            setMessage("Tally CSV created and downloaded. Exported invoices are recorded in the audit log.");
            await load();
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Tally export failed.");
        }
        finally {
            setBusy(false);
        }
    }
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiBox className="mt-6 flex flex-wrap items-end justify-between gap-4"><UiBox><UiH1 className="text-2xl font-bold">Tally export</UiH1><UiText className="mt-1 text-sm text-slate-500">Create a balanced purchase voucher CSV from approved, payment-ready invoices.</UiText></UiBox><UiButton disabled={!rows.length || busy || loading} onClick={() => void exportReady()} className="inline-flex items-center gap-2 rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-50">{busy ? <UiSpinner size={15} className="animate-spin"/> : <ArrowDownToLine size={15}/>}Export this page ({rows.length} invoices)</UiButton></UiBox><Link href="/exports/settings" className="mt-3 inline-flex rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-forest">Configure ledger mappings</Link>{message && <WorkflowFeedback message={message} onRefresh={()=>load()} />}<UiSection className="mt-6 overflow-hidden rounded-xl border border-line bg-white shadow-card">{loading ? <ContentSkeleton variant="table" label="Loading payment-ready invoices" /> : rows.length === 0 ? <EmptyState description="No payment-ready invoices to export. Approved invoices will appear here." onAction={()=>void load()} actionLabel="Refresh data" /> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[680px] text-left"><UiTableHead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><UiTableRow>{["Supplier", "Invoice number", "Invoice date", "Amount", "Status"].map(x => <UiTh key={x} className="px-5 py-3">{x}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{rows.map(row => <UiTableRow key={row.id} className="border-t border-line text-xs"><UiTd className="px-5 py-4 font-semibold">{row.vendor_name || row.supplier_name || "Supplier"}</UiTd><UiTd className="px-5 py-4 text-slate-500">{row.invoice_number || "—"}</UiTd><UiTd className="px-5 py-4 text-slate-500">{row.invoice_date || "—"}</UiTd><UiTd className="px-5 py-4 font-semibold">{money(row.invoice_total)}</UiTd><UiTd className="px-5 py-4"><UiSpan className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold text-emerald-700">Payment ready</UiSpan></UiTd></UiTableRow>)}</UiTableBody></UiTable></UiBox>}<ListPagination count={total} page={page} pageSize={pageSize} disabled={loading || busy} label="Export queue pagination" onPageChange={setPage} onPageSizeChange={size => { setPageSize(size); setPage(0); }}/></UiSection></UiMain>;
}
