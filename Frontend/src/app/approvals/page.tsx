"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import { ArrowRight, Check, ClipboardCheck, ExternalLink, Search, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ContentSkeleton } from "@/components/content-skeleton";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { AppLink } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";

type Invoice = {
  id: string;
  invoice_number: string;
  supplier_name?: string;
  vendor_name?: string;
  invoice_date?: string;
  due_date?: string;
  po_number?: string;
  supplier_gstin?: string;
  taxable_total: string;
  gst_total: string;
  tds_total: string;
  invoice_total: string;
  document?: string;
  lines: { id: string; description: string; item_code: string; quantity: string; uom: string; taxable_value: string }[];
};

type History = {
  steps: { id: string; sequence: number; workflow_version: number; approver_role: string; status: string }[];
  decisions: { id: string; approver: string; decision: string; comments: string; decided_at: string }[];
};

type Decision = "approve" | "reject";

const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const money = (value: string) => currency.format(Number(value));
const date = (value?: string) => value ? dateFormat.format(new Date(value)) : "—";
const supplier = (invoice: Invoice) => invoice.vendor_name || invoice.supplier_name || "Supplier missing";
const invoiceNumber = (invoice: Invoice) => invoice.invoice_number || "No invoice number";
const readable = (value: string) => value.toLowerCase().replace(/_/g, " ").replace(/^./, letter => letter.toUpperCase());

function InvoiceReview({ invoice, onClose, onDecision }: {
  invoice: Invoice;
  onClose: () => void;
  onDecision: (invoice: Invoice, decision: Decision, status: string) => void;
}) {
  const [history, setHistory] = useState<History>();
  const [historyError, setHistoryError] = useState(false);
  const [sourceError, setSourceError] = useState("");
  const [openingSource, setOpeningSource] = useState(false);
  const [decision, setDecision] = useState<Decision>();
  const [comments, setComments] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadHistory() {
      try {
        const response = await apiFetch(`/invoices/${invoice.id}/approval-history`);
        if (!response.ok) throw new Error();
        const data: History = await response.json();
        if (active) setHistory(data);
      } catch {
        if (active) setHistoryError(true);
      }
    }
    void loadHistory();
    return () => { active = false; };
  }, [invoice.id]);

  async function openSource() {
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    setOpeningSource(true);
    setSourceError("");
    try {
      const response = await apiFetch(`/invoices/${invoice.id}/source/`);
      if (!response.ok) throw new Error();
      const url = URL.createObjectURL(await response.blob());
      if (tab) tab.location.href = url;
      else {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener";
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      tab?.close();
      setSourceError("Could not open the original invoice. Try again.");
    } finally {
      setOpeningSource(false);
    }
  }

  async function saveDecision() {
    if (!decision || saving) return;
    setSaving(true);
    setError("");
    try {
      const response = await apiFetch(`/invoices/${invoice.id}/${decision}/`, {
        method: "POST",
        body: JSON.stringify({ comments: comments.trim() }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.error?.message || `Could not ${decision} this invoice.`);
      onDecision(invoice, decision, data?.status);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not save your decision.");
    } finally {
      setSaving(false);
    }
  }

  const latestVersion = history?.steps.at(-1)?.workflow_version;
  const steps = history?.steps.filter(step => step.workflow_version === latestVersion) ?? [];

  return <Dialog open onClose={saving ? undefined : onClose} fullWidth maxWidth="md" aria-labelledby="invoice-review-title">
    <DialogTitle id="invoice-review-title" className="flex items-start justify-between gap-4">
      <span>
        <span className="block text-lg font-bold text-slate-900">Review invoice</span>
        <span className="block text-sm font-normal text-slate-600">{invoiceNumber(invoice)} · {supplier(invoice)}</span>
      </span>
      <Button aria-label="Close invoice review" color="inherit" disabled={saving} onClick={onClose} sx={{ minWidth: 36, p: 0.75 }}><X size={19} /></Button>
    </DialogTitle>
    <DialogContent dividers>
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl bg-slate-50 p-4">
        <div>
          <div className="text-sm text-slate-600">Invoice total</div>
          <div className="text-2xl font-bold tabular-nums text-slate-900">{money(invoice.invoice_total)}</div>
        </div>
        {invoice.document
          ? <Button variant="outlined" disabled={openingSource} onClick={() => void openSource()} endIcon={<ExternalLink size={15} />}>{openingSource ? "Opening…" : "Open original invoice"}</Button>
          : <span className="text-sm text-slate-600">No original document attached</span>}
      </div>
      {sourceError && <Alert severity="error" sx={{ mt: 2 }}>{sourceError}</Alert>}

      <dl className="my-5 grid grid-cols-2 gap-x-5 gap-y-3 text-sm sm:grid-cols-4">
        {[
          ["Invoice date", date(invoice.invoice_date)], ["Due date", date(invoice.due_date)],
          ["Purchase order", invoice.po_number || "—"], ["Supplier GSTIN", invoice.supplier_gstin || "—"],
          ["Taxable amount", money(invoice.taxable_total)], ["GST", money(invoice.gst_total)], ["TDS", money(invoice.tds_total)],
        ].map(([label, value]) => <div key={label}>
          <dt className="text-slate-600">{label}</dt><dd className="break-words font-semibold text-slate-900">{value}</dd>
        </div>)}
      </dl>

      <h2 className="mb-2 text-sm font-bold text-slate-900">Invoice items</h2>
      {invoice.lines?.length ? <ul className="divide-y divide-slate-200 rounded-xl border border-line px-4">
        {invoice.lines.map(line => <li key={line.id} className="flex items-start justify-between gap-4 py-3 text-sm">
          <div className="min-w-0">
            <div className="break-words font-medium text-slate-900">{line.description || line.item_code || "Item"}</div>
            <div className="text-slate-600">Qty {Number(line.quantity).toLocaleString("en-IN")} {line.uom}</div>
          </div>
          <span className="shrink-0 tabular-nums">{money(line.taxable_value)} <span className="text-xs text-slate-600">before tax</span></span>
        </li>)}
      </ul> : <p className="text-sm text-slate-600">No line items recorded.</p>}

      <section className="mt-5 border-t border-line pt-4" aria-labelledby="approval-history-title">
        <h2 id="approval-history-title" className="mb-2 text-sm font-bold text-slate-900">Approval history</h2>
        {!history && <p role="status" className="text-sm text-slate-600">{historyError ? "Could not load approval history. Reopen the review to retry." : "Loading approval history…"}</p>}
        {steps.length > 0 && <ol className="mb-3 flex flex-wrap gap-2">
          {steps.map(step => <li key={step.id} className="rounded-md bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
            Step {step.sequence}{step.approver_role ? ` · ${readable(step.approver_role)}` : ""} · {readable(step.status)}
          </li>)}
        </ol>}
        {history && (history.decisions.length ? <ul className="space-y-2">
          {history.decisions.map(entry => <li key={entry.id} className="text-sm">
            <span className="font-semibold">{readable(entry.decision)}</span> <span className="text-slate-600">by {entry.approver} · {date(entry.decided_at)}</span>
            {entry.comments && <p className="whitespace-pre-wrap break-words text-slate-700">{entry.comments}</p>}
          </li>)}
        </ul> : <p className="text-sm text-slate-600">No decisions recorded yet.</p>)}
      </section>
      {decision && <section className="mt-5 rounded-xl border border-line p-4" aria-labelledby="confirm-invoice-decision">
        <h2 id="confirm-invoice-decision" className="text-sm font-bold text-slate-900">{decision === "approve" ? "Confirm approval" : "Confirm rejection"}</h2>
        <p className="mb-3 mt-1 text-sm text-slate-600">{decision === "approve" ? "Record your approval for this step." : "Send this invoice back for correction."}</p>
        <TextField autoFocus fullWidth multiline minRows={2} size="small" label="Note (optional)" value={comments} disabled={saving} onChange={event => setComments(event.target.value)} />
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </section>}
    </DialogContent>
    <DialogActions sx={{ px: 3, py: 2, flexWrap: "wrap", gap: 1 }}>
      {decision ? <>
        <Button disabled={saving} onClick={() => { setDecision(undefined); setError(""); }}>Back to review</Button>
        <Button variant="contained" color={decision === "reject" ? "error" : "primary"} disabled={saving} onClick={() => void saveDecision()}>
          {saving ? "Saving…" : decision === "approve" ? "Confirm approval" : "Confirm rejection"}
        </Button>
      </> : <>
        <Button color="error" variant="outlined" onClick={() => setDecision("reject")} startIcon={<X size={16} />}>Reject</Button>
        <Button variant="contained" onClick={() => setDecision("approve")} startIcon={<Check size={16} />}>Approve</Button>
      </>}
    </DialogActions>
  </Dialog>;
}

export default function ApprovalsPage() {
  const [rows, setRows] = useState<Invoice[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Invoice>();
  const latestRequest = useRef(0);

  const load = useCallback(async (silent = false) => {
    const request = ++latestRequest.current;
    if (!silent) setLoading(true);
    try {
      const response = await apiFetch("/approvals/pending");
      if (!response.ok) throw new Error(response.status === 401 ? "Sign in to view approvals." : "Could not load approvals.");
      const invoices: Invoice[] = await response.json();
      if (request === latestRequest.current) {
        setRows(invoices);
        setError("");
      }
    } catch (failure) {
      if (silent) throw failure;
      if (request === latestRequest.current) setError(failure instanceof Error ? failure.message : "Could not load approvals.");
    } finally {
      if (request === latestRequest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => { latestRequest.current += 1; };
  }, [load]);

  function completeDecision(invoice: Invoice, decision: Decision, status?: string) {
    setSelected(undefined);
    setRows(previous => previous.filter(row => row.id !== invoice.id));
    const label = invoice.invoice_number || "Invoice";
    setNotice(decision === "reject" ? `${label} was sent back for correction.`
      : status === "PAYMENT_READY" ? `${label} is approved and ready for payment.`
      : status === "APPROVAL_PENDING" ? `Approval recorded for ${label}. It still needs another approval.`
      : `Approval recorded for ${label}.`);
    void load();
  }

  const search = query.trim().toLowerCase();
  const filtered = rows.filter(invoice => [invoice.invoice_number, invoice.vendor_name, invoice.supplier_name].some(value => value?.toLowerCase().includes(search)));
  const pagination = useListPagination(search ? filtered : rows, search, "Approval queue pages");

  return <main className="w-full min-w-0 px-4 py-6 sm:px-6 lg:px-8">
    <AppLink href="/" className="text-sm font-semibold text-forest">← Overview</AppLink>
    <header className="mb-5 mt-4 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Invoice approvals</h1>
        <p className="mt-1 text-sm text-slate-600">Review invoices waiting for your decision.</p>
      </div>
      <LiveData compact onRefresh={() => load(true)} paused={Boolean(selected || loading)} />
    </header>
    {notice && <Alert severity="success" onClose={() => setNotice("")} sx={{ mb: 2 }}>{notice}</Alert>}
    {error && <Alert severity="error" action={<Button color="inherit" size="small" disabled={loading} onClick={() => void load()}>Retry</Button>} sx={{ mb: 2 }}>{error}</Alert>}
    <section className="overflow-hidden rounded-xl border border-line bg-white shadow-card" aria-labelledby="waiting-approvals">
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 sm:px-5">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-800"><ClipboardCheck size={20} /></span>
          <div>
            <h2 id="waiting-approvals" className="text-base font-bold text-slate-900">Waiting for approval</h2>
            {!loading && !error && <p className="text-sm text-slate-600">{rows.length} {rows.length === 1 ? "invoice" : "invoices"} assigned to you</p>}
          </div>
        </div>
        <label className="flex w-full items-center gap-2 rounded-lg border border-line px-3 text-slate-500 focus-within:ring-2 focus-within:ring-emerald-700 sm:w-72">
          <Search size={17} className="shrink-0" aria-hidden />
          <span className="sr-only">Search by invoice number or supplier</span>
          <input type="search" className="min-w-0 flex-1 bg-transparent py-2.5 text-sm text-slate-900 outline-none" placeholder="Invoice number or supplier" value={query} onChange={event => setQuery(event.target.value)} />
        </label>
      </div>
      {loading ? <ContentSkeleton variant="table" label="Loading approvals" /> : error && rows.length === 0 ? null : pagination.rows.length === 0
        ? <div className="border-t border-line px-4 py-12 text-center">
          <p className="font-semibold text-slate-900">{search && rows.length ? "No matching invoices" : "You're all caught up"}</p>
          <p className="mt-1 text-sm text-slate-600">{search && rows.length ? "Try a different invoice number or supplier." : "New invoices will appear here when they need your approval."}</p>
        </div>
        : <>
          <div aria-hidden className="hidden border-y border-line bg-slate-50 px-5 py-2.5 text-xs font-semibold text-slate-600 sm:grid sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_10rem] sm:gap-4">
            <span>Invoice / Supplier</span><span>Invoice date</span><span className="text-right">Amount</span>
          </div>
          <ul className="divide-y divide-slate-200 border-t border-line sm:border-t-0">
            {pagination.rows.map(invoice => <li key={invoice.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-4 hover:bg-slate-50 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_10rem] sm:px-5">
              <div className="min-w-0 break-words">
                <div className="text-sm font-bold text-slate-900">{invoiceNumber(invoice)}</div>
                <div className="mt-0.5 text-sm text-slate-600">{supplier(invoice)}</div>
              </div>
              <div className="col-start-1 row-start-2 text-sm text-slate-600 sm:col-auto sm:row-auto"><span className="sr-only">Invoice date </span>{date(invoice.invoice_date)}</div>
              <div className="col-start-2 row-start-1 text-right text-sm font-bold tabular-nums text-slate-900 sm:col-auto sm:row-auto"><span className="sr-only">Amount </span>{money(invoice.invoice_total)}</div>
              <div className="justify-self-end">
                <Button size="small" variant="outlined" endIcon={<ArrowRight size={15} />} onClick={() => setSelected(invoice)} aria-label={`Review invoice ${invoiceNumber(invoice)} from ${supplier(invoice)}`}>Review invoice</Button>
              </div>
            </li>)}
          </ul>
          {filtered.length > 10 && pagination.controls}
        </>}
    </section>
    {selected && <InvoiceReview key={selected.id} invoice={selected} onClose={() => setSelected(undefined)} onDecision={completeDecision} />}
  </main>;
}
