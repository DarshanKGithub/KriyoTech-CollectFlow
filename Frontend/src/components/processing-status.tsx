"use client";

import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";

export function ProcessingStatus({ status, label }: { status: string; label?: string }) {
  const failed = /FAILED|ERROR/.test(status);
  const running = /^(QUEUED|PENDING|PROCESSING|EXTRACTING|RUNNING|IMPORTING|EXPORTING|SYNCING|UPLOADING)$/.test(status);
  const done = /^(COMPLETED|SUCCESS|SUCCEEDED|EXPORTED)$/.test(status);
  return <Stack spacing={1} sx={{ minWidth: 130, width: "100%" }} role="status" aria-label={label || status.replaceAll("_", " ")}>
    <Chip size="small" color={failed ? "error" : running ? "info" : done ? "success" : "default"} label={label || status.replaceAll("_", " ").toLowerCase()} sx={{ alignSelf: "flex-start" }} />
    {running && <><LinearProgress aria-label={label || "Processing"} /><Typography variant="caption" color="text.secondary">{status === "QUEUED" || status === "PENDING" ? "Waiting for a worker" : "In progress"}</Typography></>}
  </Stack>;
}
