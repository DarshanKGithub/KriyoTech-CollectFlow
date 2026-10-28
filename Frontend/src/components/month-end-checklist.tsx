"use client";
import { UiAlert, UiBox, UiButton, UiForm, UiH2, UiInput, UiLabel, UiSection, UiText } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Item = {
    key: string;
    title: string;
    outstanding_count: number;
    status: "OPEN" | "REVIEWED";
    review_note: string;
    reviewed_by: string | null;
    reviewed_at: string | null;
};
function currentPeriod() { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`; }
export function MonthEndChecklist() {
    const [period, setPeriod] = useState(currentPeriod());
    const [items, setItems] = useState<Item[]>([]);
    const [disclaimer, setDisclaimer] = useState("");
    const [reviewNote, setReviewNote] = useState("");
    const [notice, setNotice] = useState("");
    const [active, setActive] = useState("");
    const load = useCallback(async () => { const response = await apiFetch(`/compliance/month-end?period=${period}`); const data = await response.json(); if (response.ok) {
        setItems(data.items || []);
        setDisclaimer(data.note || "");
    }
    else
        setNotice(data.error || "Could not load checklist."); }, [period]);
    useEffect(() => { void load(); }, [load]);
    async function submit(e: FormEvent) { e.preventDefault(); const response = await apiFetch("/compliance/month-end", { method: "POST", body: JSON.stringify({ period, item_key: active, review_note: reviewNote }) }); const data = await response.json(); setNotice(response.ok ? "Month-end review recorded." : data.error || "Could not record review."); if (response.ok) {
        setActive("");
        setReviewNote("");
        await load();
    } }
    return <UiSection className="space-y-4 rounded-xl border border-line bg-white p-5"><UiBox className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiH2 className="text-sm font-bold">Month-end checklist</UiH2><UiText className="mt-1 text-xs text-slate-500">Operational review prompts. Mark each item reviewed with a short audit note.</UiText></UiBox><UiLabel className="grid gap-1 text-[11px] font-semibold text-slate-500">Period<UiInput aria-label="Checklist period" type="month" value={period} onChange={e => setPeriod(e.target.value)} className="rounded-lg border border-line px-2 py-1.5 text-sm text-ink"/></UiLabel></UiBox>{disclaimer && <UiText className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">{disclaimer}</UiText>}<UiBox className="divide-y divide-line">{items.map(item => <UiBox key={item.key} className="py-3"><UiBox className="flex flex-wrap items-center justify-between gap-3"><UiBox><UiText className="text-sm font-semibold">{item.title}</UiText><UiText className="mt-0.5 text-xs text-slate-500">{item.outstanding_count} item(s) flagged · {item.status === "REVIEWED" ? `Reviewed${item.reviewed_by ? ` by ${item.reviewed_by}` : ""}` : "Needs review"}</UiText>{item.review_note && <UiText className="mt-1 text-xs text-slate-400">{item.review_note}</UiText>}</UiBox><UiButton onClick={() => { setActive(active === item.key ? "" : item.key); setReviewNote(""); }} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">{item.status === "REVIEWED" ? "Update review" : "Review item"}</UiButton></UiBox>{active === item.key && <UiForm onSubmit={submit} className="mt-3 flex flex-wrap gap-2"><UiInput required minLength={8} maxLength={3000} value={reviewNote} onChange={e => setReviewNote(e.target.value)} placeholder="What did you check or follow up?" className="min-w-64 flex-1 rounded-lg border border-line px-3 py-2 text-sm"/><UiButton className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Save review</UiButton></UiForm>}</UiBox>)}{!items.length && <UiText className="py-4 text-sm text-slate-500">No checklist items loaded.</UiText>}</UiBox>{notice && <UiAlert role="status" className="text-xs text-slate-500">{notice}</UiAlert>}</UiSection>;
}
