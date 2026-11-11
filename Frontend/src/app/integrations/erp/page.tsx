"use client";
import { ProcessingStatus } from "@/components/processing-status";
import { showNotice } from "@/components/product-dialogs";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { PageSkeleton } from "@/components/content-skeleton";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Button from "@mui/material/Button";
import { ArrowRight, Landmark, ReceiptIndianRupee } from "lucide-react";
import { UiAlert, UiBox, UiButton, UiDetails, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiLink, UiMain, UiModal, UiSection, UiSelect, UiSpan, UiStrong, UiSummary, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTextarea, UiTh } from "@/components/product-ui";
import Pagination from "@mui/material/Pagination";
import { LiveData } from "@/components/live-data";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
type Provider = {
    name: string;
    mode: string;
    config_fields: Record<string, string>;
    secret_fields: Record<string, string>;
    resources: string[];
    direct_write_resources: string[];
    note: string;
    docs: string;
};
type Connection = {
    id: string;
    provider: string;
    name: string;
    config: Record<string, unknown>;
    enabled: boolean;
    has_credentials: boolean;
    tested_at: string | null;
    last_error: string;
};
type Run = {
    id: string;
    connection_id: string;
    resource: string;
    status: string;
    record_count: number;
    error: string;
    page: number;
    has_more: boolean;
};
type SyncRecord = {
    id: string;
    connection_id: string;
    resource: string;
    direction: string;
    status: string;
    local_id: string | null;
    external_id: string;
    error: string;
    payload?: Record<string, unknown>;
    suggested_import?: Record<string, unknown>;
};
type Local = {
    id: string;
    name?: string;
    number?: string;
    invoice_number?: string;
    reference_number?: string;
    supplier_name?: string;
    amount?: string;
};
const label = (value: string) => value.replaceAll("_", " ");
const primaryProviders = ["TALLY", "ZOHO_BOOKS"];
const providerDescriptions: Record<string, string> = {
    TALLY: "Export approved supplier invoices and payments for your accountant.",
    ZOHO_BOOKS: "Sync supplier bills, purchase orders, and payment records.",
    ERPNEXT: "Connect suppliers, purchase orders, receipts, and accounting records.",
    ZOHO_INVENTORY: "Sync goods receipts for purchase order matching.",
    DYNAMICS_FINANCE: "Connect a Finance legal entity with administrator-provided mappings.",
};
const input = "mt-1 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal";
export default function ERPIntegrationsPage() {
    const [initialLoading, setInitialLoading] = useState(true);
    const [workspaceTab,setWorkspaceTab] = useState(0);
    const [catalog, setCatalog] = useState<Record<string, Provider>>({});
    const [connections, setConnections] = useState<Connection[]>([]);
    const [runs, setRuns] = useState<Run[]>([]);
    const [records, setRecords] = useState<SyncRecord[]>([]);
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState(false);
    const [encryption, setEncryption] = useState(true);
    const [provider, setProvider] = useState("");
    const [editing, setEditing] = useState<Connection | null>(null);
    const [selected, setSelected] = useState("");
    const [resource, setResource] = useState("suppliers");
    const [recordPage, setRecordPage] = useState(1);
    const [recordPages, setRecordPages] = useState(1);
    const [detail, setDetail] = useState<SyncRecord | null>(null);
    const [review, setReview] = useState("");
    const [confirmSend, setConfirmSend] = useState(false);
    const [locals, setLocals] = useState<Local[]>([]);
    const [localId, setLocalId] = useState("");
    const [localSearch, setLocalSearch] = useState("");
    const [localPage, setLocalPage] = useState(1);
    const [localPages, setLocalPages] = useState(1);
    const current = connections.find(connection => connection.id === selected);
    const loadSequence = useRef(0);
    const load = useCallback(async (silent = false) => {
        const sequence = ++loadSequence.current;
        try {
            const [a, b, c] = await Promise.all([apiFetch("/erp/connections"), apiFetch("/erp/runs"), apiFetch(`/erp/records?page=${recordPage}${selected ? `&connection_id=${selected}` : ""}`)]);
            if (sequence !== loadSequence.current)
                return;
            if (!a.ok) {
                const body = await a.json();
                throw new Error(typeof body.detail === "string" ? body.detail : body.error || "ERP integrations are unavailable for this account or plan.");
            }
            const body = await a.json();
            setCatalog(body.catalog);
            setConnections(body.connections);
            setEncryption(body.encryption_configured);
            if (!b.ok || !c.ok)
                throw new Error("Some ERP sync data could not refresh.");
            if (b.ok)
                setRuns(await b.json());
            if (c.ok) {
                const data = await c.json();
                if (sequence !== loadSequence.current)
                    return;
                setRecords(data.results);
                setRecordPages(data.pages);
                if (data.page !== recordPage)
                    setRecordPage(data.page);
            }
        }
        catch (error) {
            if (sequence !== loadSequence.current)
                return;
            if (silent)
                throw error;
            setNotice(error instanceof Error ? error.message : "Unable to load ERP integrations.");
        }
    }, [recordPage, selected]);
    useEffect(() => { void load().finally(() => setInitialLoading(false)); }, [load]);
    useEffect(() => {
        let active = true;
        setLocalId("");
        setLocals([]);
        apiFetch(`/erp/local-records?resource=${resource}&q=${encodeURIComponent(localSearch)}&page=${localPage}`).then(async (response) => { if (response.ok && active) {
            const body = await response.json();
            setLocals(body.results);
            setLocalPages(body.pages);
        } }).catch(() => { });
        return () => { active = false; };
    }, [resource, localSearch, localPage]);
    async function action(path: string, payload: unknown, success: string) {
        setBusy(true);
        setNotice("");
        try {
            const response = await apiFetch(path, { method: "POST", body: JSON.stringify(payload) });
            const body = await response.json();
            if (!response.ok)
                throw new Error(body.error || body.detail || "Operation failed.");
            showNotice(body.message || success, "success");
            setNotice(body.message || success);
            await load();
            return body;
        }
        catch (error) {
            setNotice(error instanceof Error ? error.message : "Operation failed.");
            return null;
        }
        finally {
            setBusy(false);
        }
    }
    async function disconnect(connection: Connection) {
        setBusy(true);
        setNotice("");
        try {
            const response = await apiFetch(`/erp/connections/${connection.id}`, { method: "DELETE" });
            const body = await response.json();
            if (!response.ok)
                throw new Error(body.error || "Could not disconnect.");
            setNotice("Connection disconnected and saved credentials removed.");
            await load();
        }
        catch (error) {
            setNotice(error instanceof Error ? error.message : "Could not disconnect.");
        }
        finally {
            setBusy(false);
        }
    }
    async function save(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setBusy(true);
        setNotice("");
        try {
            const config: Record<string, unknown> = { sync_interval_minutes: Number(form.get("sync_interval_minutes") || 0) };
            const credentials: Record<string, string> = {};
            for (const key of Object.keys(catalog[provider].config_fields))
                config[key] = String(form.get(`config:${key}`) || "").trim();
            for (const key of Object.keys(catalog[provider].secret_fields))
                credentials[key] = String(form.get(`secret:${key}`) || "");
            const advanced = JSON.parse(String(form.get("advanced") || "{}"));
            if (!advanced || Array.isArray(advanced) || typeof advanced !== "object")
                throw new Error("Advanced settings must be a JSON object.");
            const response = await apiFetch(`/erp/connections${editing ? `/${editing.id}` : ""}`, { method: editing ? "PATCH" : "POST", body: JSON.stringify({ name: form.get("name"), provider, config: { ...advanced, ...config }, credentials }) });
            const body = await response.json();
            if (!response.ok)
                throw new Error(body.error || body.detail || "Could not save connection.");
            setSelected(body.id);
            setProvider("");
            setEditing(null);
            setNotice("Connection saved. Test it before importing or sending records.");
            await load();
        }
        catch (error) {
            setNotice(error instanceof Error ? error.message : "Invalid settings.");
        }
        finally {
            setBusy(false);
        }
    }
    async function openRecord(record: SyncRecord) {
        setBusy(true);
        try {
            const response = await apiFetch(`/erp/records/${record.id}`);
            const body = await response.json();
            if (!response.ok)
                throw new Error(body.error || "Unable to load record.");
            setDetail(body);
            setReview(JSON.stringify(body.suggested_import || {}, null, 2));
            setConfirmSend(false);
        }
        catch (error) {
            setNotice(error instanceof Error ? error.message : "Unable to load record.");
        }
        finally {
            setBusy(false);
        }
    }
    async function download(format = "json") {
        if (!detail)
            return;
        setBusy(true);
        try {
            const response = await apiFetch(`/erp/records/${detail.id}/download?format=${format}`);
            if (!response.ok) {
                const body = await response.json();
                throw new Error(body.error || "Download failed.");
            }
            const url = URL.createObjectURL(await response.blob());
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = `kriyopay-${detail.resource}-${detail.id}.${format}`;
            anchor.click();
            window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
        catch (error) {
            setNotice(error instanceof Error ? error.message : "Download failed.");
        }
        finally {
            setBusy(false);
        }
    }
    const detailConnection = connections.find(row => row.id === detail?.connection_id);
    const direct = detailConnection && detail && catalog[detailConnection.provider]?.direct_write_resources.includes(detail.resource) && !(detail.payload?.target as Record<string, unknown> | undefined)?.mapping_required;
    if (initialLoading) return <PageSkeleton variant="cards" label="Loading ERP connections and sync history" />;
    return <UiMain className="w-full min-w-0 space-y-4 px-4 py-6 sm:px-6 lg:px-8">

    <UiHeader><Link href="/integrations" className="text-xs font-semibold text-forest">← All integrations</Link><UiH1 className="mt-3 text-2xl font-bold">Accounting integrations</UiH1><UiText className="mt-1 text-sm text-slate-600">Connect the accounting system your company uses to import records and export approved transactions.</UiText></UiHeader>
    {notice && !provider && <WorkflowFeedback message={notice} onRefresh={()=>load()} />}
    {busy && <ProcessingStatus status="PROCESSING" label="ERP operation in progress"/>}
    {!encryption && <UiAlert role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">The server needs an ERP credential encryption key before credentials can be saved.</UiAlert>}
    <Tabs value={workspaceTab} onChange={(_,value)=>setWorkspaceTab(value)} aria-label="ERP workspace sections" variant="scrollable" scrollButtons="auto">
      <Tab id="erp-tab-connections" aria-controls="erp-panel-connections" label="Connections"/>
      <Tab id="erp-tab-sync" aria-controls="erp-panel-sync" label="Imports & exports"/>
    </Tabs>
    <UiBox role="tabpanel" id="erp-panel-connections" aria-labelledby="erp-tab-connections" hidden={workspaceTab!==0} className="space-y-5">
    <UiSection aria-labelledby="accounting-options" className="space-y-3">
      <UiH2 id="accounting-options" className="text-base font-bold">Choose your accounting software</UiH2>
      <UiBox className="grid gap-3 sm:grid-cols-2">
        {primaryProviders.filter(key => catalog[key]).map(key => {
          const Icon = key === "TALLY" ? ReceiptIndianRupee : Landmark;
          return <UiBox key={key} className="flex flex-col items-start gap-3 rounded-xl border border-line bg-white p-4 sm:p-5">
            <span className="grid size-10 place-items-center rounded-lg bg-emerald-50 text-emerald-800"><Icon size={20} aria-hidden /></span>
            <div><UiH3 className="text-lg font-bold">{catalog[key].name}</UiH3><p className="mt-1 text-sm text-slate-600">{providerDescriptions[key]}</p></div>
            <Button variant="contained" size="small" endIcon={<ArrowRight size={15} />} disabled={busy} onClick={() => { setNotice(""); setEditing(null); setProvider(key); }}>Connect {catalog[key].name}</Button>
          </UiBox>;
        })}
      </UiBox>
      <UiDetails className="rounded-xl border border-line bg-white">
        <UiSummary className="font-semibold">
          Advanced
        </UiSummary>
        <div className="divide-y divide-line border-t border-line px-4">
          {Object.entries(catalog).filter(([key]) => !primaryProviders.includes(key)).map(([key, item]) =>
            <div key={key} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div><UiH3 className="text-sm font-bold">{item.name}</UiH3><p className="mt-0.5 text-sm text-slate-600">{providerDescriptions[key]}</p></div>
              <Button variant="outlined" size="small" disabled={busy} onClick={() => { setNotice(""); setEditing(null); setProvider(key); }}>Connect {item.name}</Button>
            </div>)}
        </div>
      </UiDetails>
    </UiSection>
    <Dialog open={Boolean(provider)} onClose={busy ? undefined : () => { setProvider(""); setEditing(null); }} fullWidth maxWidth="sm" aria-labelledby="erp-connection-title">
      {provider && <><DialogTitle id="erp-connection-title">{editing ? "Edit" : "Connect"} {catalog[provider]?.name}</DialogTitle><DialogContent dividers>
      <UiForm key={`${provider}-${editing?.id || "new"}`} onSubmit={save}>
        {notice && <UiAlert role="alert" className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900">{notice}</UiAlert>}
        {!encryption && provider !== "TALLY" && <UiAlert role="alert" className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Credential storage needs to be configured by your administrator.</UiAlert>}<UiText className="mt-2 text-xs text-slate-500">{catalog[provider]?.note} <UiLink href={catalog[provider]?.docs} target="_blank" rel="noreferrer" className="text-forest underline">Setup documentation</UiLink></UiText><UiBox className="mt-4 grid gap-4 md:grid-cols-2"><UiLabel className="text-xs font-semibold">Connection name<UiInput name="name" required maxLength={120} defaultValue={editing?.name || ""} className={input}/></UiLabel>{Object.entries(catalog[provider]?.config_fields || {}).map(([key, text]) => <UiLabel key={key} className="text-xs font-semibold">{text}<UiInput name={`config:${key}`} required defaultValue={String(editing?.config[key] || (key === "region" ? "in" : ""))} className={input}/></UiLabel>)}{Object.entries(catalog[provider]?.secret_fields || {}).map(([key, text]) => <UiLabel key={key} className="text-xs font-semibold">{text}<UiInput type="password" autoComplete="new-password" name={`secret:${key}`} required={!editing?.has_credentials} placeholder={editing?.has_credentials ? "Leave blank to retain saved credential" : ""} className={input}/></UiLabel>)}</UiBox><UiLabel className="mt-4 block text-xs font-semibold">Automatic imports<UiSelect name="sync_interval_minutes" defaultValue={String(editing?.config.sync_interval_minutes || 0)} className={input}><option value="0">Off · import manually</option><option value="15">Every 15 minutes</option><option value="60">Every hour</option><option value="1440">Daily</option></UiSelect></UiLabel><UiDetails className="mt-4"><UiSummary className="cursor-pointer text-sm font-semibold">Account, item, tax and Finance entity mappings</UiSummary><UiText className="mt-2 text-xs text-slate-500">Enter mappings reviewed with your ERP administrator. Finance requires collection names and key fields from its OData metadata. Saving changes requires a new connection test.</UiText><UiTextarea name="advanced" spellCheck={false} aria-label="ERP mappings" defaultValue={JSON.stringify(editing ? Object.fromEntries(Object.entries(editing.config).filter(([key]) => !Object.hasOwn(catalog[provider].config_fields, key) && key !== "sync_interval_minutes")) : provider === "DYNAMICS_FINANCE" ? { entities: { suppliers: { collection: "VendorsV2", key_fields: ["dataAreaId", "VendorAccountNumber"] } } } : {}, null, 2)} className="mt-3 min-h-40 w-full rounded border border-line p-3 font-mono text-xs"/></UiDetails><UiButton disabled={busy || (!encryption && provider !== "TALLY")} className="mt-4 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save connection</UiButton><Button type="button" disabled={busy} onClick={() => { setProvider(""); setEditing(null); }} sx={{ ml: 1 }}>Cancel</Button></UiForm></DialogContent></>}</Dialog>
    <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Your connections</UiH2><UiBox className="mt-3 divide-y divide-line">{connections.map(row => <UiBox key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><UiBox><UiStrong>{row.name}</UiStrong><UiText className="mt-1 text-xs text-slate-500">{catalog[row.provider]?.name} · {row.enabled ? "Connection verified" : "Not verified / disconnected"}{row.tested_at ? ` · ${new Date(row.tested_at).toLocaleString()}` : ""}</UiText>{row.last_error && <UiText className="mt-1 text-xs text-rose-700">{row.last_error}</UiText>}</UiBox><UiBox className="flex gap-2"><UiButton disabled={busy} onClick={() => { setSelected(row.id); setRecordPage(1); setWorkspaceTab(1); }} className="rounded border border-line px-3 py-2 text-xs">Imports &amp; exports</UiButton><UiButton disabled={busy} onClick={() => void action(`/erp/connections/${row.id}/test`, {}, "Connection verified.")} className="rounded border border-line px-3 py-2 text-xs">Test connection</UiButton><UiButton disabled={busy} onClick={() => { setNotice(""); setEditing(row); setProvider(row.provider); }} className="rounded border border-line px-3 py-2 text-xs">Settings</UiButton><UiButton disabled={busy} onClick={() => void disconnect(row)} className="rounded border border-line px-3 py-2 text-xs text-rose-700">Disconnect</UiButton></UiBox></UiBox>)}{!connections.length && <EmptyState description="No ERP accounts connected. Add one above." onAction={()=>void load()} actionLabel="Refresh data" />}</UiBox></UiSection>
    </UiBox><UiBox role="tabpanel" id="erp-panel-sync" aria-labelledby="erp-tab-sync" hidden={workspaceTab!==1} className="space-y-5">
    <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Import or export records</UiH2><UiBox className="mt-4 grid gap-3 md:grid-cols-3"><UiLabel className="text-xs font-semibold">Connection<UiSelect value={selected} onChange={event => { setSelected(event.target.value); setResource("suppliers"); setRecordPage(1); }} className={input}><option value="">Select connection</option>{connections.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold">Records<UiSelect value={resource} onChange={event => { setResource(event.target.value); setLocalSearch(""); setLocalPage(1); }} className={input}>{(current ? catalog[current.provider]?.resources || [] : ["suppliers"]).map(value => <option key={value} value={value}>{label(value)}</option>)}</UiSelect></UiLabel><UiBox className="self-end"><UiButton disabled={busy || !current?.enabled} onClick={() => void action("/erp/runs", { connection_id: selected, resource, page: 1 }, "Import queued. Records appear below for review.")} className="min-h-10 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Import from ERP</UiButton></UiBox></UiBox>{current && <UiText className="mt-3 text-xs text-slate-500">{catalog[current.provider]?.note}</UiText>}<UiBox className="mt-5 border-t border-line pt-4"><UiH3 className="text-sm font-semibold">Prepare a local record for ERP review</UiH3><UiInput aria-label="Search local records" placeholder="Search record name or number" value={localSearch} onChange={event => { setLocalSearch(event.target.value); setLocalPage(1); }} className={input}/><UiBox className="mt-3 flex flex-wrap items-end gap-3"><UiLabel className="min-w-64 flex-1 text-xs font-semibold">Local {label(resource)}<UiSelect value={localId} onChange={event => setLocalId(event.target.value)} className={input}><option value="">Select a record</option>{locals.map(row => <option key={row.id} value={row.id}>{row.name || row.number || row.invoice_number || row.reference_number || row.id}{row.amount ? ` · ${row.amount}` : ""}</option>)}</UiSelect></UiLabel><UiButton disabled={busy || !selected || !localId} onClick={() => void action("/erp/records", { connection_id: selected, resource, local_id: localId }, "Review package prepared. Open it below before sending.")} className="min-h-10 rounded-lg border border-line px-4 py-2 text-sm font-semibold disabled:opacity-50">Prepare export</UiButton></UiBox><UiBox className="mt-3 flex gap-4 text-xs"><Pagination aria-label="Local record pages" count={Math.max(1, localPages)} page={Math.min(localPage, Math.max(1, localPages))} onChange={(_, page) => setLocalPage(page)} color="primary" size="small" showFirstButton showLastButton disabled={busy}/></UiBox><UiText className="mt-2 text-xs text-slate-500">Suppliers and purchase orders must be approved; receipts accepted; invoices payment ready. Closed or cancelled records cannot be sent.</UiText></UiBox></UiSection>
    <UiSection className="overflow-x-auto rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Records to review</UiH2><UiTable className="mt-4 w-full min-w-[650px] text-left text-xs"><UiTableHead><UiTableRow>{["Resource", "Direction", "Status", "ERP reference", "Action"].map(text => <UiTh key={text} className="p-2">{text}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{records.map(row => <UiTableRow key={row.id} className="border-t border-line"><UiTd className="p-2">{label(row.resource)}</UiTd><UiTd className="p-2">{row.direction}</UiTd><UiTd className="p-2">{row.status}{row.error && <UiText className="mt-1 max-w-xs text-rose-700">{row.error}</UiText>}</UiTd><UiTd className="max-w-48 truncate p-2">{row.external_id || "Not sent"}</UiTd><UiTd className="p-2"><UiButton disabled={busy} onClick={() => void openRecord(row)} className="font-semibold text-forest underline">Review</UiButton></UiTd></UiTableRow>)}</UiTableBody></UiTable>{!records.length && <EmptyState description="No imported or prepared records." onAction={()=>void load()} actionLabel="Refresh data" />}<UiBox className="mt-4 flex items-center gap-4 text-xs"><Pagination aria-label="ERP record pages" count={Math.max(1, recordPages)} page={Math.min(recordPage, Math.max(1, recordPages))} onChange={(_, page) => setRecordPage(page)} color="primary" size="small" showFirstButton showLastButton disabled={busy}/></UiBox></UiSection>
    <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Import history</UiH2><UiBox className="mt-3 max-h-72 overflow-y-auto divide-y divide-line">{runs.filter(run => !selected || run.connection_id === selected).map(run => <UiBox key={run.id} className="py-3 text-xs"><UiStrong>{label(run.resource)}</UiStrong> · page {run.page} · <ProcessingStatus status={run.status}/> · {run.record_count} records{run.error && <UiText className="mt-1 text-rose-700">{run.error}</UiText>}{run.has_more && run.status === "COMPLETED" && <UiButton disabled={busy} onClick={() => void action("/erp/runs", { connection_id: run.connection_id, resource: run.resource, page: run.page + 1 }, "Next page queued.")} className="ml-3 font-semibold text-forest underline">Import next page</UiButton>}</UiBox>)}</UiBox></UiSection>
    </UiBox>
    <LiveData compact onRefresh={() => load(true)} paused={Boolean(busy || provider || detail)} interval={10000}/>
    {detail && <UiModal className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/40 p-4" onClose={() => setDetail(null)}><UiSection className="mx-auto my-4 max-w-4xl rounded-xl bg-white p-5 shadow-xl"><UiBox className="flex justify-between gap-4"><UiH2 className="font-bold">Review {label(detail.resource)} · {detail.status}</UiH2><UiButton disabled={busy} onClick={() => setDetail(null)}>Close</UiButton></UiBox>{notice && !provider && <WorkflowFeedback message={notice} onRefresh={()=>load()} />}<UiDetails className="mt-4" open={detail.direction === "OUTBOUND"}><UiSummary className="cursor-pointer text-sm font-semibold">{detail.direction === "INBOUND" ? "Original ERP data" : "Prepared ERP payload"}</UiSummary><pre className="mt-2 max-h-80 overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(detail.payload, null, 2)}</pre></UiDetails>{detail.direction === "INBOUND" && detail.local_id && <UiText className="mt-4 text-sm">Linked local record: <code>{detail.local_id}</code>. Review corrections in the relevant supplier, invoice, order, receipt or payment page.</UiText>}{detail.direction === "INBOUND" && detail.status === "CONFLICT" && <UiForm className="mt-4 rounded-lg border border-line p-4" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); void action(`/erp/records/${detail.id}/review-conflict`, { note: form.get("note") }, "Difference acknowledged. Local values retained.").then(result => { if (result)
        setDetail(null); }); }}><UiText className="text-sm">The ERP record changed after it was linked. Review both records and make any required correction through their normal approval or reversal process.</UiText><UiInput name="note" required placeholder="Review decision and correction reference" className={input}/><UiButton disabled={busy} className="mt-3 rounded border border-line px-3 py-2 text-sm">Keep local values and acknowledge</UiButton></UiForm>}{detail.direction === "INBOUND" && !detail.local_id && <><UiText className="mt-4 text-sm">Review the fields below. Use a local supplier UUID in vendor_id. To link an existing record, provide its local_id instead. Imported invoices and purchase orders retain their review and approval steps.</UiText><UiTextarea aria-label="Reviewed import fields" value={review} onChange={event => setReview(event.target.value)} className="mt-3 min-h-72 w-full rounded border border-line p-3 font-mono text-xs"/><UiButton disabled={busy} onClick={() => { try {
        const data = JSON.parse(review);
        void action(`/erp/records/${detail.id}`, { reviewed_import: data }, "Import applied.").then(result => { if (result)
            setDetail(null); });
    }
    catch {
        setNotice("Reviewed import fields must be valid JSON.");
    } }} className="mt-3 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">Apply reviewed import</UiButton></>}{detail.direction === "OUTBOUND" && <><UiText className="mt-4 text-sm text-slate-600">Review the exact destination and amounts before sending. {direct ? "The connected ERP will create an accounting record; its status depends on that ERP's rules." : "This provider needs a reviewed import package and customer-specific mappings before direct document posting."}</UiText><UiBox className="mt-4 flex flex-wrap gap-3"><UiButton disabled={busy} onClick={() => void download()} className="rounded border border-line px-3 py-2 text-sm">Download review JSON</UiButton>{detailConnection?.provider === "TALLY" && ["suppliers", "invoices", "payments"].includes(detail.resource) && <UiButton disabled={busy} onClick={() => void download("xml")} className="rounded border border-line px-3 py-2 text-sm">Download Tally XML</UiButton>}</UiBox>{direct && detail.status === "NEEDS_REVIEW" && <><UiLabel className="mt-4 flex items-start gap-2 text-sm"><UiInput type="checkbox" checked={confirmSend} onChange={event => setConfirmSend(event.target.checked)}/>I reviewed the ERP company, account mappings, amounts and taxes. Create this record in the connected ERP.</UiLabel><UiButton disabled={busy || !confirmSend} onClick={() => void action(`/erp/records/${detail.id}/send`, { confirm_send: true }, "ERP record created.").then(result => { if (result)
        setDetail(null); })} className="mt-3 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Send reviewed record</UiButton></>}{["UNKNOWN", "SENDING", "NEEDS_REVIEW"].includes(detail.status) && <UiForm className="mt-5 border-t border-line pt-4" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); void action(`/erp/records/${detail.id}/reconcile`, { external_id: form.get("external_id"), note: form.get("note") }, "Remote reference recorded after reconciliation.").then(result => { if (result)
        setDetail(null); }); }}><UiH3 className="text-sm font-semibold">Already imported or uncertain outcome?</UiH3><UiText className="mt-1 text-xs text-slate-500">Check the ERP first. Record the remote ID after confirming the exact document; this records your review and does not send it again.</UiText><UiInput name="external_id" required placeholder="Verified ERP record ID" className={input}/><UiInput name="note" required placeholder="Reconciliation note" className={input}/><UiButton disabled={busy} className="mt-3 rounded border border-line px-3 py-2 text-sm">Record verified ERP reference</UiButton></UiForm>}</>}</UiSection></UiModal>}
  </UiMain>;
}
