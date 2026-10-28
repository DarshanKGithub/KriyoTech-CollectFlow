"use client";
import { UiAlert, UiArticle, UiBox, UiButton, UiH1, UiH2, UiMain, UiSpan, UiText } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Duplicate = {
    id: string;
    invoice_id: string;
    invoice_number: string;
    candidate_invoice_id: string;
    candidate_number: string;
    kind: string;
    score: string;
    reasons: string[];
    decision: string;
};
export default function DuplicateReviewPage() {
    const [rows, setRows] = useState<Duplicate[]>([]);
    const [message, setMessage] = useState("Loading duplicate candidates…");
    const [busy, setBusy] = useState("");
    async function load() { try {
        const r = await apiFetch("/duplicate-checks?decision=PENDING");
        if (!r.ok)
            throw new Error(r.status === 401 ? "Sign in to review duplicates." : "Could not load duplicate candidates.");
        const data = await r.json();
        setRows(data);
        setMessage(data.length ? "" : "No duplicate candidates need review.");
    }
    catch (e) {
        setMessage(e instanceof Error ? e.message : "Could not load duplicate candidates.");
    } }
    useEffect(() => { void load(); }, []);
    async function decide(row: Duplicate, decision: "CONFIRM_DUPLICATE" | "NOT_DUPLICATE") { setBusy(row.id); try {
        const r = await apiFetch(`/duplicate-checks/${row.id}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
        const d = await r.json();
        if (!r.ok)
            throw new Error(d.error?.message || "Could not save the review.");
        await load();
    }
    catch (e) {
        setMessage(e instanceof Error ? e.message : "Could not save the review.");
    }
    finally {
        setBusy("");
    } }
    const pagination = useListPagination(rows);
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><UiText className="text-[10px] font-bold uppercase tracking-[.18em] text-forest">Control queue</UiText><UiH1 className="mt-2 text-2xl font-bold">Duplicate review</UiH1><UiText className="mt-1 text-sm text-slate-500">Compare suspected duplicate invoices and record a finance decision.</UiText>{message && <UiAlert role="status" className="mt-5 rounded-lg border border-line bg-white px-4 py-3 text-sm text-slate-600">{message}</UiAlert>}<UiBox className="mt-6 space-y-3">{pagination.rows.map(row => <UiArticle key={row.id} className="rounded-xl border border-line bg-white p-5 shadow-card"><UiBox className="flex flex-wrap items-start justify-between gap-4"><UiBox><UiText className="text-xs font-semibold text-slate-400">{row.kind} · confidence {Math.round(Number(row.score) * 100)}%</UiText><UiH2 className="mt-2 font-bold">{row.invoice_number || "Unnumbered invoice"} <UiSpan className="font-normal text-slate-400">may match</UiSpan> {row.candidate_number || "Unnumbered invoice"}</UiH2><UiText className="mt-2 text-xs text-slate-500">{row.reasons.join(" · ")}</UiText></UiBox><UiBox className="flex gap-2"><UiButton disabled={!!busy} onClick={() => void decide(row, "NOT_DUPLICATE")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Not duplicate</UiButton><UiButton disabled={!!busy} onClick={() => void decide(row, "CONFIRM_DUPLICATE")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === row.id ? "Saving…" : "Confirm duplicate"}</UiButton></UiBox></UiBox></UiArticle>)}</UiBox>{pagination.controls}</UiMain>;
}
