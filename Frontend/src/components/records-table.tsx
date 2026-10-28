"use client";
import { RecordDataGrid } from "@/components/record-data-grid";
import { EmptyState } from "@/components/empty-state";
import { UiBox } from "@/components/product-ui";
export function RecordsTable({ rows, resetKey = "", error, onRetry }: {
    rows: Record<string, unknown>[];
    resetKey?: string;
    error?: string;
    onRetry?: () => void;
}) {
    const columns = rows[0] ? Object.keys(rows[0]).filter(key => key !== "id").slice(0, 7) : [];
    return <>{rows.length ? <UiBox className="overflow-x-auto"><RecordDataGrid rows={rows} columns={columns} key={resetKey}/></UiBox> : <EmptyState kind={error ? "error" : "empty"} description={error || "New records will appear here after you complete the form above or import data."} onAction={onRetry} />}</>;
}
