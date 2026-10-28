"use client";

import { useState, type ReactNode } from "react";
import Box from "@mui/material/Box";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import ToggleButton from "@mui/material/ToggleButton";
import { LayoutList, Table2 } from "lucide-react";
import { RecordDataGrid } from "@/components/record-data-grid";

export function CollectionExplorer({ rows, recordPrefix, onOpen, children }: { rows: Record<string, unknown>[]; recordPrefix: string; onOpen: (id: string) => void; children: ReactNode }) {
  const [view, setView] = useState("cards");
  return <Box sx={{ minWidth: 0 }}>
    <ToggleButtonGroup value={view} exclusive size="small" aria-label="List presentation" onChange={(_, next: string | null) => { if (next) setView(next); }} sx={{ mb: 2 }}>
      <ToggleButton value="cards"><LayoutList size={16} style={{ marginRight: 6 }} />Workflow cards</ToggleButton><ToggleButton value="table"><Table2 size={16} style={{ marginRight: 6 }} />Searchable table</ToggleButton>
    </ToggleButtonGroup>
    {view === "table" && <RecordDataGrid rows={rows} columns={rows[0] ? Object.keys(rows[0]).filter(field => field !== "id") : []} onOpenRecord={id => {
      onOpen(id); setView("cards");
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const record = document.getElementById(`${recordPrefix}${id}`);
        record?.scrollIntoView({ block: "start", behavior: "auto" }); record?.focus();
      }));
    }} />}
    <Box sx={{ display: view === "cards" ? "block" : "none", "& > article": { mb: 2 } }}>{children}</Box>
  </Box>;
}
