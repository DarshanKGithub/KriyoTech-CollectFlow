"use client";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiH2, UiSection, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Health = {
    database: boolean;
    redis: boolean;
    recent_worker_heartbeat: boolean;
    extraction_counts: Record<string, number>;
    healthy: boolean;
};
export function ExtractionHealth() {
    const [health, setHealth] = useState<Health | null>(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);
    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const response = await apiFetch("/admin/operations/extraction-health");
            if (!response.ok)
                throw new Error("Unable to read extraction health.");
            setHealth(await response.json());
            setError("");
        }
        catch {
            setHealth(null);
            setError("Unable to read extraction health. Check the backend connection.");
        }
        finally {
            setLoading(false);
        }
    }, []);
    useEffect(() => { void refresh(); }, [refresh]);
    return <UiSection className="mt-6 rounded-xl border border-line bg-white p-5"><UiBox className="flex items-center justify-between gap-3"><UiH2 className="font-bold">Invoice processing health</UiH2><UiButton disabled={loading} onClick={() => void refresh()} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">{loading ? "Checking…" : "Refresh health"}</UiButton></UiBox>{error && <UiAlert role="alert" className="mt-3 text-sm text-rose-700">{error}</UiAlert>}{loading && !health && <ContentSkeleton variant="cards" rows={2} label="Loading invoice processing health" />}{health && <><UiBox className="mt-4 flex flex-wrap gap-3">{[["Database", health.database], ["Redis", health.redis], ["Worker + scheduler heartbeat", health.recent_worker_heartbeat]].map(([label, ok]) => <UiSpan key={String(label)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${ok ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>{label}: {ok ? "Healthy" : "Needs attention"}</UiSpan>)}</UiBox><UiText className="mt-3 text-xs text-slate-500">Heartbeat confirms a scheduled task ran in the last three minutes. Start Celery worker and beat if it is missing.</UiText><UiBox className="mt-3 flex flex-wrap gap-4 text-sm">{["QUEUED", "PROCESSING", "FAILED", "COMPLETED"].map(status => <UiSpan key={status}>{status.toLowerCase()}: <UiStrong>{health.extraction_counts[status] || 0}</UiStrong></UiSpan>)}</UiBox></>}</UiSection>;
}
