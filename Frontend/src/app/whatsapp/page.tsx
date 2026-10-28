"use client";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiSpinner, UiStrong, UiText, UiTextarea } from "@/components/product-ui";
import { requestConfirmation, requestInput } from "@/components/product-dialogs";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Check, CircleAlert, MessageCircle, RefreshCw, Send } from "lucide-react";
import { apiFetch } from "@/lib/api";
type Endpoint = {
    id: string;
    phone_number_id: string;
    display_phone_number: string;
    active: boolean;
};
type Invoice = {
    id: string;
    invoice_number: string;
    vendor_name?: string;
    vendor_phone?: string;
    supplier_name?: string;
    invoice_total: string;
    status: string;
};
type Draft = {
    id: string;
    invoice_number: string;
    recipient_phone: string;
    purpose: string;
    body: string;
    status: string;
    error: string;
    created_at: string;
    send_started_at: string | null;
    reconciliation_available: boolean;
};
type Message = {
    id: string;
    contact_phone: string;
    direction: string;
    message_type: string;
    body: string;
    status: string;
    invoice_id?: string;
    invoice_number?: string;
    error: string;
    created_at: string;
};
type Consent = {
    id: string;
    phone: string;
    status: "OPTED_IN" | "OPTED_OUT";
    source: "MANUAL" | "INBOUND_KEYWORD";
    evidence_note: string;
    vendor_name: string | null;
    updated_by: string | null;
    updated_at: string;
};
const purposeLabels: Record<string, string> = { APPROVAL_REQUEST: "Approval request", PAYMENT_REMINDER: "Payment due reminder", CLARIFICATION: "Clarification request", OTHER: "Other" };
export default function WhatsAppPage() {
    const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [drafts, setDrafts] = useState<Draft[]>([]);
    const [messages, setMessages] = useState<Message[]>([]);
    const [consents, setConsents] = useState<Consent[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const [recipientPhone, setRecipientPhone] = useState("");
    const load = useCallback(async () => {
        setLoading(true);
        setMessage("");
        try {
            const [endpointResponse, invoiceResponse, draftResponse, messageResponse, consentResponse] = await Promise.all([
                apiFetch("/whatsapp/endpoints"), apiFetch("/invoices/"), apiFetch("/whatsapp/drafts"), apiFetch("/whatsapp/messages"), apiFetch("/whatsapp/consents"),
            ]);
            for (const response of [endpointResponse, invoiceResponse, draftResponse, messageResponse, consentResponse]) {
                if (!response.ok)
                    throw new Error(response.status === 401 ? "Sign in again to view WhatsApp activity." : "We could not load WhatsApp activity. Check your connection and try again.");
            }
            const [endpointData, invoiceData, draftData, messageData, consentData] = await Promise.all([
                endpointResponse.json(), invoiceResponse.json(), draftResponse.json(), messageResponse.json(), consentResponse.json(),
            ]);
            setEndpoints(endpointData);
            setInvoices(invoiceData.results || []);
            setDrafts(draftData);
            setMessages(messageData);
            setConsents(consentData);
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "We could not load WhatsApp activity.");
        }
        finally {
            setLoading(false);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    async function connect(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy("connect");
        setMessage("");
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        try {
            const response = await apiFetch("/whatsapp/endpoints", { method: "POST", body: JSON.stringify({ phone_number_id: form.get("phone_number_id"), display_phone_number: form.get("display_phone_number") }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "We could not connect this WhatsApp number.");
            setMessage("WhatsApp number connected to this workspace.");
            formElement.reset();
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "We could not connect this number.");
        }
        finally {
            setBusy("");
        }
    }
    async function createDraft(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy("draft");
        setMessage("");
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        try {
            const response = await apiFetch("/whatsapp/drafts", { method: "POST", body: JSON.stringify({
                    endpoint_id: form.get("endpoint_id"), invoice_id: form.get("invoice_id"), purpose: form.get("purpose"),
                    recipient_phone: form.get("recipient_phone"), body: form.get("body"),
                }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "We could not save the draft.");
            setMessage("Message draft saved. Nothing has been sent yet.");
            formElement.reset();
            setRecipientPhone("");
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "We could not save the draft.");
        }
        finally {
            setBusy("");
        }
    }
    async function recordConsent(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy("consent");
        setMessage("");
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        try {
            const response = await apiFetch("/whatsapp/consents", { method: "POST", body: JSON.stringify({
                    phone: form.get("phone"), action: form.get("action"), evidence_note: form.get("evidence_note"),
                }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "We could not update WhatsApp consent.");
            setMessage(data.status === "OPTED_IN" ? "Verified opt-in recorded. Drafting is now enabled for this number." : "Opt-out recorded. Any unsent drafts for this number are blocked.");
            formElement.reset();
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "We could not update WhatsApp consent.");
        }
        finally {
            setBusy("");
        }
    }
    async function sendDraft(draft: Draft) {
        if (!(await requestConfirmation(`Send this WhatsApp ${purposeLabels[draft.purpose] || "message"} to ${draft.recipient_phone}?`)))
            return;
        setBusy(draft.id);
        setMessage("");
        try {
            const response = await apiFetch(`/whatsapp/drafts/${draft.id}/send`, { method: "POST", body: JSON.stringify({}) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "We could not send this message.");
            setMessage("WhatsApp message sent. Delivery updates will appear in the activity log.");
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "We could not send this message.");
        }
        finally {
            setBusy("");
        }
    }
    async function reconcileDraft(draft: Draft, action: "confirm_sent" | "confirm_not_sent") {
        const confirmedOutcome = action === "confirm_sent" ? "sent" : "not sent";
        if (!(await requestConfirmation(`Have you checked Meta WhatsApp Manager and verified that this message was ${confirmedOutcome}? This does not send or retry the message.`)))
            return;
        const evidenceNote = (await requestInput(action === "confirm_sent" ? "Enter the Meta WhatsApp message ID and where you verified delivery." : "Describe where you checked and verified that Meta did not accept this message."));
        if (!evidenceNote?.trim())
            return;
        const providerMessageId = action === "confirm_sent" ? (await requestInput("Paste the Meta WhatsApp message ID (wamid) for this delivery."))?.trim() : undefined;
        if (action === "confirm_sent" && !providerMessageId)
            return;
        setBusy(draft.id);
        setMessage("");
        try {
            const response = await apiFetch(`/whatsapp/drafts/${draft.id}/reconcile`, { method: "POST", body: JSON.stringify({ action, evidence_note: evidenceNote.trim(), ...(providerMessageId ? { provider_message_id: providerMessageId } : {}) }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "We could not reconcile this send outcome.");
            setMessage(`WhatsApp send outcome reconciled as ${confirmedOutcome}.`);
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "We could not reconcile this send outcome.");
        }
        finally {
            setBusy("");
        }
    }
    async function linkMessage(messageId: string, invoiceId: string) {
        if (!invoiceId)
            return;
        setBusy(messageId);
        setMessage("");
        try {
            const response = await apiFetch(`/whatsapp/messages/${messageId}`, { method: "PATCH", body: JSON.stringify({ invoice_id: invoiceId }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "We could not link this message.");
            setMessage(`Message linked to invoice ${data.invoice_number || "record"}.`);
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "We could not link this message.");
        }
        finally {
            setBusy("");
        }
    }
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-7 pb-20 lg:pb-8">
    <UiBox className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-[11px] font-semibold uppercase tracking-[.15em] text-forest">Vendor communication</UiText><UiH1 className="mt-1 text-2xl font-bold">WhatsApp</UiH1><UiText className="mt-1 max-w-2xl text-sm text-slate-500">Receive invoice attachments and keep every vendor message linked to its invoice. Outbound messages stay in draft until a finance user reviews and sends them.</UiText></UiBox><UiButton onClick={() => void load()} className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-line bg-white px-3 text-xs font-semibold text-slate-700"><RefreshCw size={14}/>Refresh</UiButton></UiBox>
    {message && <UiBox role="status" className="mt-5 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><CircleAlert size={17} className="mt-0.5 shrink-0"/>{message}</UiBox>}

    <UiSection className="mt-5 grid gap-5 xl:grid-cols-[.9fr_1.1fr]">
      <UiBox className="space-y-5">
        <UiArticle className="rounded-xl border border-line bg-white p-5 shadow-card">
          <UiBox className="flex items-center gap-2"><MessageCircle size={18} className="text-forest"/><UiH2 className="text-sm font-bold">Connect a WhatsApp Business number</UiH2></UiBox>
          <UiText className="mt-2 text-xs leading-5 text-slate-500">Add the phone number ID from Meta. Keep access tokens and app secrets in the backend environment; never paste them into this form.</UiText>
          <ol className="mt-3 list-inside list-decimal space-y-1 text-[11px] leading-5 text-slate-600"><li>Set <code>WHATSAPP_ACCESS_TOKEN</code>, <code>WHATSAPP_APP_SECRET</code>, and <code>WHATSAPP_VERIFY_TOKEN</code> for Django.</li><li>Set the enabled Graph API version and an approved one-placeholder utility template.</li><li>Register <code>/api/v1/whatsapp/webhook</code> with Meta and subscribe to message events.</li></ol>
          {endpoints.map(endpoint => <UiBox key={endpoint.id} className="mt-3 flex items-center justify-between rounded-lg bg-emerald-50 px-3 py-2 text-xs"><UiSpan><UiStrong>{endpoint.display_phone_number || "Connected number"}</UiStrong><UiSpan className="ml-2 text-slate-500">ID {endpoint.phone_number_id}</UiSpan></UiSpan><UiSpan className="font-semibold text-emerald-800">Connected</UiSpan></UiBox>)}
          <UiForm onSubmit={connect} className="mt-4 grid gap-3 sm:grid-cols-2"><UiLabel className="text-xs font-semibold">Meta phone number ID<UiInput name="phone_number_id" inputMode="numeric" pattern="[0-9]+" required placeholder="123456789012345" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiLabel className="text-xs font-semibold">Display number (optional)<UiInput name="display_phone_number" type="tel" placeholder="+91 98765 43210" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiButton disabled={busy === "connect"} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-forest px-3 text-xs font-semibold text-white sm:col-span-2 disabled:opacity-60">{busy === "connect" && <UiSpinner size={14} className="animate-spin"/>}Connect number</UiButton></UiForm>
        </UiArticle>

        <UiArticle className="rounded-xl border border-line bg-white p-5 shadow-card">
          <UiH2 className="text-sm font-bold">Prepare a vendor message</UiH2><UiText className="mt-1 text-xs text-slate-500">Use an approval request, due-date reminder, or clarification. Saving creates a draft only.</UiText>
          <UiForm onSubmit={createDraft} className="mt-4 space-y-3">
            <UiLabel className="block text-xs font-semibold">Invoice<UiSelect name="invoice_id" required defaultValue="" onChange={event => setRecipientPhone(invoices.find(invoice => invoice.id === event.target.value)?.vendor_phone || "")} className="mt-1.5 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal"><option value="" disabled>Select an invoice</option>{invoices.map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.invoice_number || "Invoice pending review"} · {invoice.vendor_name || invoice.supplier_name || "Unknown vendor"} · ₹{Number(invoice.invoice_total || 0).toLocaleString("en-IN")}</option>)}</UiSelect></UiLabel>
            <UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="text-xs font-semibold">WhatsApp number<UiSelect name="endpoint_id" required defaultValue="" className="mt-1.5 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal"><option value="" disabled>Select connected number</option>{endpoints.filter(item => item.active).map(item => <option key={item.id} value={item.id}>{item.display_phone_number || item.phone_number_id}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold">Message type<UiSelect name="purpose" className="mt-1.5 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal">{Object.entries(purposeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</UiSelect></UiLabel></UiBox>
            <UiLabel className="block text-xs font-semibold">Vendor’s WhatsApp number<UiInput name="recipient_phone" type="tel" required value={recipientPhone} onChange={event => setRecipientPhone(event.target.value)} placeholder="+91 98765 43210" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/><UiSpan className="mt-1 block font-normal text-slate-500">We’ll fill this from the vendor record when available. Include the country code. An active recorded opt-in is required.</UiSpan></UiLabel>
            <UiLabel className="block text-xs font-semibold">Message<UiTextarea name="body" required minLength={4} maxLength={1024} rows={4} placeholder="Write a clear message and include the invoice reference." className="mt-1.5 w-full rounded-lg border border-line px-3 py-2 text-sm font-normal"/></UiLabel>
            <UiButton disabled={busy === "draft" || !endpoints.some(item => item.active) || invoices.length === 0} className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg border border-forest px-3 text-xs font-semibold text-forest disabled:cursor-not-allowed disabled:opacity-50">{busy === "draft" && <UiSpinner size={14} className="animate-spin"/>}Save message draft</UiButton>
          </UiForm>
          {(!endpoints.length || !invoices.length) && <UiText className="mt-3 text-[11px] text-slate-500">{!endpoints.length ? "Connect a WhatsApp number and configure Meta credentials to enable drafts." : "Add an invoice before drafting a vendor message."}</UiText>}
        </UiArticle>

        <UiArticle className="rounded-xl border border-line bg-white p-5 shadow-card">
          <UiH2 className="text-sm font-bold">Vendor consent register</UiH2>
          <UiText className="mt-1 text-xs leading-5 text-slate-500">Record consent only after you have verified the vendor’s actual preference. Incoming STOP, UNSUBSCRIBE, CANCEL, END, and QUIT messages revoke consent automatically.</UiText>
          <UiForm onSubmit={recordConsent} className="mt-4 grid gap-3 sm:grid-cols-2">
            <UiLabel className="text-xs font-semibold">Vendor WhatsApp number<UiInput name="phone" type="tel" required placeholder="+91 98765 43210" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel>
            <UiLabel className="text-xs font-semibold">Action<UiSelect name="action" className="mt-1.5 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal"><option value="opt_in">Record verified opt-in</option><option value="opt_out">Record opt-out</option></UiSelect></UiLabel>
            <UiLabel className="text-xs font-semibold sm:col-span-2">Evidence / source note<UiTextarea name="evidence_note" required minLength={8} maxLength={2000} rows={2} placeholder="For example: supplier confirmed during onboarding call on 18 Oct." className="mt-1.5 w-full rounded-lg border border-line px-3 py-2 text-sm font-normal"/></UiLabel>
            <UiButton disabled={busy === "consent"} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-forest px-3 text-xs font-semibold text-white sm:col-span-2 disabled:opacity-60">{busy === "consent" && <UiSpinner size={14} className="animate-spin"/>}Save consent record</UiButton>
          </UiForm>
          <UiBox className="mt-4 divide-y divide-line">{consents.map(item => <UiBox key={item.id} className="py-2.5"><UiBox className="flex flex-wrap items-center justify-between gap-2 text-xs"><UiSpan className="font-semibold">{item.vendor_name || item.phone}</UiSpan><UiSpan className={`rounded-full px-2 py-1 text-[10px] font-bold ${item.status === "OPTED_IN" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{item.status === "OPTED_IN" ? "Opted in" : "Opted out"}</UiSpan></UiBox><UiText className="mt-1 text-[11px] text-slate-500">{item.evidence_note} · {item.source === "INBOUND_KEYWORD" ? "Vendor message" : `Recorded${item.updated_by ? ` by ${item.updated_by}` : ""}`}</UiText></UiBox>)}{!consents.length && <UiText className="py-3 text-xs text-slate-500">No consent records yet. Opt-in evidence must be recorded before a message draft can be created.</UiText>}</UiBox>
        </UiArticle>
      </UiBox>

      <UiBox className="space-y-5">
        <UiArticle className="overflow-hidden rounded-xl border border-line bg-white shadow-card"><UiBox className="border-b border-line px-5 py-4"><UiH2 className="text-sm font-bold">Message drafts</UiH2><UiText className="mt-1 text-xs text-slate-500">Every send is an explicit, audited action.</UiText></UiBox>{loading ? <ContentSkeleton variant="cards" label="Loading messages" /> : drafts.length === 0 ? <UiBox className="p-9 text-center"><Send className="mx-auto text-slate-300" size={20}/><UiText className="mt-2 text-sm font-semibold">No drafts yet</UiText><UiText className="mt-1 text-xs text-slate-500">Prepare a reminder or clarification when an invoice needs vendor input.</UiText></UiBox> : <UiBox className="divide-y divide-line">{drafts.map(draft => <UiBox key={draft.id} className="p-4"><UiBox className="flex flex-wrap items-center justify-between gap-2"><UiBox><UiStrong className="text-xs">{draft.invoice_number || "Invoice"}</UiStrong><UiSpan className="ml-2 text-[11px] text-slate-500">{purposeLabels[draft.purpose] || draft.purpose} · {draft.recipient_phone}</UiSpan></UiBox><UiSpan className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold">{draft.status.toLowerCase()}</UiSpan></UiBox><UiText className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-600">{draft.body}</UiText>{draft.error && <UiAlert role="alert" className="mt-2 text-xs text-rose-700">{draft.error}</UiAlert>}{draft.status === "DRAFT" && <UiButton disabled={busy === draft.id} onClick={() => void sendDraft(draft)} className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-lg bg-forest px-3 text-xs font-semibold text-white disabled:opacity-60">{busy === draft.id ? <UiSpinner size={14} className="animate-spin"/> : <Check size={14}/>}Review & send</UiButton>}{draft.status === "SENDING" && <UiBox className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3"><UiText className="text-xs font-semibold text-amber-950">Send outcome needs checking</UiText><UiText className="mt-1 text-[11px] leading-5 text-amber-900">Check Meta WhatsApp Manager before recording the result. This control never retries a send.{!draft.reconciliation_available && " Reconciliation unlocks five minutes after the attempt."}</UiText>{draft.reconciliation_available && <UiBox className="mt-2 flex flex-wrap gap-2"><UiButton disabled={busy === draft.id} onClick={() => void reconcileDraft(draft, "confirm_sent")} className="min-h-9 rounded-lg bg-forest px-3 text-xs font-semibold text-white disabled:opacity-50">Confirm sent</UiButton><UiButton disabled={busy === draft.id} onClick={() => void reconcileDraft(draft, "confirm_not_sent")} className="min-h-9 rounded-lg border border-amber-400 bg-white px-3 text-xs font-semibold text-amber-950 disabled:opacity-50">Confirm not sent</UiButton></UiBox>}</UiBox>}</UiBox>)}</UiBox>}</UiArticle>
        <UiArticle className="overflow-hidden rounded-xl border border-line bg-white shadow-card"><UiBox className="border-b border-line px-5 py-4"><UiH2 className="text-sm font-bold">WhatsApp activity</UiH2><UiText className="mt-1 text-xs text-slate-500">Received messages and delivery status. Link a message to an invoice when its reference is unclear.</UiText></UiBox>{loading ? <ContentSkeleton variant="cards" label="Loading activity" /> : messages.length === 0 ? <UiBox className="p-9 text-center text-xs text-slate-500">No WhatsApp messages received yet.</UiBox> : <UiBox className="max-h-[520px] divide-y divide-line overflow-y-auto">{messages.map(item => <UiBox key={item.id} className="px-4 py-3"><UiBox className="flex items-center justify-between gap-3"><UiSpan className="text-xs font-semibold">{item.direction === "INBOUND" ? "From" : "To"} {item.contact_phone}</UiSpan><UiSpan className="text-[10px] text-slate-400">{new Date(item.created_at).toLocaleString("en-IN")}</UiSpan></UiBox><UiText className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-600">{item.body || (item.message_type === "document" || item.message_type === "image" ? "Invoice attachment received" : "No text content")}</UiText><UiBox className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-500"><UiSpan>{item.status.toLowerCase()}</UiSpan>{item.invoice_number && <UiSpan>· Invoice {item.invoice_number}</UiSpan>}{item.error && <UiSpan className="text-rose-700">· {item.error}</UiSpan>}</UiBox>{!item.invoice_id && item.direction === "INBOUND" && <UiSelect aria-label={`Link message from ${item.contact_phone} to an invoice`} defaultValue="" disabled={busy === item.id} onChange={event => void linkMessage(item.id, event.target.value)} className="mt-2 min-h-9 rounded-lg border border-line bg-white px-2 text-xs"><option value="">Link to invoice…</option>{invoices.map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.invoice_number || "Invoice pending review"} · {invoice.vendor_name || invoice.supplier_name || "Unknown vendor"}</option>)}</UiSelect>}</UiBox>)}</UiBox>}</UiArticle>
      </UiBox>
    </UiSection>
  </UiMain>;
}
