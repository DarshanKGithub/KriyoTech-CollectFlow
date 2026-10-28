"use client";
import { UiBox, UiInput, UiLabel, UiLink, UiSpan, UiSpinner, UiStrong } from "@/components/product-ui";
import { ChangeEvent, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Download, Upload } from "lucide-react";
import { ProcessingStatus } from "@/components/processing-status";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { showNotice } from "@/components/product-dialogs";
export function ImportControls({ kind }: {
    kind: "purchase-orders" | "grns";
}) {
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [outcome, setOutcome] = useState<"success" | "warning" | "error">("success");
    const template = kind === "purchase-orders" ? "/templates/purchase-orders.csv" : "/templates/grns.csv";
    async function upload(event: ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        if (!file)
            return;
        setBusy(true);
        setMessage("");
        const form = new FormData();
        form.append("file", file);
        try {
            const response = await apiFetch(`/${kind}/import`, { method: "POST", body: form });
            const data = await response.json();
            if (!response.ok && response.status !== 207)
                throw new Error(data.error?.message || "Import failed");
            setOutcome(data.rejected_rows ? "warning" : "success");
            showNotice(`${data.accepted_rows} rows imported; ${data.rejected_rows} rejected.`, data.rejected_rows ? "warning" : "success");
            setMessage(`${data.accepted_rows} rows imported · ${data.rejected_rows} rejected${data.errors?.length ? `: ${data.errors.slice(0, 2).map((x: {
                row: number;
                message: string;
            }) => `row ${x.row}: ${x.message}`).join("; ")}` : ""}`);
            window.dispatchEvent(new Event("kriyopay:data-changed"));
        }
        catch (error) {
            setOutcome("error");
            setMessage(error instanceof Error ? error.message : "Import failed");
        }
        finally {
            setBusy(false);
            event.target.value = "";
        }
    }
    return <UiBox className="mt-5 flex w-full min-w-0 flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white p-4 shadow-card"><UiBox><UiStrong className="block text-xs">Import from CSV</UiStrong><UiSpan className="text-[11px] text-slate-500">Use the template columns to validate rows on upload.</UiSpan>{busy && <ProcessingStatus status="IMPORTING" label="Importing and validating rows"/>}{message && <WorkflowFeedback message={message} severity={outcome}/>}</UiBox><UiBox className="flex gap-2"><UiLink href={template} download className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[11px] font-semibold text-slate-600"><Download size={14}/>Download template</UiLink><UiLabel className="flex cursor-pointer items-center gap-2 rounded-lg bg-forest px-3 py-2 text-[11px] font-semibold text-white">{busy ? <UiSpinner className="animate-spin" size={14}/> : <Upload size={14}/>}Import CSV<UiInput type="file" accept="text/csv,.csv" className="hidden" disabled={busy} onChange={upload}/></UiLabel></UiBox></UiBox>;
}
