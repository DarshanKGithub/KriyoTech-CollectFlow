"use client";
import { applyFieldErrors } from "@/components/form-validation";
import { CollectionExplorer } from "@/components/collection-explorer";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { PageSkeleton } from "@/components/content-skeleton";
import { UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiH4, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { requestConfirmation, requestInput } from "@/components/product-dialogs";
import { useListPagination } from "@/components/list-pagination";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { LiveData } from "@/components/live-data";
import { Button, Dialog, DialogActions, DialogContent, DialogTitle } from "@mui/material";
const salaryLabels: Record<string, string> = { DRAFT: "Draft", SUBMITTED: "Awaiting approval", APPROVED: "Approved", PARTIALLY_PAID: "Partly paid", PAID: "Paid", SETTLED: "Settled" };
const salaryTools = { draft: "Create salary draft", policy: "Pay policies", earnings: "Approved trip earnings", advance: "Driver advances" } as const;
type Driver = {
    id: string;
    name: string;
    status: string;
};
type Payment = {
    id: string;
    amount: string;
    payment_date: string;
    payment_reference: string;
    notes: string;
};
type Adjustment = {
    id: string;
    kind: "DEDUCTION" | "PAYMENT_REVERSAL";
    category: string;
    amount: string;
    reason: string;
    adjustment_date: string;
    status: string;
    review_note: string;
    original_payment_id: string | null;
    evidence_filename: string;
};
type Salary = {
    id: string;
    driver: Driver;
    period_start: string;
    settlement_number: number;
    salary_amount: string;
    trip_earnings_amount: string;
    driver_expense_reimbursement_amount: string;
    driver_expense_reimbursements: { id: string; category: string; description: string; amount: string; trip_number: string; receipt: string | null }[];
    gross_earnings_amount: string;
    deductions: string;
    adjustments: Adjustment[];
    advance_recovered_amount: string;
    net_payable_amount: string;
    paid_amount: string;
    remaining_amount: string;
    status: string;
    submitted_by_name: string;
    submitted_at: string | null;
    approved_by_name: string;
    approved_at: string | null;
    review_note: string;
    notes: string;
    payments: Payment[];
};
type Advance = {
    id: string;
    driver: Driver;
    amount: string;
    recovered_amount: string;
    outstanding_amount: string;
    status: string;
    given_date: string;
    reference: string;
    notes: string;
    recoveries: {
        id: string;
        amount: string;
        period_start: string;
    }[];
};
type PayPolicy = {
    id: string;
    driver: Driver;
    basis: "MONTHLY" | "PER_TRIP" | "PER_KILOMETRE";
    rate: string;
    effective_from: string;
    effective_to: string | null;
};
type TripEarning = {
    id: string;
    driver: Driver;
    trip: {
        id: string;
        trip_number: string;
    };
    trip_date: string;
    basis: string;
    units: string;
    rate: string;
    amount: string;
    included_in_settlement: boolean;
    settlement_status: string;
};
const input = "rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const money = (value: string) => `₹${Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const statusClass: Record<string, string> = { DRAFT: "bg-slate-100 text-slate-600", SUBMITTED: "bg-amber-50 text-amber-700", APPROVED: "bg-sky-50 text-sky-700", PARTIALLY_PAID: "bg-violet-50 text-violet-700", PAID: "bg-emerald-50 text-emerald-700", SETTLED: "bg-emerald-50 text-emerald-700" };
export default function DriverSalarySettlementPage() {
    const [initialLoading, setInitialLoading] = useState(true);
    const [drivers, setDrivers] = useState<Driver[]>([]);
    const [records, setRecords] = useState<Salary[]>([]);
    const [salaryFilter, setSalaryFilter] = useState("");
    const [search, setSearch] = useState("");
    const [tool, setTool] = useState<keyof typeof salaryTools | null>(null);
    const [paymentRecordId, setPaymentRecordId] = useState("");
    const [paymentError, setPaymentError] = useState("");
    const [advances, setAdvances] = useState<Advance[]>([]);
    const [policies, setPolicies] = useState<PayPolicy[]>([]);
    const [earnings, setEarnings] = useState<TripEarning[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState("");
    const [editing, setEditing] = useState("");
    const keys = useRef(new WeakMap<HTMLFormElement, string>());
    const refresh = useCallback(async () => {
        const [driverResponse, recordResponse, advanceResponse, policyResponse, earningsResponse] = await Promise.all([apiFetch("/fleet/drivers"), apiFetch("/fleet/driver-salaries"), apiFetch("/fleet/driver-advances"), apiFetch("/fleet/driver-pay-policies"), apiFetch("/fleet/driver-earnings")]);
        if (!driverResponse.ok || !recordResponse.ok || !advanceResponse.ok || !policyResponse.ok || !earningsResponse.ok)
            throw new Error("Could not load driver pay rules and settlements.");
        setDrivers(await driverResponse.json());
        setRecords(await recordResponse.json());
        setAdvances(await advanceResponse.json());
        setPolicies(await policyResponse.json());
        setEarnings(await earningsResponse.json());
    }, []);
    useEffect(() => { void refresh().catch(error => setMessage(error.message)).finally(() => setInitialLoading(false)); }, [refresh]);
    async function createRecord(event: FormEvent<HTMLFormElement>) {
        try {
        event.preventDefault();
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form).entries());
        const month = String(data.period_month || "");
        const period_start = month ? `${month}-01` : "";
        setBusy("create");
        setMessage("");
        const payload: Record<string, unknown> = { driver_id: data.driver_id, period_start, notes: data.notes };
        if (data.salary_amount)
            payload.salary_amount = data.salary_amount;
        const response = await apiFetch("/fleet/driver-salaries", { method: "POST", body: JSON.stringify(payload) });
        const result = await response.json().catch(() => null);
        if (!response.ok) applyFieldErrors(form, result);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not create the salary record.");
        else {
            form.reset();
            setMessage("Salary entry saved as a draft. Submit it for independent review before payment.");
        }
        await refresh();
        setBusy("");
    
        } catch (error) { setMessage(error instanceof Error ? error.message : "Could not complete this action. Refresh data before retrying."); } finally { setBusy(""); }
    }
    async function createAdvance(event: FormEvent<HTMLFormElement>) {
        try {
        event.preventDefault();
        const form = event.currentTarget;
        const key = keys.current.get(form) || crypto.randomUUID();
        keys.current.set(form, key);
        const data = Object.fromEntries(new FormData(form).entries());
        setBusy("advance");
        setMessage("");
        const response = await apiFetch("/fleet/driver-advances", { method: "POST", body: JSON.stringify({ ...data, idempotency_key: key }) });
        const result = await response.json().catch(() => null);
        if (!response.ok) applyFieldErrors(form, result);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not record the driver advance.");
        else {
            form.reset();
            keys.current.delete(form);
            setMessage("Driver advance recorded. It remains outstanding until allocated to an approved salary settlement.");
        }
        await refresh();
        setBusy("");
    
        } catch (error) { setMessage(error instanceof Error ? error.message : "Could not complete this action. Refresh data before retrying."); } finally { setBusy(""); }
    }
    async function createPolicy(event: FormEvent<HTMLFormElement>) {
        try {
        event.preventDefault();
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form).entries());
        if (!data.effective_to)
            delete data.effective_to;
        setBusy("policy");
        setMessage("");
        const response = await apiFetch("/fleet/driver-pay-policies", { method: "POST", body: JSON.stringify(data) });
        const result = await response.json().catch(() => null);
        if (!response.ok) applyFieldErrors(form, result);
        if (!response.ok)
            setMessage(result?.non_field_errors?.[0] || result?.error || "Could not save this pay policy.");
        else {
            form.reset();
            setMessage("Effective-dated driver pay policy saved. Approved eligible trips will accrue earnings using its saved rate.");
        }
        await refresh();
        setBusy("");
    
        } catch (error) { setMessage(error instanceof Error ? error.message : "Could not complete this action. Refresh data before retrying."); } finally { setBusy(""); }
    }
    async function closePolicy(policy: PayPolicy) {
        const end = (await requestInput("Last date this pay rate applies (YYYY-MM-DD)", new Date().toISOString().slice(0, 10)));
        if (end === null)
            return;
        setBusy(policy.id);
        setMessage("");
        const response = await apiFetch(`/fleet/driver-pay-policies/${policy.id}`, { method: "PATCH", body: JSON.stringify({ effective_to: end }) });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(result?.error || "Could not close this policy period.");
        else
            setMessage("Policy period closed. Add the replacement rate with a start date after this one.");
        await refresh();
        setBusy("");
    }
    async function recoverAdvance(event: FormEvent<HTMLFormElement>, advance: Advance) {
        try {
        event.preventDefault();
        const form = event.currentTarget;
        const key = keys.current.get(form) || crypto.randomUUID();
        keys.current.set(form, key);
        const data = Object.fromEntries(new FormData(form).entries());
        setBusy(advance.id);
        setMessage("");
        const response = await apiFetch(`/fleet/driver-advances/${advance.id}/recoveries`, { method: "POST", body: JSON.stringify({ ...data, idempotency_key: key }) });
        const result = await response.json().catch(() => null);
        if (!response.ok) applyFieldErrors(form, result);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not allocate the advance recovery.");
        else {
            form.reset();
            keys.current.delete(form);
            setMessage("Advance recovery allocated to the approved salary settlement.");
        }
        await refresh();
        setBusy("");
    
        } catch (error) { setMessage(error instanceof Error ? error.message : "Could not complete this action. Refresh data before retrying."); } finally { setBusy(""); }
    }
    async function transition(record: Salary, action: "submit" | "approve" | "reject") {
        const note = action === "reject" ? (await requestInput("Why does this salary need correction?")) : "";
        if (action === "reject" && !note?.trim())
            return;
        setBusy(record.id);
        setMessage("");
        const response = await apiFetch(`/fleet/driver-salaries/${record.id}/${action}`, { method: "POST", body: JSON.stringify(note ? { note } : {}) });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(result?.error || `Could not ${action} this salary record.`);
        else
            setMessage(action === "submit" ? "Salary submitted for independent approval." : action === "approve" ? "Salary approved. Payments can now be recorded." : "Salary returned to draft for correction.");
        await refresh();
        setBusy("");
    }
    async function updateDraft(event: FormEvent<HTMLFormElement>, record: Salary) {
        try {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.currentTarget).entries());
        const form = event.currentTarget;
        const month = String(data.period_month || "");
        setBusy(record.id);
        setMessage("");
        const response = await apiFetch(`/fleet/driver-salaries/${record.id}`, { method: "PATCH", body: JSON.stringify({ driver_id: data.driver_id, period_start: `${month}-01`, salary_amount: data.salary_amount, notes: data.notes }) });
        const result = await response.json().catch(() => null);
        if (!response.ok) applyFieldErrors(form, result);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not update the salary draft.");
        else {
            setEditing("");
            setMessage("Salary draft updated.");
        }
        await refresh();
        setBusy("");
    
        } catch (error) { setMessage(error instanceof Error ? error.message : "Could not complete this action. Refresh data before retrying."); } finally { setBusy(""); }
    }
    async function pay(event: FormEvent<HTMLFormElement>, record: Salary) {
        event.preventDefault();
        if (busy) return;
        const form = event.currentTarget;
        const key = keys.current.get(form) || crypto.randomUUID();
        keys.current.set(form, key);
        const data = Object.fromEntries(new FormData(form).entries());
        setBusy(record.id);
        setMessage("");
        setPaymentError("");
        try {
            const response = await apiFetch(`/fleet/driver-salaries/${record.id}/payments`, { method: "POST", body: JSON.stringify({ ...data, idempotency_key: key }) });
            const result = await response.json().catch(() => null);
            if (!response.ok) {
                applyFieldErrors(form, result);
                setPaymentError(typeof result?.error === "string" ? result.error : "Could not record this salary payment. Check the form and try again.");
                return;
            }
            keys.current.delete(form);
            setPaymentRecordId("");
            setMessage("Driver payment recorded in the salary ledger.");
            await refresh().catch(() => setMessage("Payment recorded. Refresh the ledger to see the updated balance."));
        } catch (error) {
            setPaymentError(error instanceof Error ? error.message : "Could not confirm that the payment was recorded.");
        } finally {
            setBusy("");
        }
    }
    async function addAdjustment(record: Salary, kind: "DEDUCTION" | "PAYMENT_REVERSAL", payment?: Payment) {
        const amount = (await requestInput(kind === "DEDUCTION" ? "Deduction amount" : `Amount to reverse (maximum ${payment?.amount})`, kind === "PAYMENT_REVERSAL" ? payment?.amount : ""));
        if (!amount || !Number.isFinite(Number(amount)) || Number(amount) <= 0)
            return;
        const reason = (await requestInput(kind === "DEDUCTION" ? "Reason for deduction" : "Reason for payment correction"));
        if (!reason?.trim())
            return;
        const category = kind === "DEDUCTION" ? (await requestInput("Deduction category (for example: damage, fine, other)")) : "Payment correction";
        if (kind === "DEDUCTION" && !category?.trim())
            return;
        let evidence_id: string | undefined;
        const attach = (await requestConfirmation("Attach a receipt or supporting document?"));
        if (attach) {
            const file = await new Promise<File | null>(resolve => { const picker = document.createElement("input"); picker.type = "file"; picker.accept = ".pdf,image/jpeg,image/png,image/heic,image/heif"; picker.onchange = () => resolve(picker.files?.[0] || null); picker.click(); });
            if (file) {
                const form = new FormData();
                form.append("file", file);
                const upload = await apiFetch("/fleet/documents", { method: "POST", body: form });
                const uploaded = await upload.json().catch(() => null);
                if (!upload.ok) {
                    setMessage(uploaded?.error || "Could not upload the evidence file.");
                    return;
                }
                evidence_id = uploaded.id;
            }
        }
        setBusy(record.id);
        setMessage("");
        const response = await apiFetch(`/fleet/driver-salaries/${record.id}/adjustments`, { method: "POST", body: JSON.stringify({ kind, amount, reason: reason.trim(), category: category?.trim() || "", adjustment_date: new Date().toISOString().slice(0, 10), ...(payment ? { original_payment: payment.id } : {}), ...(evidence_id ? { evidence_id } : {}), idempotency_key: crypto.randomUUID() }) });
        const result = await response.json().catch(() => null);
        setMessage(response.ok ? "Adjustment submitted. A different finance reviewer must approve it." : result?.error || result?.non_field_errors?.[0] || "Could not submit adjustment.");
        await refresh();
        setBusy("");
    }
    async function reviewAdjustment(adjustment: Adjustment, action: "approve" | "reject", record: Salary) {
        const note = action === "reject" ? (await requestInput("Why are you rejecting this adjustment?")) : "";
        if (action === "reject" && !note?.trim())
            return;
        setBusy(adjustment.id);
        const response = await apiFetch(`/fleet/driver-salary-adjustments/${adjustment.id}/${action}`, { method: "POST", body: JSON.stringify(note ? { note } : {}) });
        const result = await response.json().catch(() => null);
        setMessage(response.ok ? `Adjustment ${action}d.` : result?.error || `Could not ${action} this adjustment.`);
        await refresh();
        setBusy("");
    }
    async function exportLedger() {
        const start = (await requestInput("Ledger start date (YYYY-MM-DD)", `${new Date().getFullYear()}-01-01`));
        if (!start)
            return;
        const end = (await requestInput("Ledger end date (YYYY-MM-DD)", new Date().toISOString().slice(0, 10)));
        if (!end)
            return;
        const response = await apiFetch(`/fleet/driver-ledger.csv?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`);
        if (!response.ok) {
            const result = await response.json().catch(() => null);
            setMessage(result?.error || "Could not export the driver ledger.");
            return;
        }
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a");
        link.href = url;
        link.download = `driver-ledger-${start}-to-${end}.csv`;
        link.click();
        URL.revokeObjectURL(url);
    }
    async function prepareSettlements() {
        const period = new Date().toISOString().slice(0, 7);
        setBusy("prepare");
        setMessage("");
        try {
            const response = await apiFetch("/fleet/driver-salaries", { method: "POST", body: JSON.stringify({ action: "prepare", period }) });
            const result = await response.json().catch(() => null);
            if (!response.ok) throw new Error(result?.error || "Could not prepare salary drafts.");
            const issueCount = Array.isArray(result?.discrepancies) ? result.discrepancies.length : 0;
            setMessage(`${result?.created || 0} salary draft(s) prepared for ${period}; ${result?.already_present || 0} already existed.${issueCount ? ` ${issueCount} driver policy issue(s) need review.` : ""} Review and approve drafts before recording payments.`);
            await refresh();
        } catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not prepare salary drafts.");
        } finally {
            setBusy("");
        }
    }
    const monthLabel = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    const pending = records.filter(record => record.status === "SUBMITTED").length;
    const remainingTotal = records.filter(record => ["APPROVED", "PARTIALLY_PAID"].includes(record.status)).reduce((total, record) => total + Number(record.remaining_amount), 0);
    const advanceTotal = advances.reduce((total, advance) => total + Number(advance.outstanding_amount), 0);
    const policiesPage = useListPagination(policies);
    const earningsPage = useListPagination(earnings);
    const advancesPage = useListPagination(advances);
    const payable = (record: Salary) => ["APPROVED", "PARTIALLY_PAID"].includes(record.status) && Number(record.remaining_amount) > 0;
    const paid = (record: Salary) => ["PAID", "SETTLED"].includes(record.status);
    const queueOptions = [
        { value: "", label: "All records", count: records.length },
        { value: "SUBMITTED", label: "Awaiting approval", count: pending },
        { value: "PAYABLE", label: "Ready to pay", count: records.filter(payable).length },
        { value: "CLOSED", label: "Paid or settled", count: records.filter(paid).length },
        { value: "DRAFT", label: "Drafts", count: records.filter(record => record.status === "DRAFT").length },
    ];
    const query = search.trim().toLowerCase();
    const visibleRecords = records.filter(record => {
        const matchesFilter = !salaryFilter || (salaryFilter === "PAYABLE" ? payable(record) :
            salaryFilter === "CLOSED" ? paid(record) : record.status === salaryFilter);
        return matchesFilter && `${record.driver.name} ${record.period_start.slice(0, 7)} ${monthLabel(record.period_start)}`.toLowerCase().includes(query);
    });
    const recordsPage = useListPagination(visibleRecords, `${salaryFilter}:${search}`);
    const paymentRecord = records.find(record => record.id === paymentRecordId);
    if (initialLoading) return <PageSkeleton variant="cards" label="Loading driver salaries and settlements" />;
    return <UiMain className="w-full min-w-0 space-y-6 px-4 py-8 sm:px-6 lg:px-8">
    <UiHeader className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet finance</UiText><UiH1 className="mt-1 text-2xl font-bold">Driver salary settlements</UiH1><UiText className="mt-1 max-w-3xl text-sm text-slate-500">Track salary policies, approved deductions, advances, payment corrections, and each driver’s ledger.</UiText></UiBox><UiBox className="flex flex-wrap gap-2"><UiButton disabled={!!busy} onClick={() => void prepareSettlements()} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "prepare" ? "Preparing…" : "Prepare salary drafts"}</UiButton><UiButton onClick={() => void exportLedger()} className="rounded-lg border border-line bg-white px-4 py-2 text-sm font-semibold">Export driver ledger</UiButton></UiBox></UiHeader>
    <LiveData onRefresh={refresh} paused={Boolean(busy || editing || tool || paymentRecordId)} interval={20000}/>
    {message && !tool && <WorkflowFeedback message={message} onRefresh={()=>refresh()} />}
    <UiSection className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><UiArticle className="rounded-xl border border-line bg-white p-4"><UiText className="text-xs text-slate-500">Salary records</UiText><UiStrong className="mt-1 block text-xl">{records.length}</UiStrong></UiArticle><UiArticle className="rounded-xl border border-line bg-white p-4"><UiText className="text-xs text-slate-500">Awaiting approval</UiText><UiStrong className="mt-1 block text-xl">{pending}</UiStrong></UiArticle><UiArticle className="rounded-xl border border-line bg-white p-4"><UiText className="text-xs text-slate-500">Salary still payable</UiText><UiStrong className="mt-1 block text-xl">{money(String(remainingTotal))}</UiStrong></UiArticle><UiArticle className="rounded-xl border border-line bg-white p-4"><UiText className="text-xs text-slate-500">Driver advances to recover</UiText><UiStrong className="mt-1 block text-xl">{money(String(advanceTotal))}</UiStrong></UiArticle></UiSection>
    <div className="flex flex-wrap gap-2">
      {(Object.keys(salaryTools) as Array<keyof typeof salaryTools>).map(key => <Button key={key} variant="outlined" size="small" disabled={Boolean(busy)}
        onClick={() => { setMessage(""); setTool(key); }}>{salaryTools[key]}</Button>)}
    </div>
    <UiSection className="space-y-3" aria-label="Salary ledger">
      <div className="rounded-xl border border-line bg-white p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div><UiH2 className="text-lg font-bold">Salary ledger</UiH2><p className="text-sm text-slate-600">{visibleRecords.length} matching records</p></div>
          <input aria-label="Search driver salaries" value={search} onChange={event => setSearch(event.target.value)} placeholder="Driver or salary month" className="rounded-lg border border-line px-3 py-2 text-sm"/>
        </div>
        <div role="group" aria-label="Filter salary records" className="mt-3 flex flex-wrap gap-2">
          {queueOptions.map(item => <button key={item.value} type="button" aria-pressed={salaryFilter === item.value} onClick={() => setSalaryFilter(item.value)}
            className={`rounded-lg border px-3 py-2 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest ${salaryFilter === item.value ? "border-forest bg-emerald-50 text-forest" : "border-line bg-white text-slate-700 hover:bg-slate-50"}`}>
            {item.label} · {item.count}
          </button>)}
        </div>
      </div>
      <CollectionExplorer rows={visibleRecords.map(record=>({id:record.id,driver:record.driver.name,period:record.period_start,status:salaryLabels[record.status] || record.status,gross_INR:Number(record.gross_earnings_amount),net_payable_INR:Number(record.net_payable_amount),paid_INR:Number(record.paid_amount),remaining_INR:Number(record.remaining_amount)}))} recordPrefix="salary-record-" onOpen={id=>recordsPage.reveal(visibleRecords.findIndex(item=>item.id===id))}>{recordsPage.rows.map(record => <UiArticle id={`salary-record-${record.id}`} tabIndex={-1} key={record.id} className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiBox className="flex flex-wrap items-center gap-2"><UiH3 className="font-semibold">{record.driver.name} · {monthLabel(record.period_start)}{record.settlement_number > 1 ? ` · Supplemental ${record.settlement_number - 1}` : ""}</UiH3><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusClass[record.status] || statusClass.DRAFT}`}>{salaryLabels[record.status] || record.status}</UiSpan></UiBox><dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
  {[
    { label: "Net payable", value: record.net_payable_amount },
    { label: "Paid", value: record.paid_amount },
    { label: payable(record) ? "Still to pay" : "Remaining balance", value: record.remaining_amount },
  ].map(item => <div key={item.label} className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
    <dt className="text-xs text-slate-600">{item.label}</dt>
    <dd className="m-0 break-words text-sm font-bold tabular-nums">{money(item.value)}</dd>
  </div>)}
</dl>
<details className="mt-3 text-xs text-slate-600">
  <summary className="cursor-pointer font-semibold text-forest">Pay breakdown</summary>
  <p className="mt-2">Gross {money(record.gross_earnings_amount)} · Base pay {money(record.salary_amount)} · Trip earnings {money(record.trip_earnings_amount)} · Advances recovered {money(record.advance_recovered_amount)}</p>
</details>{record.notes && <UiText className="mt-1 text-xs text-slate-500">{record.notes}</UiText>}<UiText className="mt-2 text-xs text-slate-500">{record.submitted_at ? `Submitted ${new Date(record.submitted_at).toLocaleString()}${record.submitted_by_name ? ` by ${record.submitted_by_name}` : ""}` : "Not submitted"}{record.approved_at ? ` · Approved ${new Date(record.approved_at).toLocaleString()}${record.approved_by_name ? ` by ${record.approved_by_name}` : ""}` : ""}</UiText></UiBox><UiBox className="flex gap-2">{record.status === "DRAFT" && <UiButton disabled={!!busy} onClick={() => void transition(record, "submit")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">{busy === record.id ? "Saving…" : "Submit for review"}</UiButton>}{record.status === "SUBMITTED" && <UiButton disabled={!!busy} onClick={() => void transition(record, "approve")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === record.id ? "Saving…" : "Approve salary"}</UiButton>}</UiBox></UiBox>
        {record.status === "DRAFT" && <UiButton onClick={() => setEditing(editing === record.id ? "" : record.id)} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">{editing === record.id ? "Close edit" : "Edit draft"}</UiButton>}
        {record.status === "SUBMITTED" && <UiButton disabled={!!busy} onClick={() => void transition(record, "reject")} className="mt-3 rounded-lg border border-amber-200 px-3 py-2 text-xs font-semibold text-amber-800 disabled:opacity-50">Return for correction</UiButton>}
        {record.review_note && record.status === "DRAFT" && <UiText className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">Reviewer note: {record.review_note}</UiText>}
        {editing === record.id && record.status === "DRAFT" && <UiForm onSubmit={event => void updateDraft(event, record)} className="mt-4 grid gap-2 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4"><UiLabel className="text-xs text-slate-500">Driver<UiSelect className={`${input} mt-1 block w-full`} name="driver_id" defaultValue={record.driver.id} required>{drivers.filter(driver => driver.status === "ACTIVE").map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Month<UiInput className={`${input} mt-1 block w-full`} name="period_month" type="month" defaultValue={record.period_start.slice(0, 7)} required/></UiLabel><UiLabel className="text-xs text-slate-500">Monthly base pay<UiInput className={`${input} mt-1 block w-full`} name="salary_amount" type="number" min="0" step="0.01" defaultValue={record.salary_amount} required/></UiLabel><UiLabel className="text-xs text-slate-500">Note<UiInput className={`${input} mt-1 block w-full`} name="notes" defaultValue={record.notes}/></UiLabel><UiButton disabled={!!busy} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save changes</UiButton></UiForm>}
        {payable(record) && <UiButton type="button" disabled={Boolean(busy)} onClick={() => { setPaymentError(""); setPaymentRecordId(record.id); }} className="mt-3 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">Record payment</UiButton>}
        {record.payments.length > 0 && <UiBox className="mt-4 border-t border-line pt-3"><UiH4 className="text-xs font-semibold text-slate-600">Payment history</UiH4><UiBox className="mt-2 space-y-2">{record.payments.map(payment => { const alreadyReversed = record.adjustments.filter(item => item.kind === "PAYMENT_REVERSAL" && item.original_payment_id === payment.id && item.status !== "REJECTED").reduce((sum, item) => sum + Number(item.amount), 0); return <UiBox key={payment.id} className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500"><UiSpan>{payment.payment_date}{payment.payment_reference ? ` · ${payment.payment_reference}` : ""}</UiSpan><UiSpan className="flex items-center gap-3"><UiStrong className="text-ink">{money(payment.amount)}</UiStrong>{alreadyReversed < Number(payment.amount) && <UiButton disabled={!!busy} onClick={() => void addAdjustment(record, "PAYMENT_REVERSAL", { ...payment, amount: String(Number(payment.amount) - alreadyReversed) })} className="rounded border border-amber-200 px-2 py-1 text-amber-800">Correct / reverse</UiButton>}</UiSpan></UiBox>; })}</UiBox></UiBox>}
      {record.driver_expense_reimbursements.length > 0 && <UiBox className="mt-4 border-t border-line pt-3"><UiH4 className="text-xs font-semibold text-slate-600">Approved driver-paid trip expenses · {money(record.driver_expense_reimbursement_amount)}</UiH4><UiBox className="mt-2 space-y-1">{record.driver_expense_reimbursements.map(item => <UiText key={item.id} className="text-xs text-slate-500">{item.trip_number} · {item.category} · {item.description} · {money(item.amount)}{item.receipt ? ` · Receipt: ${item.receipt}` : ""}</UiText>)}</UiBox></UiBox>}
      {record.adjustments.length > 0 && <UiBox className="mt-4 border-t border-line pt-3"><UiH4 className="text-xs font-semibold text-slate-600">Deductions and corrections</UiH4><UiBox className="mt-2 space-y-2">{record.adjustments.map(item => <UiBox key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 p-3 text-xs"><UiSpan><UiStrong>{item.kind === "DEDUCTION" ? `${item.category} deduction` : "Payment reversal"}</UiStrong> · {money(item.amount)} · {item.reason}{item.evidence_filename ? ` · Evidence: ${item.evidence_filename}` : " · No evidence attached"}<UiSpan className="block text-slate-500">{item.adjustment_date} · {item.status}</UiSpan>{item.review_note && <UiSpan className="block text-amber-800">Reviewer: {item.review_note}</UiSpan>}</UiSpan>{item.status === "SUBMITTED" && <UiSpan className="flex gap-2"><UiButton disabled={!!busy} onClick={() => void reviewAdjustment(item, "approve", record)} className="rounded bg-forest px-2 py-1 text-white">Approve</UiButton><UiButton disabled={!!busy} onClick={() => void reviewAdjustment(item, "reject", record)} className="rounded border border-line px-2 py-1">Reject</UiButton></UiSpan>}</UiBox>)}</UiBox></UiBox>}
        {record.status !== "DRAFT" && record.status !== "SUBMITTED" && <UiButton disabled={!!busy || Number(record.remaining_amount) <= 0} onClick={() => void addAdjustment(record, "DEDUCTION")} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Add deduction for review</UiButton>}
      </UiArticle>)}{visibleRecords.length > 10 && recordsPage.controls}</CollectionExplorer>
      {records.length > 0 && visibleRecords.length === 0 && <p className="rounded-xl border border-line bg-white p-5 text-sm text-slate-600">No salary records match these filters.</p>}
      {records.length === 0 && <EmptyState description="No salary records yet. Create a monthly salary draft to start the ledger." onAction={()=>void refresh()} actionLabel="Refresh data" />}
    </UiSection>
    <Dialog open={Boolean(paymentRecord)} onClose={() => { if (!busy) setPaymentRecordId(""); }} fullWidth maxWidth="sm" aria-labelledby="salary-payment-title">
      <DialogTitle id="salary-payment-title">Record salary payment</DialogTitle>
      <DialogContent dividers>
        {paymentRecord && <UiForm key={paymentRecord.id} id="salary-payment-form" onSubmit={event => void pay(event, paymentRecord)} className="space-y-4">
          <div className="rounded-lg bg-slate-50 p-3">
            <p className="text-sm font-semibold">{paymentRecord.driver.name} · {monthLabel(paymentRecord.period_start)}{paymentRecord.settlement_number > 1 ? ` · Supplemental ${paymentRecord.settlement_number - 1}` : ""}</p>
            <p className="mt-1 text-sm text-slate-700">Still to pay <strong>{money(paymentRecord.remaining_amount)}</strong></p>
          </div>
          {paymentError && <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{paymentError}</p>}
          {!payable(paymentRecord) && <p role="status" className="text-sm text-slate-600">This record no longer has a balance available for payment.</p>}
          <fieldset disabled={Boolean(busy) || !payable(paymentRecord)} className="grid min-w-0 gap-3 sm:grid-cols-2">
            <UiLabel className="text-sm">Amount paid (₹)<UiInput className={`${input} mt-1 block w-full`} name="amount" type="number" min="0.01" max={paymentRecord.remaining_amount} step="0.01" required/></UiLabel>
            <UiLabel className="text-sm">Payment date<UiInput className={`${input} mt-1 block w-full`} name="payment_date" type="date" required defaultValue={new Date().toISOString().slice(0, 10)}/></UiLabel>
            <UiLabel className="text-sm sm:col-span-2">Reference (optional)<UiInput className={`${input} mt-1 block w-full`} name="payment_reference" placeholder="Bank or UPI reference"/></UiLabel>
          </fieldset>
        </UiForm>}
      </DialogContent>
      <DialogActions>
        <Button disabled={Boolean(busy)} onClick={() => setPaymentRecordId("")}>Cancel</Button>
        <Button variant="contained" type="submit" form="salary-payment-form" disabled={Boolean(busy) || !paymentRecord || !payable(paymentRecord)}>{busy ? "Recording…" : "Record payment"}</Button>
      </DialogActions>
    </Dialog>
    <Dialog open={tool !== null} onClose={() => { if (!busy) setTool(null); }} fullWidth maxWidth="lg" aria-labelledby="salary-tool-title"><DialogTitle id="salary-tool-title">{tool ? salaryTools[tool] : ""}</DialogTitle><DialogContent dividers><div className="space-y-4">{message && <WorkflowFeedback message={message} onRefresh={refresh}/>}{tool === "policy" && <>    <UiForm onSubmit={event => void createPolicy(event)} className="grid gap-3 rounded-xl border border-line bg-white p-5 shadow-sm sm:grid-cols-2 lg:grid-cols-6"><UiBox className="sm:col-span-2 lg:col-span-6"><UiH2 className="font-semibold">Set a driver pay policy</UiH2><UiText className="mt-1 text-xs text-slate-500">Monthly policies prefill salary drafts. Trip policies accrue only on eligible trips. Per-kilometre pay requires odometer readings.</UiText></UiBox><UiLabel className="text-xs text-slate-500">Driver<UiSelect className={`${input} mt-1 block w-full`} name="driver_id" required defaultValue=""><option value="" disabled>Select driver</option>{drivers.filter(driver => driver.status === "ACTIVE").map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Pay basis<UiSelect className={`${input} mt-1 block w-full`} name="basis" required defaultValue="MONTHLY"><option value="MONTHLY">Fixed monthly salary</option><option value="PER_TRIP">Fixed amount per trip</option><option value="PER_KILOMETRE">Rate per kilometre</option></UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Amount / rate (₹)<UiInput className={`${input} mt-1 block w-full`} name="rate" type="number" min="0.01" step="0.01" required/></UiLabel><UiLabel className="text-xs text-slate-500">Effective from<UiInput className={`${input} mt-1 block w-full`} name="effective_from" type="date" required defaultValue={new Date().toISOString().slice(0, 10)}/></UiLabel><UiLabel className="text-xs text-slate-500">Effective to (optional)<UiInput className={`${input} mt-1 block w-full`} name="effective_to" type="date"/></UiLabel><UiButton disabled={busy === "policy" || drivers.length === 0} className="self-end rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "policy" ? "Saving…" : "Save pay policy"}</UiButton></UiForm>
    <UiSection className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiH2 className="font-semibold">Pay policy history</UiH2><UiBox className="mt-3 divide-y divide-line">{policiesPage.rows.map(policy => <UiBox key={policy.id} className="flex flex-wrap items-center justify-between gap-2 py-3 first:pt-0"><UiText className="text-sm"><UiStrong>{policy.driver.name}</UiStrong> · {policy.basis === "MONTHLY" ? `${money(policy.rate)} per month` : policy.basis === "PER_TRIP" ? `${money(policy.rate)} per trip` : `${money(policy.rate)} per km`} · {policy.effective_from} to {policy.effective_to || "Open ended"}</UiText>{!policy.effective_to && <UiButton disabled={!!busy} onClick={() => void closePolicy(policy)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold">Close period</UiButton>}</UiBox>)}{policies.length === 0 && <EmptyState description="No pay policies yet. Add a monthly, per-trip, or per-kilometre policy." onAction={()=>void refresh()} actionLabel="Refresh data" />}</UiBox>{policiesPage.controls}</UiSection>
</>}{tool === "earnings" && <>    <UiSection className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex items-center justify-between gap-2"><UiBox><UiH2 className="font-semibold">Approved trip earnings</UiH2><UiText className="mt-1 text-xs text-slate-500">Each amount uses a snapshot of the policy rate and distance from approval time.</UiText></UiBox><UiSpan className="text-xs text-slate-500">{earnings.length} earnings</UiSpan></UiBox><UiBox className="mt-3 divide-y divide-line">{earningsPage.rows.map(earning => <UiBox key={earning.id} className="flex flex-wrap items-center justify-between gap-2 py-3 first:pt-0"><UiText className="text-sm"><UiStrong>{earning.driver.name}</UiStrong> · {earning.trip.trip_number} · {earning.trip_date}<UiSpan className="block text-xs text-slate-500">{earning.units} {earning.basis === "Per trip" ? "trip" : "km"} × {money(earning.rate)} · {earning.included_in_settlement ? `Settlement ${earning.settlement_status.toLowerCase().replaceAll("_", " ")}` : "No monthly settlement yet"}</UiSpan></UiText><UiStrong className="text-sm">{money(earning.amount)}</UiStrong></UiBox>)}{earnings.length === 0 && <EmptyState description="No trip earnings yet. Add a policy; the next eligible approved trip will accrue automatically." onAction={()=>void refresh()} actionLabel="Refresh data" />}</UiBox>{earningsPage.controls}</UiSection>
</>}{tool === "draft" && <>    <UiForm onSubmit={event => void createRecord(event)} className="grid gap-3 rounded-xl border border-line bg-white p-5 shadow-sm sm:grid-cols-2 lg:grid-cols-5"><UiBox className="sm:col-span-2 lg:col-span-5"><UiH2 className="font-semibold">Create a monthly settlement</UiH2><UiText className="mt-1 text-xs text-slate-500">Monthly policy salary is filled automatically; enter an amount only for an override or one-off base pay.</UiText></UiBox><UiLabel className="text-xs text-slate-500">Driver<UiSelect className={`${input} mt-1 block w-full`} name="driver_id" required defaultValue=""><option value="" disabled>Select driver</option>{drivers.filter(driver => driver.status === "ACTIVE").map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Salary month<UiInput className={`${input} mt-1 block w-full`} name="period_month" type="month" required defaultValue={new Date().toISOString().slice(0, 7)}/></UiLabel><UiLabel className="text-xs text-slate-500">Monthly base pay (optional)<UiInput className={`${input} mt-1 block w-full`} name="salary_amount" type="number" min="0" step="0.01" placeholder="Use policy rate"/></UiLabel><UiLabel className="text-xs text-slate-500">Note<UiInput className={`${input} mt-1 block w-full`} name="notes" maxLength={240} placeholder="Optional note"/></UiLabel><UiButton disabled={busy === "create" || drivers.length === 0} className="self-end rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "create" ? "Saving…" : "Save draft"}</UiButton></UiForm>
</>}{tool === "advance" && <>    <UiForm onSubmit={event => void createAdvance(event)} className="grid gap-3 rounded-xl border border-line bg-white p-5 shadow-sm sm:grid-cols-2 lg:grid-cols-5"><UiBox className="sm:col-span-2 lg:col-span-5"><UiH2 className="font-semibold">Record a driver advance</UiH2><UiText className="mt-1 text-xs text-slate-500">Record advances only after money has actually been given to the driver.</UiText></UiBox><UiLabel className="text-xs text-slate-500">Driver<UiSelect className={`${input} mt-1 block w-full`} name="driver_id" required defaultValue=""><option value="" disabled>Select driver</option>{drivers.filter(driver => driver.status === "ACTIVE").map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Amount<UiInput className={`${input} mt-1 block w-full`} name="amount" type="number" min="0.01" step="0.01" required/></UiLabel><UiLabel className="text-xs text-slate-500">Given date<UiInput className={`${input} mt-1 block w-full`} name="given_date" type="date" required defaultValue={new Date().toISOString().slice(0, 10)}/></UiLabel><UiLabel className="text-xs text-slate-500">Payment reference<UiInput className={`${input} mt-1 block w-full`} name="reference" placeholder="Cash voucher / UPI ref"/></UiLabel><UiButton disabled={busy === "advance" || drivers.length === 0} className="self-end rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "advance" ? "Recording…" : "Record advance"}</UiButton></UiForm>
    <UiSection className="space-y-3"><UiBox><UiH2 className="font-semibold">Driver advances</UiH2><UiText className="mt-1 text-xs text-slate-500">Allocate recoveries only to an approved salary balance for the same driver. Any excess stays open for a later settlement.</UiText></UiBox>
      {advancesPage.rows.map(advance => {
            const candidates = records.filter(record => record.driver.id === advance.driver.id && ["APPROVED", "PARTIALLY_PAID"].includes(record.status) && Number(record.remaining_amount) > 0);
            return <UiArticle key={advance.id} className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiBox className="flex items-center gap-2"><UiH3 className="font-semibold">{advance.driver.name} · Advance {money(advance.amount)}</UiH3><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${advance.status === "RECOVERED" ? statusClass.SETTLED : statusClass.PARTIALLY_PAID}`}>{advance.status.replaceAll("_", " ")}</UiSpan></UiBox><UiText className="mt-1 text-xs text-slate-500">Given {advance.given_date}{advance.reference ? ` · Ref ${advance.reference}` : ""} · Recovered {money(advance.recovered_amount)} · <UiStrong className="text-ink">Outstanding {money(advance.outstanding_amount)}</UiStrong></UiText>{advance.notes && <UiText className="mt-1 text-xs text-slate-500">{advance.notes}</UiText>}</UiBox></UiBox>
        {Number(advance.outstanding_amount) > 0 && candidates.length > 0 && <UiForm onSubmit={event => void recoverAdvance(event, advance)} className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4"><UiLabel className="text-xs text-slate-500">Salary settlement<UiSelect className={`${input} mt-1 block`} name="salary_record_id" required defaultValue=""><option value="" disabled>Choose approved month</option>{candidates.map(record => <option key={record.id} value={record.id}>{monthLabel(record.period_start)}{record.settlement_number > 1 ? ` · Supplement ${record.settlement_number - 1}` : ""} · remaining {money(record.remaining_amount)}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Recover amount<UiInput className={`${input} mt-1 block w-36`} name="amount" type="number" min="0.01" max={Math.min(Number(advance.outstanding_amount), Math.max(...candidates.map(record => Number(record.remaining_amount))))} step="0.01" required/></UiLabel><UiButton disabled={!!busy} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === advance.id ? "Saving…" : "Allocate recovery"}</UiButton></UiForm>}
        {advance.recoveries.length > 0 && <UiBox className="mt-4 border-t border-line pt-3"><UiH4 className="text-xs font-semibold text-slate-600">Recovery history</UiH4><UiBox className="mt-2 flex flex-wrap gap-x-5 gap-y-2">{advance.recoveries.map(item => <UiText key={item.id} className="text-xs text-slate-500">{monthLabel(item.period_start)} · {money(item.amount)}</UiText>)}</UiBox></UiBox>}
      </UiArticle>;
        })}
      {advances.length === 0 && <UiBox className="rounded-xl border border-dashed border-line bg-white p-6 text-sm text-slate-500">Recorded advances will appear here until fully recovered.</UiBox>}
    {advancesPage.controls}</UiSection>
</>}</div></DialogContent><DialogActions><Button disabled={Boolean(busy)} onClick={() => setTool(null)}>Close</Button></DialogActions></Dialog>
  </UiMain>;
}
