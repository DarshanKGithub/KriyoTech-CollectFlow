"use client";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiArticle, UiBox, UiButton, UiH1, UiH2, UiMain, UiSpan, UiText } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { AppLink as Link } from "@/components/product-ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowUpRight, Clock3, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
type QueueItem = {
    id: string;
    category: string;
    title: string;
    detail: string;
    href: string;
    due?: string | null;
    priority: number;
};
type RecordRow = Record<string, unknown>;
const rows = (value: unknown): RecordRow[] => Array.isArray(value) ? value as RecordRow[] : value && typeof value === "object" && Array.isArray((value as {
    results?: unknown;
}).results) ? (value as {
    results: RecordRow[];
}).results : [];
const display = (value: unknown) => value == null || value === "" ? "" : String(value);
export default function AttentionPage() {
    const [items, setItems] = useState<QueueItem[]>([]);
    const [filter, setFilter] = useState("All");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const load = useCallback(async (silent = false) => {
        if (!silent)
            setLoading(true);
        setError("");
        const results = await Promise.allSettled([
            apiFetch("/invoices/"), apiFetch("/approvals/pending"), apiFetch("/exceptions"),
            apiFetch("/fleet/follow-ups"), apiFetch("/fleet/driver-salaries"),
        ]);
        try {
            if (results.every(result => result.status === "rejected" || !result.value.ok))
                throw new Error("All attention sources are unavailable.");
            if (results.some(result => result.status === "rejected" || !result.value.ok))
                setError("Some sources could not load, so this queue may be incomplete.");
            const payloads = await Promise.all(results.map(async (result) => {
                if (result.status === "rejected")
                    return [];
                if (!result.value.ok)
                    return [];
                return rows(await result.value.json());
            }));
            const [invoices, approvals, exceptions, followUps, salaries] = payloads;
            const next: QueueItem[] = [];
            const localNow = new Date();
            localNow.setMinutes(localNow.getMinutes() - localNow.getTimezoneOffset());
            const localDate = localNow.toISOString().slice(0, 10);
            for (const invoice of invoices) {
                const id = display(invoice.id);
                if (!id)
                    continue;
                const number = display(invoice.invoice_number) || id.slice(0, 8);
                const vendor = display(invoice.vendor_name || invoice.supplier_name) || "Supplier to review";
                const status = display(invoice.status);
                const base = { id, title: `${vendor} · ${number}`, detail: `Invoice ${status.replaceAll("_", " ").toLowerCase()}`, href: "/invoices", due: display(invoice.due_date) || null };
                const automation=invoice.automation && typeof invoice.automation==="object" ? invoice.automation as {status?:string;message?:string} : {};
                if (["QUEUED","RUNNING","RETRY"].includes(automation.status||"")) continue;
                if (["NEEDS_ATTENTION","FAILED"].includes(automation.status||"") && !["PAYMENT_READY","EXPORTED","APPROVAL_PENDING"].includes(status))
                    next.push({...base,category:"Invoice review",detail:automation.message||"Automatic processing needs a decision.",priority:1});
                else if (["UPLOADED", "EXTRACTING", "EXTRACTION_FAILED"].includes(status))
                    next.push({ ...base, category: status === "EXTRACTION_FAILED" ? "Failed extraction" : "Invoice processing", detail: status === "EXTRACTION_FAILED" ? "Extraction failed. Retry or review the fields." : status === "EXTRACTING" ? "Invoice is being extracted." : "Invoice is waiting for extraction.", href: "/invoices", priority: status === "EXTRACTION_FAILED" ? 1 : 3 });
                else if (["REVIEW_REQUIRED", "EXCEPTION"].includes(status))
                    next.push({ ...base, category: status === "EXCEPTION" ? "Invoice exception" : "Invoice review", detail: status === "EXCEPTION" ? "Resolve invoice issues before matching or approval." : "Check the extracted fields and line items.", priority: status === "EXCEPTION" ? 1 : 2 });
                const dueDate = display(invoice.due_date);
                if (dueDate && dueDate < localDate && display(invoice.payment_status) !== "PAID" && display(invoice.payment_status) !== "CANCELLED")
                    next.push({ ...base, id: `${id}-payment`, category: "Overdue payment", detail: `Payment was due ${dueDate}.`, href: "/payments", due: dueDate, priority: 1 });
            }
            for (const invoice of approvals) {
                const id = display(invoice.id);
                if (id)
                    next.push({ id: `approval-${id}`, category: "Pending approval", title: `${display(invoice.vendor_name || invoice.supplier_name) || "Invoice"} · ${display(invoice.invoice_number) || id.slice(0, 8)}`, detail: "This invoice is waiting for your approval.", href: "/approvals", priority: 2 });
            }
            for (const exception of exceptions) {
                const id = display(exception.id);
                if (id)
                    next.push({ id: `exception-${id}`, category: "Invoice exception", title: `${display(exception.invoice_number) || "Invoice"} · ${display(exception.code).replaceAll("_", " ")}`, detail: `Severity: ${display(exception.severity)}. Review the supporting evidence.`, href: "/exceptions", priority: 1 });
            }
            for (const followUp of followUps) {
                if (!["OPEN", "IN_PROGRESS"].includes(display(followUp.status)))
                    continue;
                const id = display(followUp.id);
                if (id)
                    next.push({ id: `fleet-${id}`, category: "Fleet follow-up", title: display(followUp.description) || "Fleet follow-up", detail: display(followUp.status).replaceAll("_", " "), href: "/fleet/follow-ups", due: display(followUp.due_at) || null, priority: 1 });
            }
            for (const salary of salaries) {
                const remaining = Number(salary.remaining_amount || 0);
                if (remaining <= 0)
                    continue;
                const id = display(salary.id);
                if (id)
                    next.push({ id: `salary-${id}`, category: "Driver salary balance", title: `${display((salary.driver as RecordRow | undefined)?.name) || "Driver"} · ${display(salary.period_start).slice(0, 7)}`, detail: `₹${remaining.toLocaleString("en-IN", { minimumFractionDigits: 2 })} remains to be paid.`, href: "/fleet/driver-salaries", priority: 2 });
            }
            next.sort((a, b) => a.priority - b.priority || (a.due || "9999").localeCompare(b.due || "9999"));
            if (silent && results.some(result => result.status === "rejected" || !result.value.ok))
                throw new Error("Some attention sources could not refresh.");
            setItems(next);
        }
        catch (error) {
            if (silent)
                throw error;
            setError("Could not load the attention queue. Refresh to try again.");
        }
        finally {
            if (!silent)
                setLoading(false);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    const categories = useMemo(() => ["All", ...new Set(items.map(item => item.category))], [items]);
    const visible = filter === "All" ? items : items.filter(item => item.category === filter);
    const pagination = useListPagination(visible, filter);
    return <UiMain className="w-full min-w-0 min-h-screen px-4 py-7 sm:px-6 lg:px-8">
    <UiBox className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-xs font-semibold uppercase tracking-widest text-forest">Workspace queue</UiText><UiH1 className="mt-1 text-2xl font-bold">Needs attention</UiH1><UiText className="mt-1 text-sm text-slate-500">Invoices, approvals, payments, and fleet tasks that need a next step.</UiText></UiBox><UiButton onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs font-semibold"><RefreshCw size={14} className={loading ? "animate-spin" : ""}/>Refresh</UiButton></UiBox>
    <LiveData onRefresh={() => load(true)} paused={loading} interval={30000}/>
    {error && <UiAlert role="alert" className="mt-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</UiAlert>}
    <UiBox className="mt-5 flex gap-2 overflow-x-auto pb-1">{categories.map(category => <UiButton key={category} onClick={() => setFilter(category)} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${filter === category ? "bg-forest text-white" : "bg-white text-slate-600 ring-1 ring-line"}`}>{category}{category === "All" ? ` · ${items.length}` : ` · ${items.filter(item => item.category === category).length}`}</UiButton>)}</UiBox>
    {loading ? <ContentSkeleton variant="cards" label="Loading attention items" /> : visible.length === 0 ? <UiBox className="mt-5 rounded-xl border border-line bg-white p-12 text-center"><AlertCircle className="mx-auto text-emerald-600" size={22}/><UiH2 className="mt-3 text-sm font-bold">You’re all caught up</UiH2><UiText className="mt-1 text-xs text-slate-500">New work will appear here when it needs action.</UiText></UiBox> : <UiBox className="mt-5 space-y-3">{pagination.rows.map(item => <UiArticle key={item.id} className="flex flex-col gap-3 rounded-xl border border-line bg-white p-4 shadow-sm sm:flex-row sm:items-center"><UiSpan className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-amber-50 text-amber-700"><AlertCircle size={18}/></UiSpan><UiBox className="min-w-0 flex-1"><UiBox className="flex flex-wrap items-center gap-2"><UiH2 className="truncate text-sm font-semibold">{item.title}</UiH2><UiSpan className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600">{item.category}</UiSpan></UiBox><UiText className="mt-1 text-xs text-slate-500">{item.detail}</UiText>{item.due && <UiText className="mt-2 inline-flex items-center gap-1 text-[10px] text-rose-700"><Clock3 size={12}/>{item.due}</UiText>}</UiBox><Link href={item.href} className="inline-flex items-center justify-center gap-1 rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Open <ArrowUpRight size={13}/></Link></UiArticle>)}</UiBox>}
    {!loading && pagination.controls}
  </UiMain>;
}
