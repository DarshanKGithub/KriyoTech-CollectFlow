"use client";

import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import type { GridDensity } from "@mui/x-data-grid";

export function GridDensityControl({ value, onChange }: { value: GridDensity; onChange: (value: GridDensity) => void }) {
  return <Box sx={{ display: "flex", justifyContent: "flex-end", p: 1 }}>
    <TextField select label="Row spacing" value={value} onChange={event => onChange(event.target.value as GridDensity)} size="small" slotProps={{ select: { native: true }, htmlInput: { "aria-label": "Row spacing" } }} sx={{ minWidth: 145 }}>
      <option value="compact">Compact</option><option value="standard">Standard</option><option value="comfortable">Comfortable</option>
    </TextField>
  </Box>;
}
