"use client";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { PageSkeleton } from "@/components/content-skeleton";
import { UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiText, UiTextarea } from "@/components/product-ui";
import { requestConfirmation, requestInput, showNotice } from "@/components/product-dialogs";
import { useListPagination } from "@/components/list-pagination";
import { AppLink as Link } from "@/components/product-ui";
import { RecordsTable } from "@/components/records-table";
import { LiveData } from "@/components/live-data";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Tool = "email-intake" | "approval-rules" | "sla-rules" | "follow-ups" | "custom-fields" | "bulk-actions" | "reports" | "notifications" | "vendor-aliases" | "financial-notes";
type RecordRow = Record<string, unknown> & {
    id?: string;
};
const reports = ["invoice-aging", "vendor-outstanding", "exception-summary", "payment-forecast", "month-end-readiness"];
export function Phase2Tool({ tool }: {
    tool: Tool;
}) {
    const [rows, setRows] = useState<RecordRow[]>([]);
    const [aux, setAux] = useState<RecordRow[]>([]);
    const [vendors, setVendors] = useState<RecordRow[]>([]);
    const [delegations, setDelegations] = useState<RecordRow[]>([]);
    const [members, setMembers] = useState<RecordRow[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const [token, setToken] = useState("");
    const [workspaceKey, setWorkspaceKey] = useState("");
    const [report, setReport] = useState("invoice-aging");
    const [reportResult, setReportResult] = useState<unknown>(null);
    const [selected, setSelected] = useState<string[]>([]);
    const [preview, setPreview] = useState<RecordRow | null>(null);
    const [selectedInvoice, setSelectedInvoice] = useState("");
    const [noteId, setNoteId] = useState("");
    const config: Record<Tool, {
        title: string;
        description: string;
        endpoint: string;
    }> = {
        "email-intake": { title: "Invoice email intake", description: "Use a private token to accept invoice attachments from your mail automation. Repeated message IDs are safely ignored.", endpoint: "/email-ingestion/logs" },
        "approval-rules": { title: "Approval rules", description: "Route invoices by amount, vendor, and category. Steps run in order and each decision is retained.", endpoint: "/approval-rules" },
        "sla-rules": { title: "Exception SLAs", description: "Set exception deadlines and escalate overdue work to selected workspace roles.", endpoint: "/exception-slas" },
        "follow-ups": { title: "Vendor follow-up drafts", description: "Draft vendor questions, review the recipient and message, then send only when explicitly requested.", endpoint: "/follow-ups" },
        "custom-fields": { title: "Custom invoice fields", description: "Define typed tenant fields and capture values on invoices before approval.", endpoint: "/custom-fields" },
        "bulk-actions": { title: "Bulk exception actions", description: "Select exceptions, review the preview, then confirm the time-limited action.", endpoint: "/exceptions" },
        reports: { title: "Operational reports", description: "View date-filterable payable, aging, exception, forecast, and month-end readiness reports.", endpoint: "/reports" },
        notifications: { title: "Notifications", description: "Review workspace alerts and set your own in-app and email preferences.", endpoint: "/notifications" },
        "vendor-aliases": { title: "Vendor aliases", description: "Add known supplier name, GSTIN, or sender-domain variations to improve deterministic matching.", endpoint: "/vendors/aliases" },
        "financial-notes": { title: "Credit and debit notes", description: "Record adjustments against invoices or GRNs and route them for a second-person decision.", endpoint: "/credit-debit-notes" },
    };
    const meta = config[tool];
    const refreshLive = async () => {
        const response = await apiFetch(meta.endpoint);
        if (!response.ok)
            throw new Error("Could not refresh workspace records.");
        setRows(await response.json());
    };
    const load = useCallback(async () => {
        setMessage("");
        try {
            if (tool === "email-intake") {
                const [tokenResponse, logsResponse] = await Promise.all([apiFetch("/invoice-intake-token"), apiFetch(meta.endpoint)]);
                if (!tokenResponse.ok)
                    throw new Error("Only finance users can view the intake token.");
                const tokenData = await tokenResponse.json();
                setToken(tokenData.token);
                setWorkspaceKey(tokenData.workspace_key);
                if (!logsResponse.ok)
                    throw new Error("Could not load email ingestion history.");
                setRows(await logsResponse.json());
                return;
            }
            if (tool === "follow-ups") {
                const [drafts, invoices] = await Promise.all([apiFetch(meta.endpoint), apiFetch("/invoices/")]);
                if (!drafts.ok || !invoices.ok)
                    throw new Error("Could not load follow-ups and invoices.");
                setRows(await drafts.json());
                setAux((await invoices.json()).results || []);
                return;
            }
            if (tool === "vendor-aliases") {
                const [aliases, vendors] = await Promise.all([apiFetch(meta.endpoint), apiFetch("/vendors")]);
                if (!aliases.ok || !vendors.ok)
                    throw new Error("Could not load aliases and vendors.");
                setRows(await aliases.json());
                setAux(await vendors.json());
                return;
            }
            if (tool === "financial-notes") {
                const [notes, invoices, grns] = await Promise.all([apiFetch(meta.endpoint), apiFetch("/invoices/"), apiFetch("/grns")]);
                if (!notes.ok || !invoices.ok || !grns.ok)
                    throw new Error("Could not load note register.");
                setRows(await notes.json());
                setAux([...(await invoices.json()).results || [], ...(await grns.json()).map((x: RecordRow) => ({ ...x, kind: "GRN" }))]);
                return;
            }
            if (tool === "bulk-actions") {
                const [exceptions, users] = await Promise.all([apiFetch(meta.endpoint), apiFetch("/users")]);
                if (!exceptions.ok || !users.ok)
                    throw new Error("Could not load queue and workspace members.");
                setRows(await exceptions.json());
                setAux(await users.json());
                return;
            }
            if (tool === "custom-fields") {
                const [fields, invoices] = await Promise.all([apiFetch(meta.endpoint), apiFetch("/invoices/")]);
                if (!fields.ok || !invoices.ok)
                    throw new Error("Could not load custom fields.");
                setRows(await fields.json());
                setAux((await invoices.json()).results || []);
                return;
            }
            if (tool === "notifications") {
                const [notifications, prefs] = await Promise.all([apiFetch(meta.endpoint), apiFetch("/notification-preferences")]);
                if (!notifications.ok || !prefs.ok)
                    throw new Error("Could not load notifications.");
                setRows(await notifications.json());
                setReportResult(await prefs.json());
                return;
            }
            if (tool === "approval-rules") {
                const [rules, autoRules, vendorResponse, delegationResponse, memberResponse] = await Promise.all([apiFetch("/approval-rules"), apiFetch("/auto-approval-rules"), apiFetch("/vendors"), apiFetch("/approval-delegations"), apiFetch("/users")]);
                if (!rules.ok || !autoRules.ok || !vendorResponse.ok || !delegationResponse.ok || !memberResponse.ok)
                    throw new Error("Could not load approval policies.");
                setRows(await rules.json());
                setAux(await autoRules.json());
                setVendors(await vendorResponse.json());
                setDelegations(await delegationResponse.json());
                setMembers(await memberResponse.json());
                return;
            }
            const response = await apiFetch(meta.endpoint);
            if (!response.ok)
                throw new Error("Could not load workspace records.");
            setRows(await response.json());
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not load workspace data.");
        }
    }, [meta.endpoint, tool]);
    const [initialLoading, setInitialLoading] = useState(true);
    useEffect(() => { setInitialLoading(true); void load().finally(() => setInitialLoading(false)); }, [load]);
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        setBusy(true);
        setMessage("");
        try {
            let path = meta.endpoint;
            let body: Record<string, unknown> = {};
            if (tool === "approval-rules") {
                const roles = String(form.get("roles") || "APPROVER").split(",").map(x => x.trim().toUpperCase()).filter(Boolean);
                body = { name: form.get("name"), priority: Number(form.get("priority") || 100), conditions: { min_amount: Number(form.get("min_amount") || 0), max_amount: Number(form.get("max_amount") || 999999999), categories: String(form.get("categories") || "").split(",").map(x => x.trim()).filter(Boolean) }, steps: roles.map(role => ({ role, due_hours: Number(form.get("due_hours") || 72) })) };
            }
            else if (tool === "sla-rules")
                body = { exception_code: form.get("exception_code"), due_after_hours: Number(form.get("due_after_hours")), priority: form.get("priority"), escalation_roles: String(form.get("roles") || "OWNER,FINANCE").split(",").map(x => x.trim().toUpperCase()).filter(Boolean) };
            else if (tool === "vendor-aliases")
                body = { vendor_id: form.get("vendor_id"), alias: form.get("alias"), kind: form.get("kind") };
            else if (tool === "custom-fields")
                body = { name: form.get("name"), key: form.get("key"), field_type: form.get("field_type"), required: form.get("required") === "on", options: String(form.get("options") || "").split(",").map(x => x.trim()).filter(Boolean) };
            else if (tool === "follow-ups") {
                body = { invoice_id: form.get("invoice_id"), recipient: form.get("recipient"), subject: form.get("subject"), body: form.get("body") };
            }
            else if (tool === "financial-notes") {
                const target = String(form.get("invoice") || "");
                body = { kind: form.get("kind"), invoice: target.startsWith("INV:") ? target.slice(4) : null, grn: target.startsWith("GRN:") ? target.slice(4) : null, note_number: form.get("note_number"), amount: form.get("amount"), reason: form.get("reason"), remarks: form.get("remarks") };
            }
            const response = await apiFetch(path, { method: "POST", body: JSON.stringify(body) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error?.message || JSON.stringify(data));
            formElement.reset();
            setMessage("Saved successfully and recorded.");
            await load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not save the record.");
        }
        finally {
            setBusy(false);
        }
    }
    async function rotateToken() { setBusy(true); try {
        const r = await apiFetch("/invoice-intake-token", { method: "POST", body: "{}" });
        const d = await r.json();
        if (!r.ok)
            throw new Error(d.error?.message || "Could not rotate token");
        setToken(d.token);
        setMessage("Intake token rotated. Update the configured mail integration.");
    }
    catch (e) {
        setMessage(e instanceof Error ? e.message : "Could not rotate token");
    }
    finally {
        setBusy(false);
    } }
    async function perform(path: string, body: Record<string, unknown>, success: string) { setBusy(true); setMessage(""); try {
        const r = await apiFetch(path, { method: "POST", body: JSON.stringify(body) });
        const d = await r.json();
        if (!r.ok)
            throw new Error(d.error?.message || JSON.stringify(d));
        setMessage(success);
        await load();
        return d;
    }
    catch (e) {
        setMessage(e instanceof Error ? e.message : "Action failed.");
        return null;
    }
    finally {
        setBusy(false);
    } }
    function table(data: RecordRow[]) { return <RecordsTable rows={data} resetKey={tool} error={/could not|failed|cannot|unavailable/i.test(message) ? message : undefined} onRetry={()=>void load()}/>; }
    function field(label: string, name: string, props: Record<string, string | boolean> = {}) { return <UiLabel className="block text-xs font-semibold">{label}<UiInput name={name} {...props} className="mt-2 block w-full rounded-lg border border-line px-3 py-2.5 text-sm font-normal"/></UiLabel>; }
    const pagination = useListPagination(rows, tool);
    if (initialLoading) return <PageSkeleton label={`Loading ${meta.title}`} />;
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiH1 className="mt-6 text-2xl font-bold">{meta.title}</UiH1><UiText className="mt-1 max-w-3xl text-sm text-slate-500">{meta.description}</UiText>{message && <WorkflowFeedback message={message} onRefresh={()=>load()} />}
  {["email-intake", "notifications", "follow-ups", "financial-notes"].includes(tool) && <LiveData key={tool} onRefresh={refreshLive} paused={busy} interval={20000}/>}

  {tool === "email-intake" && <UiSection className="mt-6 rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Private intake credential</UiH2><UiText className="mt-1 text-xs text-slate-500">Keep this token secret. Configure your mail provider to POST multipart attachments with message_id, sender, recipient, and subject.</UiText><code className="mt-4 block break-all rounded-lg bg-slate-50 p-3 text-xs">POST /api/v1/email-ingestion/{workspaceKey} · X-Invoice-Intake-Token: {token || "loading…"}</code><UiButton onClick={() => void rotateToken()} disabled={busy} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">Rotate intake token</UiButton><UiSection className="mt-5 overflow-hidden rounded-lg border border-line"><UiH3 className="border-b border-line px-4 py-3 text-xs font-bold">Recent ingestion runs</UiH3>{table(rows)}</UiSection></UiSection>}

  {tool === "approval-rules" && <><UiForm onSubmit={submit} className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-5 md:grid-cols-3">{field("Rule name", "name", { required: true, placeholder: "Finance review by amount" })}{field("Priority", "priority", { type: "number", defaultValue: "100" })}{field("Approver roles in sequence", "roles", { required: true, defaultValue: "APPROVER,FINANCE", placeholder: "APPROVER,FINANCE" })}{field("Minimum invoice amount", "min_amount", { type: "number", min: "0", step: ".01", defaultValue: "0" })}{field("Maximum invoice amount", "max_amount", { type: "number", min: "0", step: ".01", defaultValue: "999999999" })}{field("Step SLA hours", "due_hours", { type: "number", min: "1", max: "8760", defaultValue: "72" })}{field("Categories (comma separated)", "categories", { placeholder: "TRAVEL,SERVICES" })}<UiButton disabled={busy} className="self-end rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white">Create approval rule</UiButton></UiForm><UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white"><UiH2 className="border-b border-line px-5 py-4 text-sm font-bold">Approval rules</UiH2>{table(rows)}</UiSection><AutoRulePanel rows={aux} vendors={vendors} reload={load} action={perform} busy={busy}/><DelegationPanel rows={delegations} members={members} reload={load} action={perform} busy={busy}/></>}

  {tool === "sla-rules" && <><UiForm onSubmit={submit} className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-5 md:grid-cols-4">{field("Exception code", "exception_code", { required: true, placeholder: "RATE_VARIANCE" })}{field("Due after hours", "due_after_hours", { type: "number", min: "1", max: "8760", defaultValue: "48" })}<UiLabel className="block text-xs font-semibold">Priority<UiSelect name="priority" className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal">{["LOW", "MEDIUM", "HIGH", "CRITICAL"].map(x => <option key={x}>{x}</option>)}</UiSelect></UiLabel>{field("Escalation roles", "roles", { defaultValue: "OWNER,FINANCE" })}<UiButton disabled={busy} className="rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white">Save SLA</UiButton></UiForm><UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white"><UiBox className="flex items-center justify-between border-b border-line px-5 py-4"><UiH2 className="text-sm font-bold">Configured deadlines</UiH2><UiButton onClick={() => void perform("/exceptions/escalate-overdue", {}, "Overdue exceptions escalated.")} disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Escalate overdue now</UiButton></UiBox>{table(rows)}</UiSection></>}

  {tool === "follow-ups" && <><UiForm onSubmit={submit} className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-5 md:grid-cols-2"><UiLabel className="block text-xs font-semibold">Invoice<UiSelect name="invoice_id" required className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal"><option value="">Select invoice…</option>{aux.map((x, i) => <option key={String(x.id || i)} value={String(x.id)}>{String(x.invoice_number || x.id)} · {String(x.vendor_name || x.supplier_name || "Supplier")}</option>)}</UiSelect></UiLabel>{field("Recipient email", "recipient", { type: "email", placeholder: "Supplier contact email" })}{field("Subject", "subject", { placeholder: "Invoice query" })}<UiLabel className="block text-xs font-semibold md:col-span-2">Message<UiTextarea name="body" rows={5} className="mt-2 block w-full rounded-lg border border-line px-3 py-2 text-sm font-normal" placeholder="A draft will be generated if left empty."/></UiLabel><UiButton disabled={busy} className="w-fit rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white">Create draft</UiButton></UiForm><UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white"><UiH2 className="border-b border-line px-5 py-4 text-sm font-bold">Saved drafts</UiH2>{rows.length ? pagination.rows.map(x => <FollowUpRow key={String(x.id)} row={x} perform={perform} busy={busy}/>) : <EmptyState description="No drafts yet." onAction={()=>void load()} actionLabel="Refresh data" />}</UiSection></>}

  {tool === "custom-fields" && <><UiForm onSubmit={submit} className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-5 md:grid-cols-4">{field("Display name", "name", { required: true, placeholder: "Cost centre" })}{field("Key", "key", { placeholder: "cost_centre" })}<UiLabel className="block text-xs font-semibold">Type<UiSelect name="field_type" className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal">{["TEXT", "NUMBER", "DATE", "BOOLEAN", "CHOICE"].map(x => <option key={x}>{x}</option>)}</UiSelect></UiLabel>{field("Choice options", "options", { placeholder: "OPS,SALES" })}<UiLabel className="flex items-center gap-2 text-xs"><UiInput type="checkbox" name="required"/>Required before approval</UiLabel><UiButton disabled={busy} className="w-fit rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white">Add field</UiButton></UiForm><UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white"><UiH2 className="border-b border-line px-5 py-4 text-sm font-bold">Field definitions</UiH2>{table(rows)}</UiSection><UiForm onSubmit={async (e) => { e.preventDefault(); const f = new FormData(e.currentTarget); try {
        const body = JSON.parse(String(f.get("values_json") || "{}"));
        const r = await apiFetch(`/invoices/${f.get("invoice_id")}/custom-fields`, { method: "PATCH", body: JSON.stringify(body) });
        const d = await r.json();
        if (!r.ok)
            throw new Error(d.error?.message || JSON.stringify(d));
        setMessage("Invoice custom fields saved.");
    }
    catch (x) {
        setMessage(x instanceof Error ? x.message : "Invalid custom field JSON.");
    } }} className="mt-5 grid gap-4 rounded-xl border border-line bg-white p-5 md:grid-cols-2"><UiLabel className="block text-xs font-semibold">Set invoice values<UiSelect required name="invoice_id" onChange={e => setSelectedInvoice(e.target.value)} className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal"><option value="">Choose invoice…</option>{aux.map((x, i) => <option key={String(x.id || i)} value={String(x.id)}>{String(x.invoice_number || x.id)}</option>)}</UiSelect></UiLabel><UiLabel className="block text-xs font-semibold">Values as JSON<UiTextarea name="values_json" defaultValue="{}" rows={3} className="mt-2 w-full rounded-lg border border-line px-3 py-2 font-mono text-xs" placeholder={'{"cost_centre":"OPS"}'}/></UiLabel><UiButton disabled={!selectedInvoice} className="w-fit rounded-lg border border-line px-3 py-2 text-xs font-semibold">Save invoice values</UiButton></UiForm></>}

  {tool === "bulk-actions" && <><UiBox className="mt-6 flex flex-wrap gap-3 rounded-xl border border-line bg-white p-4"><UiSelect id="bulk-operation" className="rounded-lg border border-line bg-white px-3 py-2 text-xs"><option value="ASSIGN_EXCEPTIONS">Assign selected</option><option value="RESOLVE_EXCEPTIONS">Resolve selected</option></UiSelect><UiSelect id="bulk-assignee" className="rounded-lg border border-line bg-white px-3 py-2 text-xs"><option value="">Choose assignee…</option>{aux.map(x => <option key={String(x.id)} value={String(x.id)}>{String(x.email)} · {String(x.role)}</option>)}</UiSelect><UiButton disabled={!selected.length || busy} onClick={async () => { const op = (document.getElementById("bulk-operation") as HTMLSelectElement).value; const assignee = (document.getElementById("bulk-assignee") as HTMLSelectElement).value; const note = op === "RESOLVE_EXCEPTIONS" ? (await requestInput("Resolution note to record on each exception")) || "" : ""; if (op === "RESOLVE_EXCEPTIONS" && !note)
        return; const d = await perform("/bulk-jobs", { operation: op, ids: selected, ...(op === "ASSIGN_EXCEPTIONS" ? { assigned_to_id: assignee } : { resolution_note: note }) }, "Review the preview below, then confirm to apply."); if (d)
        setPreview(d); }} className="rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white">Preview selected ({selected.length})</UiButton></UiBox><UiBox className="mt-4 overflow-hidden rounded-xl border border-line bg-white"><UiH2 className="border-b border-line px-5 py-4 text-sm font-bold">Open exceptions</UiH2>{pagination.rows.map((x, i) => <UiLabel key={String(x.id || i)} className="flex items-center gap-3 border-b border-line px-5 py-3 text-xs"><UiInput type="checkbox" checked={selected.includes(String(x.id))} onChange={e => setSelected(v => e.target.checked ? [...v, String(x.id)] : v.filter(id => id !== x.id))}/><UiSpan className="font-semibold">{String(x.invoice_number || x.invoice_id)}</UiSpan><UiSpan className="text-slate-500">{String(x.code)} · {String(x.status)}</UiSpan></UiLabel>)}{!rows.length && <EmptyState description="No open exceptions." onAction={()=>void load()} actionLabel="Refresh data" />}</UiBox>{preview && <UiBox className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-5"><UiH2 className="font-bold">Preview: {String(preview.operation)} · {String((preview.preview as RecordRow)?.count)} records</UiH2><pre className="mt-2 whitespace-pre-wrap text-xs">{JSON.stringify(preview.preview, null, 2)}</pre><UiButton disabled={busy} onClick={async () => { const d = await perform(`/bulk-jobs/${preview.id}/commit`, { preview_token: preview.preview_token }, "Bulk action completed."); if (d) {
        setPreview(null);
        setSelected([]);
    } }} className="mt-3 rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white">Confirm bulk action</UiButton></UiBox>}</>}

  {tool === "reports" && <><UiBox className="mt-6 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-white p-4"><UiLabel className="block text-xs font-semibold">Report<UiSelect value={report} onChange={e => setReport(e.target.value)} className="mt-2 block rounded-lg border border-line bg-white px-3 py-2 text-xs">{reports.map(x => <option key={x}>{x}</option>)}</UiSelect></UiLabel><UiLabel className="block text-xs font-semibold">From<UiInput id="report-from" type="date" className="mt-2 block rounded-lg border border-line px-3 py-2 text-xs"/></UiLabel><UiLabel className="block text-xs font-semibold">To<UiInput id="report-to" type="date" className="mt-2 block rounded-lg border border-line px-3 py-2 text-xs"/></UiLabel><UiButton onClick={async () => { const from = (document.getElementById("report-from") as HTMLInputElement).value; const to = (document.getElementById("report-to") as HTMLInputElement).value; const params = new URLSearchParams(); if (from)
        params.set("from", from); if (to)
        params.set("to", to); const r = await apiFetch(`/reports/${report}?${params}`); const d = await r.json(); if (!r.ok)
        setMessage(d.error?.message || "Report failed");
    else
        setReportResult(d); }} className="rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white">Run report</UiButton><UiButton onClick={async () => { const from = (document.getElementById("report-from") as HTMLInputElement).value; const to = (document.getElementById("report-to") as HTMLInputElement).value; const params = new URLSearchParams({ export: "csv" }); if (from)
        params.set("from", from); if (to)
        params.set("to", to); const r = await apiFetch(`/reports/${report}?${params}`); if (!r.ok) {
        setMessage("Report export failed.");
        return;
    } const blob = await r.blob(); const href = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = href; a.download = `kriyopay-${report}.csv`; a.click(); URL.revokeObjectURL(href); }} className="rounded-lg border border-line px-4 py-2 text-xs font-semibold">Export CSV</UiButton></UiBox>{reportResult !== null && <pre className="mt-4 overflow-auto rounded-xl border border-line bg-white p-5 text-xs">{JSON.stringify(reportResult, null, 2)}</pre>}</>}

  {tool === "notifications" && <><UiBox className="mt-6 rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">My preferences</UiH2><UiBox className="mt-3 flex flex-wrap gap-4">{Object.entries((reportResult || {}) as Record<string, boolean>).map(([key, value]) => <UiLabel key={key} className="flex items-center gap-2 text-xs"><UiInput type="checkbox" checked={value} onChange={async (e) => { const r = await apiFetch("/notification-preferences", { method: "PATCH", body: JSON.stringify({ [key]: e.target.checked }) }); if (r.ok)
        setReportResult(await r.json()); }}/>{key.replaceAll("_", " ")}</UiLabel>)}</UiBox></UiBox><UiSection className="mt-4 overflow-hidden rounded-xl border border-line bg-white"><UiH2 className="border-b border-line px-5 py-4 text-sm font-bold">Recent notifications</UiH2>{pagination.rows.map((x, i) => <UiArticle key={String(x.id || i)} className="flex items-center justify-between gap-3 border-b border-line p-4"><UiBox><UiStrong className="text-xs">{String((x.payload as RecordRow)?.title || "Notification")}</UiStrong><UiText className="mt-1 text-xs text-slate-500">{String((x.payload as RecordRow)?.body || "")}</UiText></UiBox>{x.status !== "READ" && <UiButton onClick={async () => { await apiFetch(`/notifications/${x.id}/read`, { method: "PATCH", body: "{}" }); await load(); }} className="text-xs font-semibold text-forest">Mark read</UiButton>}</UiArticle>)}</UiSection></>}

  {tool === "vendor-aliases" && <><UiForm onSubmit={submit} className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-5 md:grid-cols-3"><UiLabel className="block text-xs font-semibold">Vendor<UiSelect name="vendor_id" required className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal"><option value="">Select vendor…</option>{aux.map(x => <option key={String(x.id)} value={String(x.id)}>{String(x.name)}</option>)}</UiSelect></UiLabel>{field("Alias", "alias", { required: true, placeholder: "Alternate supplier name" })}<UiLabel className="block text-xs font-semibold">Alias kind<UiSelect name="kind" className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal">{["NAME", "GSTIN", "EMAIL_DOMAIN"].map(x => <option key={x}>{x}</option>)}</UiSelect></UiLabel><UiButton disabled={busy} className="w-fit rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white">Add alias</UiButton></UiForm><UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white">{table(rows)}</UiSection></>}

  {tool === "financial-notes" && <><UiForm onSubmit={submit} className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-5 md:grid-cols-3"><UiLabel className="block text-xs font-semibold">Type<UiSelect name="kind" className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal"><option>CREDIT</option><option>DEBIT</option></UiSelect></UiLabel><UiLabel className="block text-xs font-semibold">Invoice / GRN<UiSelect name="invoice" required className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal"><option value="">Choose record…</option>{aux.map(x => <option key={String(x.id)} value={`${x.kind === "GRN" ? "GRN" : "INV"}:${String(x.id)}`}>{String(x.invoice_number || x.number || x.id)} {String(x.kind || "INVOICE")}</option>)}</UiSelect></UiLabel>{field("Note number", "note_number", { required: true })}{field("Amount", "amount", { type: "number", min: ".01", step: ".01", required: true })}<UiLabel className="block text-xs font-semibold">Reason<UiSelect name="reason" className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm font-normal">{["QUANTITY_SHORTAGE", "DAMAGED_GOODS", "RATE_CORRECTION", "DISCOUNT", "RETURN", "TAX_CORRECTION", "OTHER"].map(x => <option key={x}>{x}</option>)}</UiSelect></UiLabel>{field("Remarks", "remarks")}<UiButton disabled={busy} className="w-fit rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white">Create pending note</UiButton></UiForm><UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white"><UiH2 className="border-b border-line px-5 py-4 text-sm font-bold">Note approval queue</UiH2>{pagination.rows.map(x => <UiArticle key={String(x.id)} className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4 text-xs"><UiSpan>{String(x.kind)} · {String(x.note_number)} · ₹{String(x.amount)} · {String(x.status)}</UiSpan>{x.status === "PENDING" && <UiBox className="flex gap-2"><UiButton onClick={() => setNoteId(String(x.id))} className="rounded border border-line px-2 py-1">Select</UiButton>{noteId === x.id && <><UiButton onClick={() => void perform(`/credit-debit-notes/${x.id}/decision`, { decision: "APPROVED" }, "Note approved.")} className="rounded bg-forest px-2 py-1 text-white">Approve</UiButton><UiButton onClick={() => void perform(`/credit-debit-notes/${x.id}/decision`, { decision: "REJECTED" }, "Note rejected.")} className="rounded bg-rose-700 px-2 py-1 text-white">Reject</UiButton></>}</UiBox>}</UiArticle>)}</UiSection></>}
  {["follow-ups", "notifications", "financial-notes", "bulk-actions"].includes(tool) && pagination.controls}
  </UiMain>;
}
function AutoRulePanel({ rows, vendors, reload, action, busy }: {
    rows: RecordRow[];
    vendors: RecordRow[];
    reload: () => Promise<void>;
    action: (path: string, body: Record<string, unknown>, success: string) => Promise<unknown>;
    busy: boolean;
}) {
    return <UiSection className="mt-5 rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Guarded auto-approval</UiH2><UiText className="mt-1 text-xs text-slate-500">Disabled by default. Eligible invoices must be matched, duplicate-reviewed, have no blocking exceptions, fall under the amount cap, and match an explicit allowed vendor.</UiText><UiForm onSubmit={async (e) => { e.preventDefault(); const element = e.currentTarget; const f = new FormData(element); const allowed = f.getAll("vendor_ids"); const r = await apiFetch("/auto-approval-rules", { method: "POST", body: JSON.stringify({ name: f.get("name"), amount_limit: f.get("amount_limit"), allowed_vendor_ids: allowed, enabled: f.get("enabled") === "on" }) }); const d = await r.json(); if (!r.ok)
        showNotice(d.error?.message || "Could not save rule");
    else {
        element.reset();
        await reload();
    } }} className="mt-4 grid gap-3 md:grid-cols-3"><UiInput name="name" required placeholder="Rule name" className="rounded-lg border border-line px-3 py-2 text-xs"/><UiInput name="amount_limit" required type="number" min=".01" step=".01" placeholder="Maximum amount" className="rounded-lg border border-line px-3 py-2 text-xs"/><UiSelect name="vendor_ids" required multiple size={4} className="rounded-lg border border-line bg-white px-3 py-2 text-xs md:col-span-2">{vendors.map(v => <option key={String(v.id)} value={String(v.id)}>{String(v.name)} · {String(v.id)}</option>)}</UiSelect><UiLabel className="flex items-center gap-2 text-xs"><UiInput type="checkbox" name="enabled"/>Enable</UiLabel><UiButton disabled={busy} className="w-fit rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Save auto-approval rule</UiButton></UiForm>{rows.length > 0 && <UiBox className="mt-4 space-y-2">{rows.map(x => <UiBox key={String(x.id)} className="flex items-center justify-between rounded-lg bg-slate-50 p-3 text-xs"><UiSpan>{String(x.name)} · cap ₹{String(x.amount_limit)} · {x.enabled ? "Enabled" : "Disabled"}</UiSpan><UiButton onClick={async () => { await action(`/auto-approval-rules/${x.id}`, { enabled: !x.enabled }, `Auto-approval ${x.enabled ? "disabled" : "enabled"}.`); await reload(); }} className="font-semibold text-forest">{x.enabled ? "Disable" : "Enable"}</UiButton></UiBox>)}</UiBox>}</UiSection>;
}
function FollowUpRow({ row, perform, busy, compact = false }: {
    compact?: boolean;
    row: RecordRow;
    perform: (path: string, body: Record<string, unknown>, success: string) => Promise<unknown>;
    busy: boolean;
}) {
    const [recipient, setRecipient] = useState(String(row.recipient || ""));
    const [subject, setSubject] = useState(String(row.subject || ""));
    const [body, setBody] = useState(String(row.body || ""));
    return <UiBox className={`grid gap-3 ${compact ? "" : "border-b border-line p-4 md:grid-cols-4"}`}><UiSpan className="text-xs font-semibold">{String(row.invoice_number || row.invoice_id)} · {String(row.status)}</UiSpan><UiInput value={recipient} onChange={e => setRecipient(e.target.value)} className="rounded border border-line px-2 py-1 text-xs"/><UiInput value={subject} onChange={e => setSubject(e.target.value)} className="rounded border border-line px-2 py-1 text-xs"/><UiTextarea value={body} onChange={e => setBody(e.target.value)} rows={3} className={`rounded border border-line px-2 py-1 text-xs ${compact ? "" : "md:col-span-3"}`}/><UiBox className="flex items-start gap-2"><UiButton disabled={busy || row.status === "SENT"} onClick={() => void perform(`/follow-ups/${row.id}`, { recipient, subject, body }, "Draft saved.")} className="rounded border border-line px-3 py-2 text-xs">Save draft</UiButton><UiButton disabled={busy || row.status === "SENT" || !recipient} onClick={async () => { if ((await requestConfirmation(`Send this message to ${recipient}?`)))
        void perform(`/follow-ups/${row.id}`, { recipient, subject, body, send: true }, "Follow-up sent."); }} className="rounded bg-forest px-3 py-2 text-xs font-semibold text-white">Send</UiButton></UiBox></UiBox>;
}
function DelegationPanel({ rows, members, reload, action, busy }: {
    rows: RecordRow[];
    members: RecordRow[];
    reload: () => Promise<void>;
    action: (path: string, body: Record<string, unknown>, success: string) => Promise<unknown>;
    busy: boolean;
}) {
    return <UiSection className="mt-5 rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">My approval delegation</UiH2><UiText className="mt-1 text-xs text-slate-500">Create a bounded delegation for your own approval tasks. Delegates can act only during the saved window.</UiText><UiForm onSubmit={async (e) => { e.preventDefault(); const element = e.currentTarget; const f = new FormData(element); const result = await action("/approval-delegations", { delegate_id: f.get("delegate_id"), starts_at: new Date(String(f.get("starts_at"))).toISOString(), ends_at: new Date(String(f.get("ends_at"))).toISOString() }, "Approval delegation created."); if (result) {
        element.reset();
        await reload();
    } }} className="mt-4 grid gap-3 md:grid-cols-4"><UiLabel className="block text-xs font-semibold">Delegate<UiSelect required name="delegate_id" className="mt-2 w-full rounded-lg border border-line bg-white px-3 py-2 text-xs"><option value="">Select member…</option>{members.map(m => <option key={String(m.id)} value={String(m.id)}>{String(m.email)} · {String(m.role)}</option>)}</UiSelect></UiLabel><UiLabel className="block text-xs font-semibold">Starts<UiInput required name="starts_at" type="datetime-local" className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-xs"/></UiLabel><UiLabel className="block text-xs font-semibold">Ends<UiInput required name="ends_at" type="datetime-local" className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-xs"/></UiLabel><UiButton disabled={busy} className="self-end rounded-lg bg-forest px-3 py-2.5 text-xs font-semibold text-white">Create delegation</UiButton></UiForm><UiBox className="mt-4 space-y-2">{rows.map(x => <UiBox key={String(x.id)} className="rounded-lg bg-slate-50 p-3 text-xs">Delegated to {String(members.find(m => m.id === x.delegate_id)?.email || x.delegate_id)} · {new Date(String(x.starts_at)).toLocaleString()} – {new Date(String(x.ends_at)).toLocaleString()}</UiBox>)}</UiBox></UiSection>;
}
