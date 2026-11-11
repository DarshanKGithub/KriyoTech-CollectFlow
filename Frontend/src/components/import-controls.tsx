"use client";

import { UiBox, UiInput, UiLabel, UiLink, UiSpan, UiSpinner, UiStrong } from "@/components/product-ui";
import { ChangeEvent, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Download, Upload } from "lucide-react";
import { ProcessingStatus } from "@/components/processing-status";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { showNotice } from "@/components/product-dialogs";

type ImportResult = {
    preview: boolean;
    accepted_rows: number;
    rejected_rows: number;
    errors: { row: number; message: string }[];
    correction_rows: Record<string, string | number | null>[];
};

function csvCell(value: string | number | null) {
    const text = value == null ? "" : String(value);
    return `"${text.replaceAll('"', '""')}"`;
}

function downloadCorrectionRows(rows: ImportResult["correction_rows"]) {
    if (!rows.length)
        return;
    const headers = [...new Set(rows.flatMap(row => Object.keys(row)))];
    const contents = [headers, ...rows.map(row => headers.map(header => row[header] ?? ""))]
        .map(row => row.map(csvCell).join(","))
        .join("\r\n");
    const url = URL.createObjectURL(new Blob([`\uFEFF${contents}`], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "import-corrections.csv";
    link.click();
    URL.revokeObjectURL(url);
}

export function ImportControls({ kind }: {
    kind: "purchase-orders" | "grns";
}) {
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [outcome, setOutcome] = useState<"success" | "warning" | "error">("success");
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [result, setResult] = useState<ImportResult | null>(null);
    const template = kind === "purchase-orders" ? "/templates/purchase-orders.csv" : "/templates/grns.csv";

    async function submit(file: File, preview: boolean) {
        setBusy(true);
        setMessage("");
        const form = new FormData();
        form.append("file", file);
        if (preview)
            form.append("preview", "true");
        try {
            const response = await apiFetch(`/${kind}/import`, { method: "POST", body: form });
            const data = await response.json() as ImportResult & { error?: { message?: string } };
            if (!response.ok && response.status !== 207)
                throw new Error(data.error?.message || "Import failed");
            setResult(data);
            setOutcome(data.rejected_rows ? "warning" : "success");
            if (preview) {
                setMessage(`Preview complete: ${data.accepted_rows} rows ready to import · ${data.rejected_rows} need correction. Nothing has been saved yet.`);
            } else {
                showNotice(`${data.accepted_rows} rows imported; ${data.rejected_rows} rejected.`, data.rejected_rows ? "warning" : "success");
                setMessage(`${data.accepted_rows} rows imported · ${data.rejected_rows} rejected${data.errors.length ? `: ${data.errors.slice(0, 2).map(error => `row ${error.row}: ${error.message}`).join("; ")}` : ""}`);
                if (!data.rejected_rows)
                    setSelectedFile(null);
                window.dispatchEvent(new Event("kriyopay:data-changed"));
            }
        } catch (error) {
            setOutcome("error");
            setMessage(error instanceof Error ? error.message : "Import failed");
        } finally {
            setBusy(false);
        }
    }

    async function previewUpload(event: ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file)
            return;
        setSelectedFile(file);
        setResult(null);
        await submit(file, true);
    }

    async function commitImport() {
        if (selectedFile)
            await submit(selectedFile, false);
    }

    return <UiBox className="mt-5 flex w-full min-w-0 flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white p-4 shadow-card">
        <UiBox>
            <UiStrong className="block text-xs">Import from CSV</UiStrong>
            <UiSpan className="text-[11px] text-slate-500">Preview and validate up to 1,000 rows before saving. Invalid rows can be downloaded for correction.</UiSpan>
            {busy && <ProcessingStatus status="IMPORTING" label={result?.preview ? "Importing validated rows" : "Validating CSV without saving"} />}
            {message && <WorkflowFeedback message={message} severity={outcome} />}
            {result && <>
                <UiBox className="mt-2 text-[11px] text-slate-600">
                    {result.preview ? "Preview" : "Import result"}: {result.accepted_rows} valid · {result.rejected_rows} rejected.
                    {result.rejected_rows > 0 && <UiSpan className="ml-1">{result.errors.slice(0, 3).map(error => `Row ${error.row}: ${error.message}`).join(" · ")}</UiSpan>}
                </UiBox>
                {result.correction_rows.length > 0 && <button type="button" onClick={() => downloadCorrectionRows(result.correction_rows)} className="mt-2 flex items-center gap-1 text-[11px] font-semibold text-forest">
                    <Download size={13} />Download rejected rows with errors
                </button>}
            </>}
        </UiBox>
        <UiBox className="flex flex-wrap gap-2">
            <UiLink href={template} download className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[11px] font-semibold text-slate-600"><Download size={14} />Download template</UiLink>
            <UiLabel className="flex cursor-pointer items-center gap-2 rounded-lg bg-forest px-3 py-2 text-[11px] font-semibold text-white">
                {busy ? <UiSpinner className="animate-spin" size={14} /> : <Upload size={14} />}Preview CSV
                <UiInput type="file" accept="text/csv,.csv" className="hidden" disabled={busy} onChange={event => void previewUpload(event)} />
            </UiLabel>
            {result?.preview && selectedFile && <button type="button" disabled={busy || result.accepted_rows === 0} onClick={() => void commitImport()} className="rounded-lg border border-forest px-3 py-2 text-[11px] font-semibold text-forest disabled:opacity-50">
                {busy ? "Importing…" : `Import ${result.accepted_rows} valid rows`}
            </button>}
        </UiBox>
    </UiBox>;
}
