"use client";
import { UiAlert, UiArticle, UiBox, UiButton, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiText } from "@/components/product-ui";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Invoice = {
    id: string;
    invoice_number: string;
    supplier_name: string;
    invoice_total: string;
};
type Suggestion = {
    id: string;
    invoice_id: string;
    invoice_number: string;
    supplier: string;
    type: string;
    title: string;
    rationale: string;
    confidence: string;
    evidence_fields: string[];
    status: string;
    reviewed_by: string | null;
    created_at: string;
};
type Provider = {
    configured: boolean;
    model: string;
};
type Settings = {
    enabled: boolean;
    provider_configured: boolean;
    provider: "openai" | "gemini";
    model: string;
    providers: Record<"openai" | "gemini", Provider>;
    can_configure: boolean;
    processing: string;
};
export default function AIReviewPage() {
    const [settings, setSettings] = useState<Settings | null>(null);
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
    const [invoiceId, setInvoiceId] = useState("");
    const [confirmed, setConfirmed] = useState(false);
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState(false);
    async function load() {
        const [s, i, a] = await Promise.all([apiFetch("/ai-review/settings"), apiFetch("/invoices/"), apiFetch("/ai-review/suggestions")]);
        if (s.ok)
            setSettings(await s.json());
        if (i.ok) {
            const d = await i.json();
            setInvoices(d.results || []);
        }
        if (a.ok)
            setSuggestions(await a.json());
    }
    useEffect(() => { void load(); }, []);
    async function configure(body: {
        enabled?: boolean;
        provider?: "openai" | "gemini";
    }) {
        const response = await apiFetch("/ai-review/settings", { method: "PATCH", body: JSON.stringify(body) });
        const result = await response.json();
        setNotice(response.ok ? (body.provider ? `AI provider set to ${body.provider === "gemini" ? "Gemini" : "OpenAI"}.` : `AI review ${body.enabled ? "enabled" : "disabled"} for this workspace.`) : result.error || "Could not update workspace settings.");
        if (response.ok)
            await load();
    }
    async function generate() {
        if (!invoiceId || !confirmed)
            return;
        setBusy(true);
        setNotice("");
        const response = await apiFetch("/ai-review/suggestions", { method: "POST", body: JSON.stringify({ invoice_id: invoiceId, confirm_external_processing: true }) });
        const result = await response.json();
        setNotice(response.ok ? `${result.suggestions.length} review suggestion(s) created. Review them below.` : result.error || "AI review failed.");
        setBusy(false);
        setConfirmed(false);
        if (response.ok)
            await load();
    }
    async function decide(id: string, decision: "ACCEPTED" | "DISMISSED") {
        const response = await apiFetch("/ai-review/suggestions", { method: "PATCH", body: JSON.stringify({ suggestion_id: id, decision }) });
        const result = await response.json();
        setNotice(response.ok ? `Suggestion marked ${result.status.toLowerCase()}.` : result.error || "Could not save review decision.");
        if (response.ok)
            await load();
    }
    const selectedProvider = settings?.providers?.[settings.provider];
    const providerName = settings?.provider === "gemini" ? "Gemini" : "OpenAI";
    return <UiMain className="w-full min-w-0 space-y-6 px-5 py-8">
    <UiHeader><UiText className="text-xs font-bold uppercase tracking-[.14em] text-forest">Review tools</UiText><UiH1 className="mt-2 text-2xl font-bold">AI invoice review</UiH1><UiText className="mt-1 text-sm text-slate-500">Ask for evidence-backed review prompts, then decide what is useful. Suggestions never change invoice status or execute payments.</UiText></UiHeader>
    <UiSection className="rounded-xl border border-amber-200 bg-amber-50 p-4">
      <UiText className="text-sm font-semibold text-amber-950">External processing controls</UiText>
      <UiText className="mt-1 text-xs text-amber-900">{settings?.processing || "Invoice metadata is shared only after workspace enablement and explicit per-review confirmation."} The uploaded file itself is not sent. Do not enable this unless your workspace permits this processing.</UiText>
      <UiBox className="mt-3 flex flex-wrap items-center gap-3">
        <UiLabel className="text-xs font-medium">AI provider <UiSelect disabled={!settings?.can_configure} value={settings?.provider || "openai"} onChange={e => void configure({ provider: e.target.value as "openai" | "gemini" })} className="ml-2 rounded-lg border border-amber-300 bg-white px-2.5 py-2">
          <option value="openai">OpenAI {settings?.providers?.openai?.configured ? `· ${settings.providers.openai.model}` : "· not configured"}</option>
          <option value="gemini">Google Gemini {settings?.providers?.gemini?.configured ? `· ${settings.providers.gemini.model}` : "· not configured"}</option>
        </UiSelect></UiLabel>
        <UiSpan className="text-xs">Selected: {selectedProvider?.configured ? `${providerName} · ${settings?.model}` : `${providerName} is not configured`}</UiSpan>
        <UiButton disabled={!settings?.can_configure || !settings?.provider_configured} onClick={() => void configure({ enabled: !settings?.enabled })} className="rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-semibold disabled:opacity-50">{settings?.enabled ? "Disable AI review" : "Enable AI review"}</UiButton>
      </UiBox>
      {!settings?.can_configure && <UiText className="mt-2 text-xs text-amber-900">Ask a workspace owner to choose a provider and enable AI review.</UiText>}
    </UiSection>
    <UiSection className="rounded-xl border border-line bg-white p-5">
      <UiH2 className="text-sm font-bold">Generate suggestions for an invoice</UiH2>
      <UiBox className="mt-3 flex flex-wrap items-center gap-3"><UiSelect value={invoiceId} onChange={e => setInvoiceId(e.target.value)} aria-label="Select invoice for AI review" className="min-w-72 rounded-lg border border-line px-3 py-2 text-sm"><option value="">Select invoice</option>{invoices.map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.invoice_number || "No invoice number"} · {invoice.supplier_name || "Unknown supplier"} · ₹{invoice.invoice_total}</option>)}</UiSelect><UiButton disabled={!settings?.enabled || !settings.provider_configured || !invoiceId || !confirmed || busy} onClick={() => void generate()} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Reviewing…" : "Generate review suggestions"}</UiButton></UiBox>
      <UiLabel className="mt-3 flex max-w-3xl gap-2 text-xs text-slate-600"><UiInput type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5"/>I confirm that invoice metadata (supplier/invoice fields and up to 50 line descriptions and amounts) may be sent to {providerName} for this one review.</UiLabel>
      {notice && <UiAlert role="status" className="mt-3 text-xs text-slate-600">{notice}</UiAlert>}
    </UiSection>
    <UiSection className="space-y-3"><UiH2 className="text-sm font-bold">Review queue · {suggestions.length}</UiH2>
      {suggestions.map(item => <UiArticle key={item.id} className="rounded-xl border border-line bg-white p-5"><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiText className="text-[10px] font-bold uppercase tracking-wider text-forest">{item.type.replaceAll("_", " ")} · {Math.round(Number(item.confidence) * 100)}% model-reported confidence</UiText><UiH3 className="mt-1 font-semibold">{item.title}</UiH3><UiText className="mt-1 text-xs text-slate-500">Invoice {item.invoice_number || "—"} · {item.supplier}</UiText></UiBox><UiSpan className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold">{item.status}</UiSpan></UiBox><UiText className="mt-3 text-sm leading-6 text-slate-700">{item.rationale}</UiText>{item.evidence_fields.length > 0 && <UiText className="mt-2 text-[10px] text-slate-400">Fields: {item.evidence_fields.join(", ")}</UiText>}<UiText className="mt-2 text-[10px] text-slate-400">The confidence value is uncalibrated and is not a probability or approval decision.</UiText>{item.status === "PENDING" && <UiBox className="mt-4 flex gap-2"><UiButton onClick={() => void decide(item.id, "ACCEPTED")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Keep suggestion</UiButton><UiButton onClick={() => void decide(item.id, "DISMISSED")} className="rounded-lg border border-line px-3 py-2 text-xs">Dismiss</UiButton></UiBox>}</UiArticle>)}
      {!suggestions.length && <UiText className="rounded-xl border border-dashed border-line bg-white p-8 text-center text-sm text-slate-500">No suggestions yet. A workspace owner must configure a backend OpenAI or Gemini key and enable review.</UiText>}
    </UiSection>
  </UiMain>;
}
