"use client";
import { applyFieldErrors } from "@/components/form-validation";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { ContentSkeleton } from "@/components/content-skeleton";
import { InvoiceUploadDialog } from "@/components/invoice-upload-dialog";
import { requestConfirmation, showNotice } from "@/components/product-dialogs";
import { InvoiceGrid } from "@/components/invoice-grid";
import { InvoiceProgress } from "@/components/workflow-progress";
import { UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiIconButton, UiInput, UiLabel, UiMain, UiReviewDrawer, UiSelect, UiSection, UiSpan, UiSpinner, UiText } from "@/components/product-ui";
import { ListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Check, FilePlus2, RefreshCw, Upload, X, ExternalLink } from "lucide-react";
type InvoiceLine = {
    description: string;
    item_code?: string;
    hsn_sac?: string;
    quantity: string | number;
    uom?: string;
    rate: string | number;
    taxable_value: string | number;
    gst_rate: string | number;
    gst_amount: string | number;
    tds_amount: string | number;
};
type Invoice = {
    id: string;
    invoice_number: string;
    supplier_name?: string;
    vendor_name?: string;
    vendor?: string | null;
    invoice_date?: string;
    invoice_total: string;
    status: string;
    exception_codes?: string[];
    lines?: InvoiceLine[];
    document?: string | null;
    extraction_confidence?: Record<string, number>;
    extraction_status?: string;
    extraction_error?: string;
    automation?: {status?:string;message?:string;version?:number};
    financial_locked_at?: string | null;
    payment_status?: string;
};
const pretty = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
const canEdit = (row: Invoice) => !row.financial_locked_at && !["APPROVED", "PAYMENT_READY", "EXPORTED", "APPROVAL_PENDING", "EXTRACTING"].includes(row.status) && (!row.payment_status || row.payment_status === "UNPAID");
const money = (value: string) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
export default function InvoiceQueue() {
    const [uploadOpen, setUploadOpen] = useState(false);
    const [rows, setRows] = useState<Invoice[]>([]);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState("");
    const [editing, setEditing] = useState<Invoice | null>(null);
    const [suppliers,setSuppliers]=useState<{id:string;name:string}[]>([]);
    const [editingLines, setEditingLines] = useState<InvoiceLine[]>([]);
    const [workflowEnabled,setWorkflowEnabled]=useState(false);
    const [extractionEnabled, setExtractionEnabled] = useState(false);
    const [page, setPage] = useState(0);
    const [pageSize, setPageSize] = useState(25);
    const [total, setTotal] = useState(0);
    const [searchInput, setSearchInput] = useState("");
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("");
    const [ordering, setOrdering] = useState("-created_at");
    useEffect(()=>{const timer=setTimeout(()=>{setPage(0);setSearch(searchInput.trim());},300);return()=>clearTimeout(timer);},[searchInput]);
    const requestSequence = useRef(0);
    const load = useCallback(async (silent = false) => {
        const sequence = ++requestSequence.current;
        if (!silent)
            setLoading(true);
        try {
            const [response, settingsResponse] = await Promise.all([apiFetch(`/invoices/?page=${page + 1}&page_size=${pageSize}&search=${encodeURIComponent(search)}&ordering=${encodeURIComponent(ordering)}${statusFilter ? `&status=${encodeURIComponent(statusFilter)}` : ""}`), apiFetch("/settings")]);
            if (sequence !== requestSequence.current)
                return;
            if (response.status === 404 && page > 0) {
                setPage(0);
                return;
            }
            if (!response.ok)
                throw new Error(response.status === 401 ? "Sign in and choose your workspace to see invoices." : "Could not load invoices.");
            const [data, settings] = await Promise.all([response.json(), settingsResponse.ok ? settingsResponse.json() : Promise.resolve({})]);
            if (sequence !== requestSequence.current)
                return;
            setTotal(data.count || 0);
            setRows(data.results || []);
            setExtractionEnabled(Boolean(settings.automatic_extraction_enabled));
            setWorkflowEnabled(settings.automatic_invoice_workflow_enabled === true);
        }
        catch (error) {
            if (sequence !== requestSequence.current)
                return;
            if (silent)
                throw error;
            setMessage(error instanceof Error ? error.message : "Could not load invoices.");
        }
        finally {
            if (sequence === requestSequence.current && !silent)
                setLoading(false);
        }
    }, [page, pageSize, search, statusFilter, ordering]);
    useEffect(() => { void load(); }, [load]);
    async function upload(file: File): Promise<boolean> {
        setBusy("upload");
        setMessage("");
        const form = new FormData();
        form.append("file", file);
        try {
            const response = await apiFetch("/invoices/", { method: "POST", body: form });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error?.message || "Upload failed");
            showNotice(extractionEnabled ? "Invoice uploaded. Extraction is queued." : "Invoice uploaded. Review its fields manually.", "success");
            setMessage(extractionEnabled ? "Invoice uploaded. Automatic field extraction has been queued; you can review the result when it finishes." : "Invoice uploaded. Automatic extraction is disabled; review the fields manually.");
            if (page === 0)
                await load();
            else
                setPage(0);
            return true;
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Upload failed");
            return false;
        }
        finally {
            setBusy("");
        }
    }
    async function action(invoice: Invoice, name: string, method = "POST") {
        if (["approve", "reject"].includes(name) && !await requestConfirmation(`Record your ${name === "approve" ? "approval" : "rejection"} for invoice ${invoice.invoice_number || invoice.id}?`))
            return;
        setBusy(invoice.id);
        setMessage("");
        try {
            const response = await apiFetch(`/invoices/${invoice.id}/${name}/`, { method, body: method === "POST" ? JSON.stringify({}) : undefined });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error?.message || (typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.join(" ") : "This action could not be completed."));
            }
            if (name === "export") {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const anchor = document.createElement("a");
                anchor.href = url;
                anchor.download = `kriyopay-${invoice.invoice_number || invoice.id}.csv`;
                anchor.click();
                URL.revokeObjectURL(url);
                showNotice("Tally CSV downloaded.", "success");
                setMessage("Tally CSV downloaded.");
            }
            else {
                showNotice(name === "extract" ? "Extraction request accepted. Watch the invoice status for its result." : "Invoice action completed.", "success");
                setMessage(`Invoice ${invoice.invoice_number || "record"}: ${pretty(name.replaceAll("-", "_"))} completed.`);
                await load();
            }
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Action failed.");
        }
        finally {
            setBusy("");
        }
    }
    async function openSource(invoice: Invoice) {
        const tab = window.open("about:blank", "_blank");
        setBusy(invoice.id);
        try {
            const response = await apiFetch(`/invoices/${invoice.id}/source/`);
            if (!response.ok)
                throw new Error("Source document could not be opened.");
            const url = URL.createObjectURL(await response.blob());
            if (tab)
                tab.location.href = url;
            else {
                const anchor = document.createElement("a");
                anchor.href = url;
                anchor.target = "_blank";
                anchor.rel = "noopener";
                anchor.click();
            }
            window.setTimeout(() => URL.revokeObjectURL(url), 60000);
        }
        catch (error) {
            tab?.close();
            setMessage(error instanceof Error ? error.message : "Source document could not be opened.");
        }
        finally {
            setBusy("");
        }
    }
    useEffect(()=>{
        if(!editing)return;
        let active=true;
        apiFetch("/vendors").then(async response=>{if(response.ok){const data=await response.json();if(active)setSuppliers(Array.isArray(data)?data:data.results||[]);}}).catch(()=>{});
        return()=>{active=false;};
    },[editing]);
    async function saveReview(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!editing)
            return;
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        setBusy(editing.id);
        try {
            const lines = editingLines.filter(line => line.description.trim()).map(line => ({ ...line, quantity: Number(line.quantity), rate: Number(line.rate), taxable_value: Number(line.taxable_value), gst_rate: Number(line.gst_rate), gst_amount: Number(line.gst_amount), tds_amount: Number(line.tds_amount) }));
            const response = await apiFetch(`/invoices/${editing.id}/`, { method: "PATCH", body: JSON.stringify({ vendor: form.get("vendor") || null, supplier_name: form.get("supplier_name"), invoice_number: form.get("invoice_number"), invoice_date: form.get("invoice_date") || null, invoice_total: form.get("invoice_total"), lines }) });
            const data = await response.json();
            if (!response.ok) {
                applyFieldErrors(formElement, data);
                throw new Error(data.error?.message || data.detail || "Could not save invoice fields.");
            }
            setEditing(null);
            setMessage("Invoice fields saved. Automatic processing will validate, match and route approval when enabled. Any issue will appear beside the invoice.");
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not save changes.");
        }
        finally {
            setBusy("");
        }
    }
    function setLine(index: number, key: keyof InvoiceLine, value: string) { setEditingLines(lines => lines.map((line, i) => i === index ? { ...line, [key]: value } : line)); }
    function addLine() { setEditingLines(lines => [...lines, { description: "", item_code: "", hsn_sac: "", quantity: 1, uom: "", rate: 0, taxable_value: 0, gst_rate: 0, gst_amount: 0, tds_amount: 0 }]); }
    function actionsFor(invoice: Invoice) {
        if (["QUEUED","RUNNING","RETRY"].includes(invoice.automation?.status||"")) return [];
        const actions: {
            label: string;
            key: string;
            className?: string;
        }[] = [];
        if (canEdit(invoice) && ["UPLOADED", "EXTRACTION_FAILED", "REVIEW_REQUIRED", "EXCEPTION"].includes(invoice.status)) {
            if (extractionEnabled && invoice.document)
                actions.push({ label: invoice.status === "EXTRACTION_FAILED" ? "Retry extraction" : "Extract fields", key: "extract", className: "text-blue-700" });
            actions.push({ label: "Review", key: "review" }, { label: "Run match", key: "confirm-extraction", className: "text-forest" });
        }
        if (invoice.status === "MATCHED" && !invoice.financial_locked_at) {
            actions.push({ label: "Review", key: "review" });
            actions.push({ label: "Submit approval", key: "submit-for-approval", className: "text-forest" });
        }
        if (invoice.status === "APPROVAL_PENDING")
            actions.push({ label: "Approve", key: "approve", className: "text-emerald-700" }, { label: "Reject", key: "reject", className: "text-rose-700" });
        if (invoice.status === "PAYMENT_READY")
            actions.push({ label: "Export CSV", key: "export", className: "text-forest" });
        if (workflowEnabled && canEdit(invoice) && ["REVIEW_REQUIRED","EXCEPTION","MATCHED"].includes(invoice.status)) actions.push({label:"Resume automation",key:"resume-automation",className:"text-forest"});
        return actions;
    }
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiBox className="mt-6 flex flex-wrap items-end justify-between gap-4"><UiBox><UiH1 className="text-2xl font-bold">Invoices</UiH1><UiText className="mt-1 text-sm text-slate-500">Upload once. KriyoPay checks suppliers, validates totals, matches documents and routes approvals. Review only the items that need attention.</UiText></UiBox><UiButton type="button" onClick={() => setUploadOpen(true)} className="bg-forest text-white"><FilePlus2 size={15}/>Upload invoice</UiButton></UiBox>{message && <WorkflowFeedback message={message} onRefresh={()=>load()} />}<LiveData onRefresh={() => load(true)} interval={30000} paused={Boolean(uploadOpen || editing || busy || loading)}/><UiBox className="mt-5 flex flex-wrap items-end gap-3"><UiLabel className="min-w-0 flex-1 text-xs">Search invoices<UiInput className="mt-1 w-full" value={searchInput} onChange={event=>setSearchInput(event.target.value)} placeholder="Invoice number, supplier or PO" aria-label="Search invoices" maxLength={200}/></UiLabel><UiLabel className="text-xs">Status<UiSelect aria-label="Filter invoice status" className="mt-1 block" value={statusFilter} onChange={event=>{setPage(0);setStatusFilter(event.target.value);}}><option value="">All statuses</option>{["UPLOADED","EXTRACTING","EXTRACTION_FAILED","REVIEW_REQUIRED","MATCHED","EXCEPTION","APPROVAL_PENDING","APPROVED","REJECTED","PAYMENT_READY","EXPORTED"].map(status=><option key={status} value={status}>{status.replaceAll("_"," ").toLowerCase()}</option>)}</UiSelect></UiLabel>{(searchInput || statusFilter)&&<UiButton type="button" onClick={()=>{setSearchInput("");setStatusFilter("");setPage(0);}}>Clear filters</UiButton>}</UiBox><UiSection className="mt-6 overflow-hidden rounded-xl border border-line bg-white shadow-card"><UiBox className="flex items-center justify-between border-b border-line px-5 py-4 text-xs font-semibold">All invoices <UiSpan className="ml-1 text-slate-400">{total}</UiSpan><UiIconButton onClick={() => void load()} aria-label="Refresh invoices" className="ml-auto text-slate-500 hover:text-forest"><RefreshCw size={14}/></UiIconButton></UiBox>{loading ? <ContentSkeleton variant="table" label="Loading invoices" /> : rows.length === 0 ? <UiBox className="p-12 text-center"><Upload className="mx-auto text-slate-300"/><EmptyState kind={search || statusFilter ? "search" : "empty"} description={search || statusFilter ? "Try another search or clear the filters." : "Upload a supplier invoice to start extraction and review."} onAction={()=>{if(search || statusFilter){setSearchInput("");setStatusFilter("");setPage(0);}else setUploadOpen(true);}} actionLabel={search || statusFilter ? "Clear filters" : "Upload invoice"} /><UiText className="mt-1 text-xs text-slate-500">Upload a PDF or image to create the first invoice record.</UiText></UiBox> : <UiBox className="overflow-x-auto"><InvoiceGrid onOrderingChange={setOrdering} rows={rows} total={total} page={page} pageSize={pageSize} busy={busy} actions={invoice => <>{invoice.document && <UiButton type="button" disabled={busy === invoice.id} onClick={() => void openSource(invoice)}><ExternalLink size={12}/>Source</UiButton>}{actionsFor(invoice).map(item => <UiButton key={item.key} type="button" disabled={busy === invoice.id} onClick={() => {
                        if (item.key === "review") {
                            setEditing(invoice);
                            setEditingLines(invoice.lines || []);
                        }
                        else
                            void action(invoice, item.key);
                    }} className={item.className}>{item.label}</UiButton>)}</>}/></UiBox>}<ListPagination count={total} page={page} pageSize={pageSize} disabled={loading || Boolean(busy)} label="Invoice pagination" onPageChange={setPage} onPageSizeChange={size => { setPageSize(size); setPage(0); }}/></UiSection>
  {editing && <UiReviewDrawer className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4" onClose={() => setEditing(null)}><UiForm onSubmit={saveReview} className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl"><UiBox className="flex items-start justify-between"><UiBox><UiH2 className="text-lg font-bold">Review invoice fields</UiH2><UiText className="mt-1 text-xs text-slate-500">Check the extracted header and line items against the source. AI never approves or pays invoices.</UiText></UiBox><UiIconButton type="button" onClick={() => setEditing(null)} aria-label="Close" className="text-slate-400"><X size={18}/></UiIconButton></UiBox><InvoiceProgress status={editing.status}/><WorkflowFeedback message={message} />{Object.keys(editing.extraction_confidence || {}).length > 0 && <UiBox className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3"><UiText className="text-xs font-semibold text-amber-900">Model-reported confidence (uncalibrated)</UiText><UiBox className="mt-2 flex flex-wrap gap-2">{Object.entries(editing.extraction_confidence || {}).map(([field, score]) => <UiSpan key={field} className={`rounded px-2 py-1 text-[11px] ${Number(score) < 0.9 ? "bg-rose-100 font-semibold text-rose-800" : "bg-white text-slate-700"}`}>{pretty(field)} · {Math.round(Number(score) * 100)}%{Number(score) < 0.9 ? " · verify" : ""}</UiSpan>)}</UiBox></UiBox>}<UiBox className="mt-5 grid gap-4 sm:grid-cols-2"><UiLabel className="text-xs font-semibold">Linked supplier<UiSelect name="vendor" required defaultValue={editing.vendor||""} className="mt-2 w-full"><option value="">Select supplier…</option>{suppliers.map(supplier=><option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</UiSelect><UiText className="mt-1 text-xs text-slate-500">Choose the supplier record used for approvals and payment.</UiText></UiLabel>{[["supplier_name", "Supplier", editing.supplier_name || editing.vendor_name || ""], ["invoice_number", "Invoice number", editing.invoice_number], ["invoice_date", "Invoice date", editing.invoice_date || ""], ["invoice_total", "Invoice total", editing.invoice_total]].map(([name, label, value]) => <UiLabel key={name} className="text-xs font-semibold">{label}<UiInput name={name} type={name === "invoice_date" ? "date" : name === "invoice_total" ? "number" : "text"} min={name === "invoice_total" ? "0.01" : undefined} step={name === "invoice_total" ? "0.01" : undefined} defaultValue={value} required={name !== "invoice_date"} className="mt-2 w-full rounded-lg border border-line px-3 py-2.5 text-sm font-normal"/></UiLabel>)}</UiBox><UiBox className="mt-6 flex items-center justify-between"><UiBox><UiH3 className="text-sm font-bold">Invoice line items</UiH3><UiText className="mt-1 text-[11px] text-slate-500">Add reviewed lines so matching can compare quantities, rates, and GST.</UiText></UiBox><UiButton type="button" onClick={addLine} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold text-forest">Add line</UiButton></UiBox><UiBox className="mt-3 space-y-3">{editingLines.map((line, index) => <UiBox key={index} className="rounded-lg border border-line p-3"><UiBox className="grid gap-2 sm:grid-cols-4">{([["description", "Description", "text"], ["item_code", "Item code", "text"], ["quantity", "Quantity", "number"], ["uom", "UOM", "text"], ["rate", "Rate", "number"], ["taxable_value", "Taxable value", "number"], ["gst_rate", "GST %", "number"], ["gst_amount", "GST amount", "number"]] as const).map(([key, label, type]) => <UiLabel key={key} className="text-[10px] font-semibold text-slate-600">{label}<UiInput name={`lines.${index}.${key}`} min={type === "number" ? (key === "quantity" ? "0.000001" : "0") : undefined} type={type} step={type === "number" ? "0.000001" : undefined} value={line[key] ?? ""} required={["description", "quantity", "rate"].includes(key)} onChange={event => setLine(index, key, event.target.value)} className="mt-1 w-full rounded-md border border-line px-2 py-2 text-xs font-normal"/></UiLabel>)}</UiBox><UiButton type="button" onClick={() => setEditingLines(lines => lines.filter((_, i) => i !== index))} className="mt-2 text-[10px] font-semibold text-rose-700">Remove line</UiButton></UiBox>)}{editingLines.length === 0 && <EmptyState description="Add at least one reviewed line before matching." onAction={addLine} actionLabel="Add line item" />}</UiBox><UiBox className="mt-6 flex justify-end gap-2"><UiButton type="button" onClick={() => setEditing(null)} className="rounded-lg border border-line px-4 py-2 text-xs font-semibold">Cancel</UiButton><UiButton disabled={busy === editing.id} className="inline-flex items-center gap-2 rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white">{busy === editing.id ? <UiSpinner className="animate-spin" size={14}/> : <Check size={14}/>}Save corrections</UiButton></UiBox></UiForm></UiReviewDrawer>}
  <InvoiceUploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} onUpload={upload} busy={busy === "upload"} automatic={extractionEnabled}/></UiMain>;
}
