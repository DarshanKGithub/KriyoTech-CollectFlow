"use client";

import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import { FolderOpen, SearchX, CircleAlert } from "lucide-react";

export function EmptyState({ kind = "empty", title, description, actionLabel, onAction }: {
  kind?: "empty" | "search" | "error"; title?: string; description?: string; actionLabel?: string; onAction?: () => void;
}) {
  const Icon = kind === "error" ? CircleAlert : kind === "search" ? SearchX : FolderOpen;
  return <Stack role="status" spacing={1.5} sx={{ alignItems: "center", justifyContent: "center", p: 4, minHeight: 200, textAlign: "center", width: "100%", height: "100%" }}>
    <Icon size={30} color={kind === "error" ? "#b42318" : "#17634f"} aria-hidden="true" />
    <Typography sx={{ fontWeight: 600 }}>{title || (kind === "error" ? "Could not load records" : kind === "search" ? "No matching results" : "No records yet")}</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 420 }}>{description || (kind === "error" ? "Check your connection and try again." : kind === "search" ? "Try a different search or clear your filters." : "Records will appear here once you add them.")}</Typography>
    {onAction && <Button variant="outlined" onClick={onAction}>{actionLabel || (kind === "error" ? "Retry" : kind === "search" ? "Clear filters" : "Refresh")}</Button>}
  </Stack>;
}
