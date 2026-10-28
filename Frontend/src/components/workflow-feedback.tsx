"use client";

import { useEffect, useRef } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import { showNotice } from "@/components/product-dialogs";

const confirmedSuccess = /^(Saved successfully\.|Payment recorded and allocated|Invoice fields and line items saved|Expense and receipt submitted|Vendor created\.|Tally CSV created and downloaded|Salary entry saved|Driver advance recorded|Effective-dated driver pay policy saved|Policy period closed|Salary draft updated|Salary payment recorded|Trip .*recorded\.|Trip marked complete\.|Trip sent for review\.|Trip approved\.|Connection saved\.|Sync started\.|.* offline update\(s\) synced\.)/;

export function WorkflowFeedback({ message, onRefresh, severity }: { message: string; onRefresh?: () => void | Promise<unknown>; severity?: "success" | "error" | "warning" | "info" }) {
  const last = useRef("");
  const success = severity === "success" || confirmedSuccess.test(message);
  useEffect(() => {
    if (message && success && last.current !== message) showNotice(message, "success");
    last.current = message;
  }, [message, success]);
  if (!message) return null;
  return <Alert sx={{ my: 2, whiteSpace: "pre-wrap" }} severity={severity || (success ? "success" : /fail|could not|cannot|unable|error|unavailable|invalid/i.test(message) ? "error" : "info")}
    action={!success && onRefresh ? <Button color="inherit" size="small" onClick={() => { void Promise.resolve(onRefresh()).catch(() => showNotice("Could not refresh. Check your connection and try again.")); }}>Refresh data</Button> : undefined}>{message}</Alert>;
}
