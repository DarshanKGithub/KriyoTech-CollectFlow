"use client";
import { requestConfirmation } from "@/components/product-dialogs";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { ContentSkeleton, PageSkeleton } from "@/components/content-skeleton";
import Autocomplete from "@mui/material/Autocomplete";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import dayjs from "dayjs";
import { ArrowRight, Search, Wallet } from "lucide-react";
import { useListPagination } from "@/components/list-pagination";
import NextLink from "next/link";
import TextField from "@mui/material/TextField";
import { DateField } from "@/components/date-field";
import { UiBox, UiButton, UiForm, UiH1, UiH2, UiMain, UiSection, UiText } from "@/components/product-ui";
import { LiveData } from "@/components/live-data";
import dynamic from "next/dynamic";
import { FormEvent, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
const PaymentRegisterGrid = dynamic(() => import("@/components/payment-register-grid").then(module => module.PaymentRegisterGrid), { ssr: false, loading: () => <ContentSkeleton variant="table" label="Loading payment table" /> });
type Invoice = {
    id: string;
    invoice_number: string;
    vendor: string | null;
    status: string;
    vendor_name?: string;
    supplier_name?: string;
    due_date?: string;
    outstanding_balance: string;
    payment_hold: "missing_supplier" | "unapproved_supplier" | "blocking_exception" | null;
    payment_status: string;
};
type Vendor = {
    id: string;
    name: string;
};
type PayoutInstruction = {
    id:string; invoice_id:string; invoice_number:string; vendor_name:string; amount:string; currency:string;
    status:"AWAITING_APPROVAL"|"APPROVED"|"REJECTED"|"CANCELLED"|"STALE";
    requested_by:string; requested_by_id:string|null; reviewed_by:string; review_note:string; created_at:string;
    execution:string;
};
const paymentModes = { BANK_TRANSFER: "Bank transfer", UPI: "UPI", CHEQUE: "Cheque", CASH: "Cash", OTHER: "Other" };
const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const holdLabels = { missing_supplier: "Supplier missing", unapproved_supplier: "Supplier needs approval", blocking_exception: "Invoice needs review" };

async function loadPaymentQueue(fresh: boolean): Promise<Invoice[]> {
    const invoices: Invoice[] = [];
    for (let page = 1; ; page++) {
        const response = await apiFetch(`/invoices/?status__in=PAYMENT_READY,EXPORTED&payment_status__in=UNPAID,PARTIALLY_PAID&payment_queue=1&page_size=50&page=${page}`, fresh ? { cache: "no-store" } : {});
        if (!response.ok) throw new Error("Could not load invoices ready for payment.");
        const data = await response.json();
        if (Array.isArray(data)) return data;
        invoices.push(...data.results);
        if (!data.next) return invoices;
    }
}

export default function PaymentsPage() {
    const [initialLoading, setInitialLoading] = useState(true);
    const [canRecord,setCanRecord] = useState(false);
    const [canReviewPayout,setCanReviewPayout] = useState(false);
    const [currentUserId,setCurrentUserId] = useState("");
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [payouts,setPayouts]=useState<PayoutInstruction[]>([]);
    const [payoutInvoiceId,setPayoutInvoiceId]=useState("");
    const [payoutAmount,setPayoutAmount]=useState("");
    const [refreshVersion,setRefreshVersion]=useState(0);
    const [invoiceId, setInvoiceId] = useState("");
    const [query, setQuery] = useState("");
    const [dialogError, setDialogError] = useState("");
    const [loadError, setLoadError] = useState("");
    const [amount, setAmount] = useState("");
    const [paidAt, setPaidAt] = useState("");
    const [reference, setReference] = useState("");
    const [mode, setMode] = useState("BANK_TRANSFER");
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const paymentKeys = useRef(new Map<string, string>());
    const paymentInFlight = useRef(false);
    const loadVersion = useRef(0);
    const [supplierId,setSupplierId]=useState("");
    const [supplierReason,setSupplierReason]=useState("");
    const selectedInvoice = invoices.find(row => row.id === invoiceId);
    const supplierName = (invoice: Invoice) => invoice.vendor_name || vendors.find(vendor => vendor.id === invoice.vendor)?.name || invoice.supplier_name || "Supplier missing";
    const invoiceNumber = (invoice: Invoice) => invoice.invoice_number || invoice.id.slice(0, 8);
    const search = query.trim().toLowerCase();
    const filtered = invoices.filter(invoice => [invoiceNumber(invoice), supplierName(invoice)].some(value => value.toLowerCase().includes(search)))
        .sort((a, b) => Number(Boolean(a.payment_hold)) - Number(Boolean(b.payment_hold)));
    const pagination = useListPagination(filtered, search, "Payment queue pages");
    const readyCount = invoices.filter(invoice => !invoice.payment_hold).length;

    function openPayment(invoice: Invoice) {
        setInvoiceId(invoice.id);
        setAmount(invoice.outstanding_balance);
        setPaidAt(dayjs().format("YYYY-MM-DD"));
        setReference("");
        setMode("BANK_TRANSFER");
        setDialogError("");
    }
    useEffect(()=>{setSupplierId("");setSupplierReason("");},[invoiceId]);
    async function correctSupplier(){
        if(busy||!selectedInvoice||selectedInvoice.vendor||!supplierId||supplierReason.trim().length<8)return;
        setBusy(true);
        setDialogError("");
        try{
            if(!await requestConfirmation("Link this supplier and return the invoice for matching and approval?"))return;
            const response=await apiFetch(`/invoices/${selectedInvoice.id}/resolve-missing-supplier/`,{method:"POST",body:JSON.stringify({vendor:supplierId,reason:supplierReason.trim()})});
            const data=await response.json();
            if(!response.ok)throw new Error(data.error?.message||data.detail||"Could not correct the supplier.");
            setInvoiceId("");
            setInvoices(previous => previous.filter(invoice => invoice.id !== selectedInvoice.id));
            await load();setMessage("Supplier linked. Go to Invoices → Review → Save corrections → Run match → Submit approval. A separate approver must approve it again before you record payment.");
        }catch(error){setDialogError(error instanceof Error?error.message:"Could not correct the supplier.");}finally{setBusy(false);}
    }
    async function load(silent = false) {
        const version = ++loadVersion.current;
        try {
            const [queue, vr, profileResponse, payoutResponse] = await Promise.all([
                loadPaymentQueue(!silent), apiFetch("/vendors"), apiFetch("/auth/me"), apiFetch("/payments/instructions"),
            ]);
            if (!vr.ok) throw new Error("Could not load suppliers.");
            const [supplierRows, profile, instructions] = await Promise.all([
                vr.json(), profileResponse.ok ? profileResponse.json() : null, payoutResponse.ok ? payoutResponse.json() : null,
            ]);
            if (version !== loadVersion.current) return;
            setInvoices(queue);
            setLoadError("");
            setVendors(supplierRows);
            if(instructions) setPayouts(instructions.results || []);
            setRefreshVersion(value=>value+1);
            setCurrentUserId(profile?.id || "");
            setCanRecord(["OWNER", "FINANCE"].includes(profile?.role));
            setCanReviewPayout(["OWNER", "FINANCE", "APPROVER"].includes(profile?.role));
        }
        catch (e) {
            if (version !== loadVersion.current) return;
            if (silent)
                throw e;
            setLoadError(e instanceof Error ? e.message : "Could not load payment register.");
        }
    }
    useEffect(() => { void load().finally(() => setInitialLoading(false)); }, []);
    async function requestPayout(e:FormEvent<HTMLFormElement>){
        e.preventDefault();if(!payoutInvoiceId||!payoutAmount||busy)return;
        const invoice=invoices.find(row=>row.id===payoutInvoiceId);if(!invoice)return;
        if(!await requestConfirmation(`Request approval to pay INR ${payoutAmount} to ${invoice.vendor_name||"this supplier"} for invoice ${invoice.invoice_number}? This creates an internal instruction only; it will not transfer money.`))return;
        setBusy(true);try{const response=await apiFetch("/payments/instructions",{method:"POST",body:JSON.stringify({invoice_id:payoutInvoiceId,amount:payoutAmount,idempotency_key:crypto.randomUUID()})});const data=await response.json();if(!response.ok)throw new Error(data.error||data.detail||"Could not request payout approval.");setPayoutInvoiceId("");setPayoutAmount("");await load(true);setMessage("Payout instruction submitted for independent approval. No transfer was sent.");}catch(error){setMessage(error instanceof Error?error.message:"Could not request payout approval.");}finally{setBusy(false);}
    }
    async function decidePayout(row:PayoutInstruction,decision:"APPROVE"|"REJECT"){
        if(row.requested_by_id===currentUserId){setMessage("The requester cannot review their own payout instruction.");return;}
        const note=decision==="REJECT"?window.prompt("Reason for rejecting this payout (at least 8 characters):")||"":"Approved after independent review";
        if(decision==="REJECT"&&note.trim().length<8){setMessage("Enter a rejection reason with at least 8 characters.");return;}
        if(decision==="APPROVE"&&!await requestConfirmation(`Approve INR ${row.amount} for ${row.vendor_name}? This is internal approval only; no transfer will be sent.`))return;
        setBusy(true);try{const response=await apiFetch(`/payments/instructions/${row.id}/decision`,{method:"POST",body:JSON.stringify({decision,note})});const data=await response.json();if(!response.ok)throw new Error(data.error||data.detail||"Could not review payout instruction.");await load(true);setMessage(decision==="APPROVE"?"Instruction approved internally. Connect a payment provider before any transfer can be sent.":"Payout instruction rejected with an audit reason.");}catch(error){setMessage(error instanceof Error?error.message:"Could not review payout instruction.");}finally{setBusy(false);}
    }
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!canRecord || busy || paymentInFlight.current || !selectedInvoice?.vendor || selectedInvoice.payment_hold) return;
        const invoice = selectedInvoice;
        if (!/^\d{4}-\d{2}-\d{2}$/.test(paidAt)) {
            setDialogError("Choose a valid payment date.");
            return;
        }
        paymentInFlight.current = true;
        setBusy(true);
        setDialogError("");
        try {
            if (!await requestConfirmation(`Record ${currency.format(Number(amount))} paid to ${supplierName(invoice)} for invoice ${invoiceNumber(invoice)}?`)) return;
            const payload = { vendor: invoice.vendor, amount, paid_at: paidAt, reference_number: reference, mode, allocations: [{ invoice: invoice.id, amount }] };
            const signature = JSON.stringify(payload);
            const key = paymentKeys.current.get(signature) ?? crypto.randomUUID();
            paymentKeys.current.set(signature, key);
            const response = await apiFetch("/payments", { method: "POST", body: JSON.stringify({ ...payload, idempotency_key: key }) });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error?.message || data.detail || Object.values(data).flat().join(" ") || "Could not record payment.");
            paymentKeys.current.delete(signature);
            setInvoiceId("");
            setInvoices(previous => previous.filter(row => row.id !== invoice.id));
            setMessage(`Payment recorded and allocated to invoice ${invoiceNumber(invoice)}.`);
            await load();
        } catch (error) {
            setDialogError(error instanceof Error ? error.message : "Could not record payment.");
        } finally {
            setBusy(false);
            paymentInFlight.current = false;
        }
    }

    if (initialLoading) return <PageSkeleton variant="table" label="Loading payment workspace" />;

    return <UiMain className="w-full min-w-0 px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
            <div>
                <UiH1 className="text-3xl font-bold tracking-tight text-slate-900">Payments</UiH1>
                <UiText className="mt-1 text-sm text-slate-600">See what’s due and record payments you’ve already made.</UiText>
            </div>
            <LiveData compact onRefresh={() => load(true)} paused={busy || Boolean(invoiceId)} />
        </header>
        {message && <WorkflowFeedback message={message} onRefresh={() => load()} />}
        {loadError && <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" onClick={() => void load()}>Retry</Button>}>{loadError}</Alert>}
        <UiSection className="overflow-hidden rounded-xl border border-line bg-white shadow-card" aria-labelledby="payment-queue">
            <div className="flex flex-wrap items-center justify-between gap-4 p-4 sm:px-5">
                <div className="flex items-center gap-3">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-800"><Wallet size={20} /></span>
                    <div>
                        <UiH2 id="payment-queue" className="text-base font-bold text-slate-900">Invoices to pay</UiH2>
                        {!loadError && <UiText className="text-sm text-slate-600">{readyCount} ready{invoices.length > readyCount && ` · ${invoices.length - readyCount} need attention`}</UiText>}
                    </div>
                </div>
                <label className="flex w-full items-center gap-2 rounded-lg border border-line px-3 text-slate-500 focus-within:ring-2 focus-within:ring-emerald-700 sm:w-72">
                    <Search size={17} className="shrink-0" aria-hidden />
                    <span className="sr-only">Search by invoice number or supplier</span>
                    <input type="search" className="min-w-0 flex-1 bg-transparent py-2.5 text-sm text-slate-900 outline-none" placeholder="Invoice number or supplier" value={query} onChange={event => setQuery(event.target.value)} />
                </label>
            </div>
            {pagination.rows.length ? <>
                <div aria-hidden className="hidden border-y border-line bg-slate-50 px-5 py-2.5 text-xs font-semibold text-slate-600 md:grid md:grid-cols-[minmax(0,2fr)_1fr_1fr_1fr_11rem] md:gap-4">
                    <span>Invoice / Supplier</span><span>Due date</span><span>Status</span><span className="text-right">Balance due</span>
                </div>
                <ul className="divide-y divide-slate-200 border-t border-line md:border-t-0">
                    {pagination.rows.map(invoice => <li key={invoice.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-4 md:grid-cols-[minmax(0,2fr)_1fr_1fr_1fr_11rem] md:px-5">
                        <div className="min-w-0 break-words text-sm">
                            <div className="font-bold text-slate-900">{invoiceNumber(invoice)}</div>
                            <div className="mt-0.5 text-slate-600">{supplierName(invoice)}</div>
                        </div>
                        <div className="col-start-1 row-start-2 text-sm text-slate-600 md:col-auto md:row-auto">
                            <span className="md:sr-only">Due </span>{invoice.due_date ? dateFormat.format(new Date(invoice.due_date)) : "—"}
                        </div>
                        <div className="row-start-3 md:row-auto">
                            <span className={`inline-block rounded-md px-2 py-1 text-xs font-semibold ${invoice.payment_hold ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-900"}`}>
                                {invoice.payment_hold ? holdLabels[invoice.payment_hold] : invoice.payment_status === "PARTIALLY_PAID" ? "Partially paid" : "Ready to pay"}
                            </span>
                        </div>
                        <div className="col-start-2 row-start-1 text-right text-sm font-bold tabular-nums md:col-auto md:row-auto">
                            <span className="sr-only">Balance due </span>{currency.format(Number(invoice.outstanding_balance))}
                        </div>
                        <div className="col-start-2 row-start-3 justify-self-end md:col-auto md:row-auto">
                            {canRecord && !invoice.payment_hold && <Button size="small" variant="contained" endIcon={<ArrowRight size={15} />} disabled={busy} onClick={() => openPayment(invoice)} aria-label={`Record payment for invoice ${invoiceNumber(invoice)}`}>Record payment</Button>}
                            {canRecord && invoice.payment_hold === "missing_supplier" && invoice.status === "PAYMENT_READY" && invoice.payment_status === "UNPAID" &&
                                <Button size="small" variant="outlined" disabled={busy} onClick={() => openPayment(invoice)}>Link supplier</Button>}
                            {invoice.payment_hold === "unapproved_supplier" && <Button size="small" component={NextLink} href="/vendors">View suppliers</Button>}
                            {(invoice.payment_hold === "blocking_exception" || (invoice.payment_hold === "missing_supplier" && (invoice.status !== "PAYMENT_READY" || invoice.payment_status !== "UNPAID"))) &&
                                <Button size="small" component={NextLink} href="/invoices">Open invoices</Button>}
                        </div>
                    </li>)}
                </ul>
                {filtered.length > 10 && pagination.controls}
            </> : !loadError && <div className="border-t border-line px-4 py-10 text-center">
                <p className="font-semibold text-slate-900">{invoices.length ? "No matching invoices" : "No invoices to pay"}</p>
                <p className="mt-1 text-sm text-slate-600">{invoices.length ? "Try a different invoice number or supplier." : "Approved invoices with an outstanding balance will appear here."}</p>
            </div>}
        </UiSection>

        <Dialog open={Boolean(invoiceId && selectedInvoice && canRecord)} onClose={busy ? undefined : () => setInvoiceId("")} fullWidth maxWidth="sm" aria-labelledby="payment-dialog-title">
            {selectedInvoice && <form onSubmit={submit}>
                <DialogTitle id="payment-dialog-title">{selectedInvoice.vendor ? "Record payment" : "Link supplier"}</DialogTitle>
                <DialogContent dividers>
                    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-4">
                        <div className="min-w-0 break-words">
                            <div className="font-semibold text-slate-900">{invoiceNumber(selectedInvoice)}</div>
                            <div className="text-sm text-slate-600">{supplierName(selectedInvoice)}</div>
                        </div>
                        <div>
                            <div className="text-xs text-slate-600">Balance due</div>
                            <div className="text-lg font-bold tabular-nums text-slate-900">{currency.format(Number(selectedInvoice.outstanding_balance))}</div>
                        </div>
                    </div>
                    {selectedInvoice.vendor ? <>
                        <p className="mb-4 text-sm text-slate-600">Enter the details of a payment already made to this supplier.</p>
                        <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
                            <TextField autoFocus name="amount" label="Amount paid (INR)" required type="number" size="small" value={amount}
                                slotProps={{ htmlInput: { min: "0.01", max: selectedInvoice.outstanding_balance, step: "0.01" } }} onChange={event => setAmount(event.target.value)} />
                            <DateField label="Payment date" required value={paidAt} onChange={setPaidAt} disabled={busy} />
                            <TextField select label="Payment method" size="small" value={mode} onChange={event => setMode(event.target.value)} slotProps={{ select: { native: true } }}>
                                {Object.entries(paymentModes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                            </TextField>
                            <TextField name="reference_number" label="Reference (optional)" placeholder="Bank UTR or cheque number" size="small" value={reference} onChange={event => setReference(event.target.value)} />
                        </fieldset>
                    </> : <>
                        <Alert severity="warning" sx={{ mb: 2 }}>Linking a supplier sends this invoice back for matching and approval.</Alert>
                        <div className="grid gap-4">
                            <Autocomplete options={vendors} value={vendors.find(vendor => vendor.id === supplierId) || null} isOptionEqualToValue={(a, b) => a.id === b.id} getOptionLabel={vendor => vendor.name}
                                onChange={(_, vendor) => setSupplierId(vendor?.id || "")} disabled={busy} renderInput={params => <TextField {...params} label="Correct supplier" />} />
                            <TextField label="Reason for correction" value={supplierReason} onChange={event => setSupplierReason(event.target.value)} disabled={busy} helperText="At least 8 characters. Saved to the audit log." />
                            <NextLink href="/vendors" className="text-sm font-semibold text-forest">Manage suppliers</NextLink>
                        </div>
                    </>}
                    {dialogError && <Alert severity="error" sx={{ mt: 2 }}>{dialogError}</Alert>}
                </DialogContent>
                <DialogActions sx={{ px: 3, py: 2 }}>
                    <Button type="button" disabled={busy} onClick={() => setInvoiceId("")}>Cancel</Button>
                    {selectedInvoice.vendor
                        ? <Button type="submit" variant="contained" disabled={busy || Boolean(selectedInvoice.payment_hold)}>{busy ? "Saving…" : "Record payment"}</Button>
                        : <Button type="button" variant="contained" disabled={busy || !supplierId || supplierReason.trim().length < 8} onClick={() => void correctSupplier()}>Link and return to review</Button>}
                </DialogActions>
            </form>}
        </Dialog>
        <UiSection className="mt-6 overflow-hidden rounded-xl border border-line bg-white"><UiBox className="border-b border-line px-5 py-4"><UiH2 className="text-sm font-bold">Recorded payments</UiH2></UiBox><PaymentRegisterGrid refreshVersion={refreshVersion} vendors={vendors}/></UiSection>
        <UiSection className="mt-6 rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Supplier payout instructions</UiH2><UiText className="mt-1 text-sm text-slate-500">Request a separate approval for a ready invoice. Approval is internal only; no bank or PSP transfer is connected yet.</UiText>{canRecord&&<UiForm onSubmit={requestPayout} className="mt-4 grid gap-3 md:grid-cols-[minmax(260px,2fr)_1fr_auto]"><Autocomplete options={invoices.filter(invoice => !invoice.payment_hold)} value={invoices.find(invoice=>invoice.id===payoutInvoiceId)||null} isOptionEqualToValue={(a,b)=>a.id===b.id} getOptionLabel={invoice=>`${invoice.invoice_number||invoice.id.slice(0,8)} · ${invoice.vendor_name||vendors.find(vendor=>vendor.id===invoice.vendor)?.name||"Supplier"}`} onChange={(_,invoice)=>{setPayoutInvoiceId(invoice?.id||"");setPayoutAmount("");}} renderInput={params=><TextField {...params} label="Approved invoice" size="small" helperText="Choose an invoice with an approved supplier; enter the amount to request."/>}/><TextField label="Amount (INR)" required type="number" slotProps={{htmlInput:{min:"0.01",step:"0.01"}}} value={payoutAmount} onChange={event=>setPayoutAmount(event.target.value)} size="small"/><UiButton disabled={busy||!payoutInvoiceId||!payoutAmount} className="bg-forest px-4 text-white">Request approval</UiButton></UiForm>}{payouts.length>0&&<UiBox className="mt-5 space-y-2">{payouts.map(row=><UiBox key={row.id} className="flex flex-col gap-3 rounded-lg border border-line p-3 md:flex-row md:items-center md:justify-between"><UiBox><UiText className="text-sm font-semibold">{row.invoice_number} · {row.vendor_name} · {row.currency} {row.amount}</UiText><UiText className="mt-1 text-xs text-slate-500">{row.status.replaceAll("_"," ")} · requested by {row.requested_by} · {row.execution}</UiText>{row.review_note&&<UiText className="mt-1 text-xs">Review note: {row.review_note}</UiText>}</UiBox>{canReviewPayout&&row.status==="AWAITING_APPROVAL"&&row.requested_by_id!==currentUserId&&<UiBox className="flex gap-2"><UiButton type="button" disabled={busy} onClick={()=>void decidePayout(row,"APPROVE")} className="bg-forest px-3 text-white">Approve</UiButton><UiButton type="button" disabled={busy} onClick={()=>void decidePayout(row,"REJECT")} className="border border-line px-3">Reject</UiButton></UiBox>}</UiBox>)}</UiBox>}</UiSection>
    </UiMain>;
}
