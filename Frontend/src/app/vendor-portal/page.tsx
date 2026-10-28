"use client";
import { UiAlert, UiBox, UiButton, UiH1, UiH2, UiHeader, UiInput, UiMain, UiSection, UiSelect, UiSmall, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Vendor = {
    id: string;
    name: string;
};
type Invite = {
    id: string;
    vendor_id: string;
    vendor: string;
    expires_at: string;
    revoked: boolean;
    created_at: string;
};
type Message = {
    id: string;
    invoice_id: string;
    invoice_number: string;
    vendor: string;
    direction: "INBOUND" | "OUTBOUND";
    body: string;
    created_at: string;
};
export default function VendorPortalPage() {
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [invites, setInvites] = useState<Invite[]>([]);
    const [messages, setMessages] = useState<Message[]>([]);
    const [vendorId, setVendorId] = useState("");
    const [url, setUrl] = useState("");
    const [notice, setNotice] = useState("");
    const [replying, setReplying] = useState("");
    const [reply, setReply] = useState("");
    async function load() { const [v, i, m] = await Promise.all([apiFetch("/vendors"), apiFetch("/vendor-portal/invitations"), apiFetch("/vendor-portal/messages")]); if (v.ok)
        setVendors(await v.json()); if (i.ok)
        setInvites(await i.json()); if (m.ok)
        setMessages(await m.json()); }
    useEffect(() => { void load(); }, []);
    async function create() { setNotice(""); const response = await apiFetch("/vendor-portal/invitations", { method: "POST", body: JSON.stringify({ vendor_id: vendorId, expires_in_days: 30 }) }); const data = await response.json(); if (!response.ok) {
        setNotice(data.error || "Could not create invitation.");
        return;
    } setUrl(data.url); setNotice(`Secure link created for ${data.vendor}. Copy and share it directly with the vendor.`); await load(); }
    async function revoke(id: string) { const response = await apiFetch(`/vendor-portal/invitations/${id}`, { method: "PATCH", body: JSON.stringify({ action: "revoke" }) }); setNotice(response.ok ? "Portal link revoked." : "Could not revoke portal link."); if (response.ok)
        await load(); }
    async function sendReply(invoiceId: string) { if (!reply.trim())
        return; const response = await apiFetch(`/vendor-portal/invoices/${invoiceId}/messages`, { method: "POST", body: JSON.stringify({ body: reply }) }); const result = await response.json(); setNotice(response.ok ? "Reply added to the supplier portal conversation." : result.error || "Could not send reply."); if (response.ok) {
        setReply("");
        setReplying("");
        await load();
    } }
    return <UiMain className="w-full min-w-0 space-y-6 px-5 py-8"><UiHeader><UiText className="text-xs font-bold uppercase tracking-[.14em] text-forest">Supplier collaboration</UiText><UiH1 className="mt-2 text-2xl font-bold">Vendor portal</UiH1><UiText className="mt-1 text-sm text-slate-500">Invite suppliers, receive their invoice questions, and reply in the portal.</UiText></UiHeader><UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Create a vendor link</UiH2><UiText className="mt-1 text-xs text-slate-500">Links expire in 30 days. Each link is private to one vendor and can be revoked at any time.</UiText><UiBox className="mt-4 flex flex-wrap gap-3"><UiSelect aria-label="Select vendor" value={vendorId} onChange={e => setVendorId(e.target.value)} className="min-w-64 rounded-lg border border-line px-3 py-2 text-sm"><option value="">Choose a vendor</option>{vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</UiSelect><UiButton disabled={!vendorId} onClick={() => void create()} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Create secure link</UiButton></UiBox>{url && <UiBox className="mt-4 rounded-lg bg-emerald-50 p-3"><UiText className="text-xs font-semibold text-emerald-900">Link shown once at creation. Store and share it securely.</UiText><UiBox className="mt-2 flex flex-wrap items-center gap-2"><UiInput aria-label="New vendor portal link" readOnly value={url} className="min-w-0 flex-1 rounded border border-emerald-200 bg-white px-2 py-2 text-xs"/><UiButton onClick={() => void navigator.clipboard.writeText(url)} className="rounded border border-emerald-200 bg-white px-3 py-2 text-xs font-semibold">Copy link</UiButton></UiBox></UiBox>}{notice && <UiAlert role="status" className="mt-3 text-xs text-slate-600">{notice}</UiAlert>}</UiSection><UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Supplier conversations</UiH2><UiBox className="mt-3 divide-y divide-line">{messages.map(message => <UiBox key={message.id} className="py-4"><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiText className="text-xs font-semibold text-forest">{message.vendor} · Invoice {message.invoice_number || "—"} · {message.direction === "INBOUND" ? "Supplier" : "Workspace"}</UiText><UiText className="mt-1 text-sm text-slate-700">{message.body}</UiText><time className="mt-1 block text-[10px] text-slate-400">{new Date(message.created_at).toLocaleString()}</time></UiBox><UiButton onClick={() => { setReplying(replying === message.invoice_id ? "" : message.invoice_id); setReply(""); }} className="rounded border border-line px-3 py-1.5 text-xs">Reply</UiButton></UiBox>{replying === message.invoice_id && <UiBox className="mt-3 flex gap-2"><UiInput value={reply} onChange={e => setReply(e.target.value)} maxLength={3000} placeholder="Write a portal reply…" className="min-w-0 flex-1 rounded border border-line px-3 py-2 text-sm"/><UiButton onClick={() => void sendReply(message.invoice_id)} className="rounded bg-forest px-3 py-2 text-xs font-semibold text-white">Send</UiButton></UiBox>}</UiBox>)}{!messages.length && <UiText className="py-5 text-xs text-slate-500">No supplier messages yet.</UiText>}</UiBox></UiSection><UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Issued links</UiH2><UiBox className="mt-3 divide-y divide-line">{invites.map(invite => <UiBox key={invite.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><UiSpan><UiStrong>{invite.vendor}</UiStrong><UiSmall className="ml-2 text-slate-500">Expires {new Date(invite.expires_at).toLocaleDateString()} · {invite.revoked ? "Revoked" : "Active"}</UiSmall></UiSpan>{!invite.revoked && <UiButton onClick={() => void revoke(invite.id)} className="rounded border border-line px-3 py-1.5 text-xs">Revoke</UiButton>}</UiBox>)}{!invites.length && <UiText className="py-5 text-xs text-slate-500">No portal invitations yet.</UiText>}</UiBox></UiSection></UiMain>;
}
