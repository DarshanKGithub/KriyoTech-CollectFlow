"use client";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { ContentSkeleton } from "@/components/content-skeleton";
import { RecordDataGrid } from "@/components/record-data-grid";
import { UiBox, UiButton, UiH1, UiMain, UiSection, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
export function OperationalPage({ title, description, path }: {
    title: string;
    description: string;
    path: string;
}) {
    const [rows, setRows] = useState<Record<string, unknown>[]>([]);
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(true);
    const load = useCallback(() => {
        setLoading(true);
        apiFetch(path).then(async (response) => {
            if (!response.ok)
                throw new Error(response.status === 401 ? "Sign in to view this workspace data." : "Could not load records.");
            const data = await response.json();
            return Array.isArray(data) ? data : data.results || [];
        }).then(setRows).catch(e => setMessage(e instanceof Error ? e.message : "Could not load records.")).finally(() => setLoading(false));
    }, [path]);
    useEffect(() => { load(); const refresh = () => load(); window.addEventListener("kriyopay:data-changed", refresh); return () => window.removeEventListener("kriyopay:data-changed", refresh); }, [load]);
    const columns = rows[0] ? Object.keys(rows[0]).filter(key => !key.endsWith("_id") && key !== "id").slice(0, 7) : [];
    function display(value: unknown) {
        if (value === null || value === undefined || value === "")
            return "—";
        if (typeof value === "boolean")
            return value ? "Yes" : "No";
        if (typeof value === "object")
            return JSON.stringify(value);
        return String(value).replaceAll("_", " ");
    }
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiBox className="mt-6 flex items-end justify-between"><UiBox><UiH1 className="text-2xl font-bold">{title}</UiH1><UiText className="mt-1 text-sm text-slate-500">{description}</UiText></UiBox><UiButton onClick={load} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Refresh</UiButton></UiBox>{message && <WorkflowFeedback message={message} onRefresh={()=>load()} />}<UiSection className="mt-6 overflow-hidden rounded-xl border border-line bg-white shadow-card">{loading ? <ContentSkeleton variant="table" label="Loading records" /> : rows.length === 0 ? <EmptyState kind={message ? "error" : "empty"} description={message || "No records to show. Add records or import data to get started."} onAction={()=>void load()} actionLabel={message ? "Retry" : "Refresh data"} /> : <UiBox className="overflow-x-auto"><RecordDataGrid rows={rows} columns={columns} format={display} key={path}/></UiBox>}</UiSection></UiMain>;
}
