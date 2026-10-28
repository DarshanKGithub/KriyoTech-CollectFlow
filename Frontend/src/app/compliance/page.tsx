"use client";
import { UiBox, UiButton, UiH1, UiHeader, UiMain, UiSpan, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { showNotice } from "@/components/product-dialogs";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { MonthEndChecklist } from "@/components/month-end-checklist";
type Row = {
    invoice_id: string;
    invoice_number: string;
    supplier: string;
    gstin: string;
    taxable_total: string;
    gst_total: string;
    tds_total: string;
    invoice_total: string;
    issues: string[];
    review: null | {
        gst_registration_status: string;
        itc_eligible: boolean | null;
        itc_block_reason: string;
        einvoice_irn: string;
        tds_section: string;
        tds_rate: string | null;
        tds_certificate_reference: string;
        review_note: string;
    };
};
export default function CompliancePage() {
    const [rows, setRows] = useState<Row[]>([]);
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState("");
    async function load() { const r = await apiFetch("/compliance/tax-reviews"); const data = await r.json(); setRows(data.results || []); setNote(data.disclaimer || ""); }
    useEffect(() => { void load(); }, []);
    async function review(row: Row) { setBusy(row.invoice_id); const r = await apiFetch("/compliance/tax-reviews", { method: "PATCH", body: JSON.stringify({ invoice_id: row.invoice_id, gst_registration_status: "UNKNOWN", review_note: "Reviewed in KriyoPay" }) }); setBusy(""); if (r.ok)
        void load();
    else
        showNotice("Could not save tax review."); }
    return <UiMain className="w-full min-w-0 space-y-6 px-5 py-8"><UiHeader><UiText className="text-xs font-bold uppercase tracking-[.14em] text-forest">Controls · Compliance</UiText><UiH1 className="mt-2 text-2xl font-bold">Tax review</UiH1><UiText className="mt-1 text-sm text-slate-500">Review invoice tax details, exceptions, and evidence before approval.</UiText></UiHeader><UiBox className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">{note || "Tax review uses local format and arithmetic checks. It does not contact government registries or provide a tax determination."}</UiBox><UiBox className="overflow-hidden rounded-xl border border-line bg-white"><UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[850px] text-left text-sm"><UiTableHead className="bg-slate-50 text-xs text-slate-500"><UiTableRow>{["Invoice", "Supplier / GSTIN", "Taxable", "GST", "TDS", "Review flags", "Action"].map(x => <UiTh key={x} className="px-4 py-3 font-semibold">{x}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{rows.map(row => <UiTableRow key={row.invoice_id} className="border-t border-line"><UiTd className="px-4 py-4 font-semibold">{row.invoice_number || "Unnumbered"}<UiSpan className="block text-xs font-normal text-slate-400">Total {row.invoice_total}</UiSpan></UiTd><UiTd className="px-4 py-4">{row.supplier || "Unknown supplier"}<UiSpan className="block text-xs text-slate-500">{row.gstin || "GSTIN missing"}</UiSpan></UiTd><UiTd className="px-4 py-4">₹{row.taxable_total}</UiTd><UiTd className="px-4 py-4">₹{row.gst_total}</UiTd><UiTd className="px-4 py-4">₹{row.tds_total}</UiTd><UiTd className="px-4 py-4">{row.issues.length ? row.issues.map(issue => <UiSpan key={issue} className="mb-1 block rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{issue}</UiSpan>) : <UiSpan className="text-xs text-emerald-700">No format/arithmetic flags</UiSpan>}</UiTd><UiTd className="px-4 py-4"><UiButton disabled={!!busy} onClick={() => void review(row)} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold hover:bg-slate-50 disabled:opacity-50">{busy === row.invoice_id ? "Saving…" : row.review ? "Reviewed" : "Mark reviewed"}</UiButton></UiTd></UiTableRow>)}{!rows.length && <UiTableRow><UiTd colSpan={7} className="px-4 py-12 text-center text-slate-500">No invoices to review yet.</UiTd></UiTableRow>}</UiTableBody></UiTable></UiBox></UiBox><MonthEndChecklist /></UiMain>;
}
