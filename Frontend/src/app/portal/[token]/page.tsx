"use client";
import { DateField } from "@/components/date-field";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSmall, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
type Invoice = {
    id: string;
    invoice_number: string;
    invoice_date: string;
    due_date: string;
    amount: string;
    status: string;
    payment_status: string;
};
type PortalMessage = {
    direction: "INBOUND" | "OUTBOUND";
    body: string;
    created_at: string;
};
type PortalData = {
    vendor: string;
    workspace: string;
    expires_at: string;
    invoices: Invoice[];
};
export default function SupplierPortalPage() {
    const { token } = useParams<{
        token: string;
    }>();
    const [data, setData] = useState<PortalData | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [invoiceNumber, setInvoiceNumber] = useState("");
    const [invoiceDate, setInvoiceDate] = useState("");
    const [dueDate, setDueDate] = useState("");
    const [amount, setAmount] = useState("");
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState(false);
    const [activeInvoice, setActiveInvoice] = useState<Invoice | null>(null);
    const [messages, setMessages] = useState<PortalMessage[]>([]);
    const [messageBody, setMessageBody] = useState("");
    const load = useCallback(async () => {
        const response = await apiFetch(`/vendor-portal/access/${token}`);
        const result = await response.json();
        if (response.ok)
            setData(result);
        else
            setNotice(result.error || "This vendor link is unavailable.");
    }, [token]);
    useEffect(() => { void load(); }, [load]);
    async function submit(e: FormEvent) {
        e.preventDefault();
        if (!file)
            return;
        if(!/^\d{4}-\d{2}-\d{2}$/.test(invoiceDate) || (dueDate && !/^\d{4}-\d{2}-\d{2}$/.test(dueDate))){setNotice("Enter a valid invoice date and due date.");return;}
        setBusy(true);
        const form = new FormData();
        form.set("file", file);
        form.set("invoice_number", invoiceNumber);
        form.set("invoice_date", invoiceDate);
        form.set("due_date", dueDate);
        form.set("invoice_total", amount);
        const response = await apiFetch(`/vendor-portal/access/${token}`, { method: "POST", body: form });
        const result = await response.json();
        setNotice(response.ok ? `Invoice ${invoiceNumber} submitted for review.` : result.error || "Could not submit invoice.");
        setBusy(false);
        if (response.ok) {
            setFile(null);
            setInvoiceNumber("");
            setAmount("");
            await load();
        }
    }
    async function openConversation(invoice: Invoice) {
        setActiveInvoice(invoice);
        const response = await apiFetch(`/vendor-portal/access/${token}/invoices/${invoice.id}/messages`);
        const result = await response.json();
        if (response.ok)
            setMessages(result.messages || []);
        else
            setNotice(result.error || "Could not load this conversation.");
    }
    async function sendMessage(e: FormEvent) {
        e.preventDefault();
        if (!activeInvoice || !messageBody.trim())
            return;
        const response = await apiFetch(`/vendor-portal/access/${token}`, { method: "POST", body: JSON.stringify({ action: "message", invoice_id: activeInvoice.id, body: messageBody }) });
        const result = await response.json();
        setNotice(response.ok ? "Your message was sent to the workspace team." : result.error || "Message could not be sent.");
        if (response.ok) {
            setMessageBody("");
            await openConversation(activeInvoice);
        }
    }
    if (!data)
        return <UiMain className="mx-auto max-w-3xl px-5 py-16"><UiBox className="rounded-xl border border-line bg-white p-8 text-center"><UiStrong className="text-lg">KriyoPay supplier portal</UiStrong><UiText className="mt-3 text-sm text-slate-600">{notice || "Checking your secure link…"}</UiText></UiBox></UiMain>;
    return <UiMain className="mx-auto max-w-4xl space-y-6 px-5 py-10"><UiHeader><UiText className="text-xs font-bold uppercase tracking-[.14em] text-forest">{data.workspace}</UiText><UiH1 className="mt-2 text-2xl font-bold">Hello, {data.vendor}</UiH1><UiText className="mt-1 text-sm text-slate-500">Submit an invoice or check the status of documents sent to this workspace.</UiText></UiHeader><UiForm onSubmit={submit} className="grid gap-3 rounded-xl border border-line bg-white p-5 md:grid-cols-2"><UiH2 className="text-sm font-bold md:col-span-2">Submit an invoice</UiH2><UiInput required placeholder="Invoice number" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} className="rounded-lg border border-line px-3 py-2 text-sm"/><UiInput required type="number" min="0.01" step="0.01" placeholder="Total amount (INR)" value={amount} onChange={e => setAmount(e.target.value)} className="rounded-lg border border-line px-3 py-2 text-sm"/><UiLabel className="grid gap-1 text-xs text-slate-500">Invoice date<DateField required value={invoiceDate} onChange={setInvoiceDate} className="rounded-lg border border-line px-3 py-2 text-sm text-slate-800"/></UiLabel><UiLabel className="grid gap-1 text-xs text-slate-500">Due date<DateField value={dueDate} onChange={setDueDate} className="rounded-lg border border-line px-3 py-2 text-sm text-slate-800"/></UiLabel><UiLabel className="grid gap-1 text-xs text-slate-500 md:col-span-2">Invoice file (PDF, PNG, JPEG; max 12 MB)<UiInput required type="file" accept="application/pdf,image/png,image/jpeg" onChange={e => setFile(e.target.files?.[0] || null)} className="text-sm"/></UiLabel><UiButton disabled={busy || !file} className="w-fit rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Submitting…" : "Submit for review"}</UiButton>{notice && <UiAlert role="status" className="self-center text-xs text-slate-600">{notice}</UiAlert>}</UiForm><UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Your submitted invoices</UiH2><UiBox className="mt-3 divide-y divide-line">{data.invoices.map(invoice => <UiBox key={invoice.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><UiSpan><UiStrong>{invoice.invoice_number || "Invoice"}</UiStrong><UiSmall className="ml-2 text-slate-500">₹{invoice.amount} · {invoice.status.replaceAll("_", " ")} · {invoice.payment_status.replaceAll("_", " ")}</UiSmall></UiSpan><UiButton onClick={() => void openConversation(invoice)} className="rounded border border-line px-3 py-1.5 text-xs">View conversation</UiButton></UiBox>)}{!data.invoices.length && <UiText className="py-6 text-sm text-slate-500">No invoices submitted yet.</UiText>}</UiBox></UiSection>{activeInvoice && <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Conversation · {activeInvoice.invoice_number}</UiH2><UiBox className="mt-3 max-h-64 space-y-2 overflow-y-auto">{messages.map((message, i) => <UiBox key={`${message.created_at}-${i}`} className={`max-w-[85%] rounded-xl p-3 text-sm ${message.direction === "INBOUND" ? "bg-mint text-forest" : "ml-auto bg-slate-100 text-slate-700"}`}><UiText>{message.body}</UiText><time className="mt-1 block text-[10px] opacity-60">{new Date(message.created_at).toLocaleString()}</time></UiBox>)}{!messages.length && <UiText className="text-xs text-slate-500">No messages yet. Ask the workspace team a question.</UiText>}</UiBox><UiForm onSubmit={sendMessage} className="mt-3 flex gap-2"><UiInput value={messageBody} onChange={e => setMessageBody(e.target.value)} required maxLength={3000} placeholder="Write a question…" className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-sm"/><UiButton className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">Send</UiButton></UiForm>{notice && <UiAlert role="status" className="mt-2 text-xs text-slate-500">{notice}</UiAlert>}</UiSection>}<UiText className="text-xs text-slate-400">This secure link is vendor-specific and expires {new Date(data.expires_at).toLocaleDateString()}.</UiText></UiMain>;
}
