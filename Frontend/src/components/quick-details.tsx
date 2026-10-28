"use client";

import { useState, type ReactNode } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import { X } from "lucide-react";

export function QuickDetails({ title, fields, label = "Details", children }: { title: string; fields: Record<string, ReactNode>; label?: ReactNode; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return <><Button type="button" size="small" onClick={() => setOpen(true)} aria-label={`View ${title}`}>{label}</Button>
    <Drawer anchor="right" open={open} onClose={() => setOpen(false)} slotProps={{ paper: { role: "dialog", "aria-modal": true, "aria-label": title, sx: { width: { xs: "100%", sm: 480 }, maxWidth: "100%", p: 3 } } }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", justifyContent: "space-between" }}><Typography variant="h6">{title}</Typography><IconButton aria-label="Close details" onClick={() => setOpen(false)}><X size={20} /></IconButton></Stack><Divider sx={{ my: 2 }} />
      <Box component="dl" sx={{ m: 0 }}>{Object.entries(fields).map(([name, value]) => <Box key={name} sx={{ mb: 2.5 }}><Typography component="dt" variant="caption" color="text.secondary" sx={{ textTransform: "capitalize" }}>{name.replaceAll("_", " ")}</Typography><Typography component="dd" variant="body2" sx={{ m: 0, mt: 0.5, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>{value ?? "—"}</Typography></Box>)}</Box>
      {children}
    </Drawer></>;
}
