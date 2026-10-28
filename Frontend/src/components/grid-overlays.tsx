"use client";

import { useGridApiContext } from "@mui/x-data-grid";
import { EmptyState } from "@/components/empty-state";

export function GridNoRows() { return <EmptyState title="No records yet" description="New records will appear here once they are created." />; }
export function GridNoResults() {
  const api = useGridApiContext();
  return <EmptyState kind="search" onAction={() => api.current.setFilterModel({ items: [], quickFilterValues: [] })} />;
}
