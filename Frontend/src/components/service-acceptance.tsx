"use client";
import { UiAlert, UiBox, UiButton, UiH2, UiSection, UiSpan, UiText } from "@/components/product-ui";
import { requestInput } from "@/components/product-dialogs";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type GRNRow = {
    id: string;
    number: string;
    service_accepted: boolean;
    service_acceptance_reference: string;
    purchase_order_id?: string | null;
};
export function ServiceAcceptance() { const [rows, setRows] = useState<GRNRow[]>([]); const [message, setMessage] = useState(""); const load = useCallback(async () => { try {
    const r = await apiFetch("/grns");
    if (!r.ok)
        throw new Error("Could not load service receipts.");
    setRows(await r.json());
}
catch (e) {
    setMessage(e instanceof Error ? e.message : "Could not load service receipts.");
} }, []); useEffect(() => { void load(); }, [load]); async function toggle(row: GRNRow) { const accepted = !row.service_accepted; const reference = accepted ? (await requestInput(`Acceptance reference for ${row.number}`))?.trim() : ""; if (accepted && !reference)
    return; const r = await apiFetch(`/grns/${row.id}/service-acceptance`, { method: "PATCH", body: JSON.stringify({ service_accepted: accepted, service_acceptance_reference: reference }) }); const d = await r.json(); if (!r.ok) {
    setMessage(d.error?.message || "Could not update acceptance evidence.");
    return;
} setMessage(accepted ? "Service acceptance recorded." : "Service acceptance revoked and audited."); await load(); } return <UiSection className="mt-5 w-full min-w-0 overflow-hidden rounded-xl border border-line bg-white"><UiBox className="border-b border-line px-5 py-4"><UiH2 className="text-sm font-bold">Service acceptance evidence</UiH2><UiText className="mt-1 text-xs text-slate-500">Required before service invoices can pass matching when workspace controls require it.</UiText></UiBox>{message && <UiAlert role="status" className="px-5 py-3 text-xs text-amber-800">{message}</UiAlert>}{rows.map(row => <UiBox key={row.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3 text-xs"><UiSpan className="font-semibold">{row.number}<UiSpan className="ml-2 font-normal text-slate-400">{row.service_acceptance_reference || "No acceptance evidence"}</UiSpan></UiSpan><UiButton onClick={() => void toggle(row)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${row.service_accepted ? "border border-line text-slate-600" : "bg-forest text-white"}`}>{row.service_accepted ? "Revoke acceptance" : "Mark accepted"}</UiButton></UiBox>)}{rows.length === 0 && <UiText className="p-5 text-sm text-slate-500">Add GRNs to record service acceptance.</UiText>}</UiSection>; }
