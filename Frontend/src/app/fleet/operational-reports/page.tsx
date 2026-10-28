"use client";
import { DateField } from "@/components/date-field";
import { UiAlert, UiButton, UiH1, UiHeader, UiLabel, UiMain, UiSection, UiSelect, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
type Row = Record<string, string | number | null>;
const reports = [{ id: "trip-costs", label: "Trip costs and fuel use" }, { id: "salary-outstanding", label: "Outstanding driver salaries" }, { id: "invoice-exceptions", label: "Invoice exceptions" }, { id: "payment-status", label: "Payment status" }];
export default function FleetOperationalReportsPage() {
    const [report, setReport] = useState("trip-costs");
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const [rows, setRows] = useState<Row[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    function url(exportCsv = false) {
        const params = new URLSearchParams();
        if (from)
            params.set("from", from);
        if (to)
            params.set("to", to);
        if (exportCsv)
            params.set("export", "csv");
        return `/fleet/operational-reports/${report}?${params}`;
    }
    async function run() {
        if(from === "INVALID" || to === "INVALID" || (from && to && from > to)){setMessage("Choose a valid date range before running the report.");return;}
        setBusy(true);
        setMessage("");
        try {
            const response = await apiFetch(url());
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "Could not run report.");
            setRows(data.rows || []);
            setMessage(`${data.count} row(s) found.`);
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not run report.");
        }
        finally {
            setBusy(false);
        }
    }
    async function exportCsv() {
        if(from === "INVALID" || to === "INVALID" || (from && to && from > to)){setMessage("Choose a valid date range before exporting.");return;}
        setBusy(true);
        try {
            const response = await apiFetch(url(true));
            if (!response.ok)
                throw new Error("Report export failed.");
            const blob = await response.blob();
            const href = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = href;
            anchor.download = `kriyopay-${report}.csv`;
            anchor.click();
            URL.revokeObjectURL(href);
            setMessage("CSV downloaded.");
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Report export failed.");
        }
        finally {
            setBusy(false);
        }
    }
    const pagination = useListPagination(rows, report + from + to);
    return <UiMain className="w-full min-w-0 space-y-5 px-5 py-8"><UiHeader><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet · Finance</UiText><UiH1 className="mt-1 text-2xl font-bold">Operational reports</UiH1><UiText className="mt-1 text-sm text-slate-500">Review and export trip costs, salary balances, invoice exceptions, and payments for a date range.</UiText></UiHeader><UiSection className="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-white p-4"><UiLabel className="text-xs font-semibold">Report<UiSelect value={report} onChange={e => setReport(e.target.value)} className="mt-1 block rounded-lg border border-line px-3 py-2">{reports.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold">From<DateField value={from} onChange={setFrom} className="mt-1 block rounded-lg border border-line px-3 py-2"/></UiLabel><UiLabel className="text-xs font-semibold">To<DateField value={to} onChange={setTo} className="mt-1 block rounded-lg border border-line px-3 py-2"/></UiLabel><UiButton disabled={busy} onClick={() => void run()} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">{busy ? "Working…" : "Run report"}</UiButton><UiButton disabled={busy} onClick={() => void exportCsv()} className="rounded-lg border border-line px-4 py-2 text-sm font-semibold">Download CSV</UiButton></UiSection>{message && <UiAlert role="status" className="text-sm text-slate-600">{message}</UiAlert>}<UiSection className="overflow-x-auto rounded-xl border border-line bg-white"><UiTable className="w-full min-w-[650px] text-left text-sm"><UiTableHead className="bg-slate-50"><UiTableRow>{(rows[0] ? Object.keys(rows[0]) : []).map(key => <UiTh key={key} className="px-4 py-3 text-xs font-semibold capitalize text-slate-500">{key.replaceAll("_", " ")}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{pagination.rows.map((row, index) => <UiTableRow key={index} className="border-t border-line">{Object.values(row).map((value, column) => <UiTd key={column} className="px-4 py-3">{String(value ?? "—")}</UiTd>)}</UiTableRow>)}</UiTableBody></UiTable>{rows.length === 0 && <UiText className="p-8 text-center text-sm text-slate-500">Choose a report and date range, then run it.</UiText>}{pagination.controls}</UiSection></UiMain>;
}
