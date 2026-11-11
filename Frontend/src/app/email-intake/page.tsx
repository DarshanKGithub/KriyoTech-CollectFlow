"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle } from "@mui/material";
import { ArrowRight, Inbox, Mail, RefreshCw } from "lucide-react";
import { AppLink } from "@/components/product-ui";
import { ContentSkeleton } from "@/components/content-skeleton";
import { useListPagination } from "@/components/list-pagination";
import { requestConfirmation } from "@/components/product-dialogs";
import { LiveData } from "@/components/live-data";
import { apiFetch } from "@/lib/api";

type Connection = { connected: boolean; email?: string };
type ImportRun = {
  id: string;
  provider: string;
  sender: string;
  subject: string;
  status: string;
  error: string;
  attachments: { filename: string; status: string; reason?: string; invoice_id?: string }[];
  created_at: string;
};

const statusLabels: Record<string, string> = {
  RECEIVED: "Received", PROCESSING: "Importing", PROCESSED: "Imported",
  PARTIAL: "Needs review", FAILED: "Failed", QUARANTINED: "Quarantined",
};
const importDate = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" });

async function readResponse<T>(response: Response, fallback: string): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof body?.error === "string" ? body.error : body?.error?.message || body?.detail;
    throw new Error(typeof detail === "string" ? detail : fallback);
  }
  return body as T;
}

export default function EmailIntakePage() {
  const [connection, setConnection] = useState<Connection>();
  const [runs, setRuns] = useState<ImportRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"connect" | "sync" | "disconnect">();
  const [selected, setSelected] = useState<ImportRun>();
  const [query, setQuery] = useState("");
  const requestVersion = useRef(0);
  const actionInFlight = useRef(false);

  const load = useCallback(async (silent = false, fresh = false) => {
    const version = ++requestVersion.current;
    const options = fresh ? { cache: "no-store" as const } : undefined;
    const [mailbox, history] = await Promise.allSettled([
      apiFetch("/google/gmail", options).then(response => readResponse<Connection>(response, "Could not check the Gmail connection.")),
      apiFetch("/email-ingestion/logs", options).then(response => readResponse<ImportRun[]>(response, "Could not load recent imports.")),
    ]);
    if (version !== requestVersion.current) return;
    if (mailbox.status === "fulfilled") {
      setConnection(mailbox.value);
      setConnectionError("");
    } else {
      setConnectionError(mailbox.reason instanceof Error ? mailbox.reason.message : "Could not check the Gmail connection.");
    }
    if (history.status === "fulfilled") {
      setRuns(history.value);
      setHistoryError("");
    } else {
      setHistoryError(history.reason instanceof Error ? history.reason.message : "Could not load recent imports.");
    }
    setLoading(false);
    if (silent && (mailbox.status === "rejected" || history.status === "rejected")) throw new Error("Could not refresh email intake.");
  }, []);

  useEffect(() => {
    void load();
    return () => { requestVersion.current += 1; };
  }, [load]);

  async function changeConnection(action: "connect" | "sync" | "disconnect") {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(action);
    setActionError("");
    setNotice("");
    let redirecting = false;
    try {
      if (action === "disconnect" && !await requestConfirmation("Disconnect this Gmail inbox from the workspace? Previously imported invoices will stay in KriyoPay.")) return;
      if (action === "connect") {
        const response = await apiFetch("/google/gmail", { method: "POST", body: "{}" });
        const result = await readResponse<{ authorization_url: string }>(response, "Could not start Gmail authorization.");
        window.location.assign(result.authorization_url);
        redirecting = true;
        return;
      }
      if (action === "disconnect") {
        const response = await apiFetch("/google/gmail", { method: "DELETE", body: "{}" });
        await readResponse(response, "Could not disconnect Gmail.");
        setConnection({ connected: false });
        setNotice("Gmail disconnected.");
      } else {
        const response = await apiFetch("/google/gmail/sync", { method: "POST", body: "{}" });
        const result = await readResponse<{ messages_checked: number; attachments_imported: number; attachments_quarantined: number }>(response, "Could not sync Gmail.");
        setNotice(`Checked ${result.messages_checked} messages. Imported ${result.attachments_imported} attachments. ${result.attachments_quarantined} quarantined.`);
      }
      await load(false, true);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not update the Gmail connection.");
      if (action !== "connect") await load(false, true);
    } finally {
      if (!redirecting) {
        actionInFlight.current = false;
        setBusy(undefined);
      }
    }
  }

  const search = query.trim().toLowerCase();
  const filtered = runs.filter(run => [run.subject, run.sender, ...run.attachments.map(item => item.filename)].some(value => value.toLowerCase().includes(search)));
  const pagination = useListPagination(filtered, search, "Recent email imports pages");

  return <main className="w-full min-w-0 space-y-4 px-4 py-6 sm:px-6 lg:px-8">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-bold tracking-tight text-ink">Email intake</h1><p className="mt-1 text-sm text-slate-600">Import supplier invoices from your workspace’s Gmail inbox.</p></div>
      <AppLink href="/invoices" className="inline-flex items-center gap-1 text-sm font-semibold text-forest">Open invoices <ArrowRight size={15} /></AppLink>
    </header>

    <section aria-labelledby="gmail-title" className="rounded-xl border border-line bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-800"><Mail size={20} aria-hidden /></span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><h2 id="gmail-title" className="font-bold text-ink">Gmail inbox</h2>
              {connection && !connectionError && <Chip size="small" color={connection.connected ? "success" : "default"} variant="outlined" label={connection.connected ? "Connected" : "Not connected"} />}
            </div>
            <p className="mt-1 break-words text-sm text-slate-600">{connection?.connected ? connection.email : "Connect the Gmail inbox where suppliers send your invoices."}</p>
            <p className="mt-1 text-xs text-slate-600">Read-only access. Sync checks recent messages with attachments.</p>
          </div>
        </div>
        {!connectionError && connection && (connection.connected ? <div className="flex flex-wrap gap-2">
          <Button variant="contained" disabled={Boolean(busy)} startIcon={<RefreshCw size={15} />} onClick={() => void changeConnection("sync")}>{busy === "sync" ? "Syncing…" : "Sync recent mail"}</Button>
          <Button variant="outlined" color="inherit" disabled={Boolean(busy)} onClick={() => void changeConnection("disconnect")}>{busy === "disconnect" ? "Disconnecting…" : "Disconnect"}</Button>
        </div> : <Button variant="contained" disabled={Boolean(busy)} onClick={() => void changeConnection("connect")}>{busy === "connect" ? "Connecting…" : "Connect Gmail"}</Button>)}
        {loading && <span role="status" className="text-sm text-slate-600">Checking Gmail…</span>}
      </div>
      {connectionError && <Alert severity="warning" sx={{ mt: 2 }} action={<Button color="inherit" size="small" onClick={() => void load(false, true)}>Retry</Button>}>{connectionError}</Alert>}
      {actionError && <Alert severity="error" sx={{ mt: 2 }}>{actionError}</Alert>}
      {notice && <Alert severity="success" sx={{ mt: 2 }} onClose={() => setNotice("")}>{notice}</Alert>}
    </section>

    <section aria-labelledby="imports-title" className="overflow-hidden rounded-xl border border-line bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <div><h2 id="imports-title" className="font-bold text-ink">Recent imports</h2><p className="text-sm text-slate-600">See what was imported and what needs review.</p></div>
        <input type="search" aria-label="Search recent imports" placeholder="Search sender, subject, or file" value={query} onChange={event => setQuery(event.target.value)} className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm sm:w-64" />
      </div>
      {historyError && <Alert severity="error" sx={{ m: 2 }} action={<Button color="inherit" size="small" onClick={() => void load(false, true)}>Retry</Button>}>{historyError}</Alert>}
      {loading ? <ContentSkeleton variant="table" label="Loading recent imports" />
        : pagination.rows.length ? <ul className="divide-y divide-slate-200">
          {pagination.rows.map(run => <li key={run.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
            <div className="min-w-0 flex-1 basis-52">
              <p className="break-words text-sm font-semibold text-ink">{run.subject || "(No subject)"}</p>
              <p className="break-words text-xs text-slate-600">{run.sender || "Unknown sender"} · {run.provider === "GMAIL" ? "Gmail" : "Email intake"}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2 sm:gap-4">
              <span className="text-xs text-slate-600">{importDate.format(new Date(run.created_at))}</span>
              <Chip size="small" variant="outlined" color={run.status === "PROCESSED" ? "success" : ["FAILED", "QUARANTINED", "PARTIAL"].includes(run.status) ? "warning" : "default"} label={statusLabels[run.status] || run.status} />
              <Button size="small" onClick={() => setSelected(run)} aria-label={`View import details for ${run.subject || "email without subject"}`}>Details</Button>
            </div>
          </li>)}
        </ul> : !historyError && <div className="grid justify-items-center gap-2 p-8 text-center">
          <Inbox size={24} className="text-slate-500" aria-hidden />
          <p className="font-semibold text-ink">{search ? "No matching imports" : "No email imports yet"}</p>
          <p className="text-sm text-slate-600">{search ? "Try another sender, subject, or filename." : connection?.connected ? "Use Sync recent mail to check your inbox." : "Imports will appear here after an inbox is connected and synced."}</p>
        </div>}
      {filtered.length > 10 && pagination.controls}
    </section>
    <LiveData compact onRefresh={() => load(true)} paused={loading || Boolean(busy || selected)} interval={30000} />
    <Dialog open={Boolean(selected)} onClose={() => setSelected(undefined)} fullWidth maxWidth="sm" aria-labelledby="import-details-title">
      <DialogTitle id="import-details-title">{selected?.subject || "Import details"}</DialogTitle>
      <DialogContent dividers>
        <p className="mb-3 text-sm text-slate-600">{selected?.sender || "Unknown sender"}</p>
        {selected?.error && <Alert severity="warning" sx={{ mb: 2 }}>{selected.error}</Alert>}
        {selected?.attachments.length ? <ul className="divide-y divide-slate-200">
          {selected.attachments.map((item, index) => <li key={index} className="py-2">
            <p className="break-words text-sm font-semibold">{item.filename}</p>
            <p className="text-xs text-slate-600">{item.invoice_id ? "Invoice created" : statusLabels[item.status] || item.status}{item.reason && ` · ${item.reason}`}</p>
          </li>)}
        </ul> : <p className="text-sm text-slate-600">No attachments recorded.</p>}
      </DialogContent>
      <DialogActions><Button onClick={() => setSelected(undefined)}>Close</Button></DialogActions>
    </Dialog>
  </main>;
}
