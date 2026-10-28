"use client";
import { requestConfirmation } from "@/components/product-dialogs";
import { applyFieldErrors } from "@/components/form-validation";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { ContentSkeleton, PageSkeleton } from "@/components/content-skeleton";
import Autocomplete from "@mui/material/Autocomplete";
import Alert from "@mui/material/Alert";
import NextLink from "next/link";
import TextField from "@mui/material/TextField";
import { DateField } from "@/components/date-field";
import { UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiText } from "@/components/product-ui";
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
    invoice_total: string;
    payment_status: string;
};
type Vendor = {
    id: string;
    name: string;
};
type Payment = {
    id: string;
    vendor: string | null;
    amount: string;
    reference_number: string;
    mode: string;
    paid_at: string;
    allocations: {
        invoice: string;
        amount: string;
    }[];
};
type PayoutInstruction = {
    id:string; invoice_id:string; invoice_number:string; vendor_name:string; amount:string; currency:string;
    status:"AWAITING_APPROVAL"|"APPROVED"|"REJECTED"|"CANCELLED"|"STALE";
    requested_by:string; requested_by_id:string|null; reviewed_by:string; review_note:string; created_at:string;
    execution:string;
};
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
    const [amount, setAmount] = useState("");
    const [paidAt, setPaidAt] = useState(new Date().toISOString().slice(0, 10));
    const [reference, setReference] = useState("");
    const [mode, setMode] = useState("BANK_TRANSFER");
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const idempotencyKey = useRef("");
    const paymentInFlight = useRef(false);
    const invoiceInput = useRef<HTMLInputElement>(null);
    const [invoiceError,setInvoiceError] = useState("");
    const [supplierId,setSupplierId]=useState("");
    const [supplierReason,setSupplierReason]=useState("");
    const selectedInvoice=invoices.find(row=>row.id===invoiceId);
    useEffect(()=>{setSupplierId("");setSupplierReason("");},[invoiceId]);
    async function correctSupplier(){
        if(busy||!selectedInvoice||selectedInvoice.vendor||!supplierId||supplierReason.trim().length<8)return;
        if(!await requestConfirmation("Link this supplier and return the invoice for review? Matching and approval must be completed again before payment can be recorded."))return;
        setBusy(true);
        try{
            const response=await apiFetch(`/invoices/${selectedInvoice.id}/resolve-missing-supplier/`,{method:"POST",body:JSON.stringify({vendor:supplierId,reason:supplierReason.trim()})});
            const data=await response.json();
            if(!response.ok)throw new Error(data.error?.message||data.detail||"Could not correct the supplier.");
            setInvoiceId("");setAmount("");setReference("");idempotencyKey.current="";
            await load();setMessage("Supplier linked. Go to Invoices → Review → Save corrections → Run match → Submit approval. A separate approver must approve it again before you record payment.");
        }catch(error){setMessage(error instanceof Error?error.message:"Could not correct the supplier.");}finally{setBusy(false);}
    }
    async function load(silent = false) {
        try {
            const [ir, vr, profileResponse, payoutResponse] = await Promise.all([apiFetch("/invoices/?status__in=PAYMENT_READY,EXPORTED&payment_status__in=UNPAID,PARTIALLY_PAID"), apiFetch("/vendors"),apiFetch("/auth/me"),apiFetch("/payments/instructions")]);
            if (!ir.ok || !vr.ok)
                throw new Error("Could not load payment workspace data.");
            const idata = await ir.json();
            const irows = Array.isArray(idata) ? idata : idata.results || [];
            setInvoices(irows.filter((i: Invoice) => ["PAYMENT_READY", "EXPORTED"].includes(i.status) && i.payment_status !== "PAID" && i.payment_status !== "CANCELLED"));
            setVendors(await vr.json());
            if(payoutResponse.ok){const payoutData=await payoutResponse.json();setPayouts(payoutData.results||[]);}
            setRefreshVersion(value=>value+1);
            if(profileResponse.ok){const profile=await profileResponse.json();setCurrentUserId(profile.id||"");setCanRecord(["OWNER","FINANCE"].includes(profile.role));setCanReviewPayout(["OWNER","FINANCE","APPROVER"].includes(profile.role));}
            if (!silent)
                setMessage("");
        }
        catch (e) {
            if (silent)
                throw e;
            setMessage(e instanceof Error ? e.message : "Could not load payment register.");
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
    async function submit(e: FormEvent<HTMLFormElement>) {
        e.preventDefault();
        if (paymentInFlight.current) return;
        const formElement = e.currentTarget;
        const invoice = invoices.find(i => i.id === invoiceId);
        if (!invoice) {
            setInvoiceError("Choose an invoice from the list with an outstanding balance.");
            invoiceInput.current?.focus();
            setMessage("Choose an invoice with an outstanding balance.");
            return;
        }
        if(!invoice.vendor){setMessage("Link the correct supplier below and send this invoice through review and approval again before recording payment.");return;}
        if(!/^\d{4}-\d{2}-\d{2}$/.test(paidAt)){setMessage("Choose a valid payment date.");return;}
        paymentInFlight.current = true;
        setBusy(true);
        if (!await requestConfirmation(`Record INR ${amount} paid to ${invoice.vendor_name || "this supplier"} against invoice ${invoice.invoice_number || invoice.id}? This records an existing payment; it does not initiate a bank transfer.`)) { paymentInFlight.current = false; setBusy(false); return; }
        setBusy(true);
        setMessage("");
        if (!idempotencyKey.current)
            idempotencyKey.current = crypto.randomUUID();
        try {
            const r = await apiFetch("/payments", { method: "POST", body: JSON.stringify({ idempotency_key: idempotencyKey.current, vendor: invoice.vendor, amount, paid_at: paidAt, reference_number: reference, mode, allocations: [{ invoice: invoice.id, amount }] }) });
            const d = await r.json();
            if (!r.ok) {
                applyFieldErrors(formElement, d);
                throw new Error(d.error?.message || Object.values(d).flat().join(" ") || "Could not record payment.");
            }
            idempotencyKey.current = "";
            setInvoiceId("");
            setAmount("");
            setReference("");
            await load();
            setMessage("Payment recorded and allocated to the invoice.");
        }
        catch (err) {
            setMessage(err instanceof Error ? err.message : "Could not record payment.");
        }
        finally {
            setBusy(false);
            paymentInFlight.current = false;
        }
    }
    if (initialLoading) return <PageSkeleton variant="form" label="Loading payment workspace" />;
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><UiText className="text-[10px] font-bold uppercase tracking-[.18em] text-forest">Payables</UiText><UiH1 className="mt-2 text-2xl font-bold">Payment register</UiH1><UiText className="mt-1 text-sm text-slate-500">Record payments and allocate them against approved invoices. KriyoPay records payments; it does not initiate bank transfers.</UiText>{message && <WorkflowFeedback message={message} onRefresh={()=>load()} />}<LiveData onRefresh={() => load(true)} paused={busy || Boolean(invoiceId || amount || reference)}/>{canRecord&&<UiForm onSubmit={submit} className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-5 shadow-card md:grid-cols-5"><UiBox className="md:col-span-2"><Autocomplete options={invoices} value={invoices.find(invoice=>invoice.id===invoiceId)||null} isOptionEqualToValue={(a,b)=>a.id===b.id}
 getOptionLabel={invoice=>`${invoice.invoice_number||invoice.id.slice(0,8)} · ${invoice.vendor_name||vendors.find(v=>v.id===invoice.vendor)?.name||"Supplier"} · ₹${invoice.invoice_total} (${invoice.payment_status})`}
 onChange={(_,invoice)=>{setInvoiceError("");setInvoiceId(invoice?.id||"");setAmount(invoice&&invoice.payment_status!=="PARTIALLY_PAID"?invoice.invoice_total:"");}}
 onInputChange={(_,__,reason)=>{if(reason==="input")setInvoiceId("");}}
 renderInput={params=><TextField {...params} inputRef={invoiceInput} error={Boolean(invoiceError)} helperText={invoiceError || "Select an approved invoice with an outstanding balance."} onInvalid={event=>{event.preventDefault();setInvoiceError("Choose an invoice from the list.");}} required label="Invoice" placeholder="Search an approved invoice" size="small"/>}/></UiBox><UiLabel className="text-xs font-semibold">Amount<UiInput name="amount" helperText="Enter the amount paid against this invoice." required type="number" min="0.01" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} className="mt-2 block w-full rounded-lg border border-line px-3 py-2.5 text-sm font-normal"/></UiLabel><UiLabel className="text-xs font-semibold">Payment date<DateField required value={paidAt} onChange={setPaidAt} className="mt-2 block w-full rounded-lg border border-line px-3 py-2.5 text-sm font-normal"/></UiLabel><UiLabel className="text-xs font-semibold">Payment mode<UiSelect value={mode} onChange={e => setMode(e.target.value)} className="mt-2 block w-full rounded-lg border border-line bg-white px-3 py-2.5 text-xs font-normal">{["BANK_TRANSFER", "UPI", "CHEQUE", "CASH", "OTHER"].map(x => <option key={x}>{x}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold md:col-span-3">Reference number<UiInput name="reference_number" value={reference} onChange={e => setReference(e.target.value)} className="mt-2 block w-full rounded-lg border border-line px-3 py-2.5 text-sm font-normal" placeholder="Bank UTR / cheque number"/></UiLabel><UiBox className="flex items-end"><UiButton disabled={busy || !selectedInvoice?.vendor} className="rounded-lg bg-forest px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-50">{busy ? "Recording…" : "Record payment"}</UiButton></UiBox></UiForm>}{canRecord&&selectedInvoice&&!selectedInvoice.vendor&&<Alert severity="warning" sx={{mt:2}}><UiH2 className="text-sm font-semibold">Link a supplier before payment</UiH2><UiText className="mt-1 text-sm">Invoice {selectedInvoice.invoice_number} has no linked supplier{selectedInvoice.supplier_name?` (extracted name: ${selectedInvoice.supplier_name})`:""}. Select the correct supplier. This correction returns the invoice for matching and approval; no payment will be recorded.</UiText><UiBox className="mt-4 grid items-start gap-3 md:grid-cols-3"><Autocomplete options={vendors} value={vendors.find(vendor=>vendor.id===supplierId)||null} isOptionEqualToValue={(a,b)=>a.id===b.id} getOptionLabel={vendor=>vendor.name} onChange={(_,vendor)=>setSupplierId(vendor?.id||"")} disabled={busy} renderInput={params=><TextField {...params} label="Correct supplier"/>}/><TextField label="Reason for correction" value={supplierReason} onChange={event=>setSupplierReason(event.target.value)} disabled={busy} helperText="At least 8 characters; recorded in audit history."/><UiButton type="button" disabled={busy||!supplierId||supplierReason.trim().length<8} onClick={()=>void correctSupplier()} className="border border-line">Link supplier & return to review</UiButton></UiBox><UiText className="mt-3 text-xs">Supplier not listed? Add it in <NextLink href="/vendors" className="underline">Vendors</NextLink>, then refresh this page.</UiText></Alert>}
<UiSection className="mt-6 rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Supplier payout instructions</UiH2><UiText className="mt-1 text-sm text-slate-500">Request a separate approval for a ready invoice. Approval is internal only; no bank or PSP transfer is connected yet.</UiText>{canRecord&&<UiForm onSubmit={requestPayout} className="mt-4 grid gap-3 md:grid-cols-[minmax(260px,2fr)_1fr_auto]"><Autocomplete options={invoices.filter(invoice=>Boolean(invoice.vendor))} value={invoices.find(invoice=>invoice.id===payoutInvoiceId)||null} isOptionEqualToValue={(a,b)=>a.id===b.id} getOptionLabel={invoice=>`${invoice.invoice_number||invoice.id.slice(0,8)} · ${invoice.vendor_name||vendors.find(vendor=>vendor.id===invoice.vendor)?.name||"Supplier"}`} onChange={(_,invoice)=>{setPayoutInvoiceId(invoice?.id||"");setPayoutAmount("");}} renderInput={params=><TextField {...params} label="Approved invoice" size="small" helperText="Choose an invoice with an approved supplier; enter the amount to request."/>}/><TextField label="Amount (INR)" required type="number" slotProps={{htmlInput:{min:"0.01",step:"0.01"}}} value={payoutAmount} onChange={event=>setPayoutAmount(event.target.value)} size="small"/><UiButton disabled={busy||!payoutInvoiceId||!payoutAmount} className="bg-forest px-4 text-white">Request approval</UiButton></UiForm>}{payouts.length>0&&<UiBox className="mt-5 space-y-2">{payouts.map(row=><UiBox key={row.id} className="flex flex-col gap-3 rounded-lg border border-line p-3 md:flex-row md:items-center md:justify-between"><UiBox><UiText className="text-sm font-semibold">{row.invoice_number} · {row.vendor_name} · {row.currency} {row.amount}</UiText><UiText className="mt-1 text-xs text-slate-500">{row.status.replaceAll("_"," ")} · requested by {row.requested_by} · {row.execution}</UiText>{row.review_note&&<UiText className="mt-1 text-xs">Review note: {row.review_note}</UiText>}</UiBox>{canReviewPayout&&row.status==="AWAITING_APPROVAL"&&row.requested_by_id!==currentUserId&&<UiBox className="flex gap-2"><UiButton type="button" disabled={busy} onClick={()=>void decidePayout(row,"APPROVE")} className="bg-forest px-3 text-white">Approve</UiButton><UiButton type="button" disabled={busy} onClick={()=>void decidePayout(row,"REJECT")} className="border border-line px-3">Reject</UiButton></UiBox>}</UiBox>)}</UiBox>}</UiSection>
<UiSection className="mt-8 overflow-hidden rounded-xl border border-line bg-white"><UiBox className="border-b border-line px-5 py-4"><UiH2 className="text-sm font-bold">Recorded payments</UiH2></UiBox><PaymentRegisterGrid refreshVersion={refreshVersion} vendors={vendors}/></UiSection></UiMain>;
}
