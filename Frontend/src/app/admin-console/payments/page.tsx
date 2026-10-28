"use client";
import { PageSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiModal, UiSelect, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/admin/admin-ui";
import { useListPagination } from "@/components/list-pagination";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { minorUnits } from "@/lib/finance";
import { apiFetch } from "@/lib/api";
import { AdminDataTable } from "../data-table";
type Payment = {
    id: string;
    tenant_name: string;
    amount: number;
    currency: string;
    status: string;
    razorpay_payment_id: string;
    razorpay_order_id: string;
    payment_method: string;
    offline_reference: string;
    paid_at: string | null;
    created_at: string;
};
type Company = {
    id: string;
    name: string;
};
type Plan = {
    id: string;
    name: string;
};
const money = (paise: number, currency = "INR") => new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(paise / 100);
export default function PaymentsPage() {
    const [payments, setPayments] = useState<Payment[]>([]);
    const [companies, setCompanies] = useState<Company[]>([]);
    const [plans, setPlans] = useState<Plan[]>([]);
    const [role, setRole] = useState("");
    const [offlineOpen, setOfflineOpen] = useState(false);
    const [refundPayment, setRefundPayment] = useState<Payment | null>(null);
    const [message, setMessage] = useState("");
    const [initialLoading, setInitialLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const canManage = role === "SUPER_ADMIN" || role === "BILLING_ADMIN";
    const load = useCallback(async () => { const [paymentResponse, companyResponse, planResponse, meResponse] = await Promise.all([apiFetch("/admin/payments"), apiFetch("/admin/companies?page_size=100"), apiFetch("/admin/plans"), apiFetch("/admin/auth/me")]); if (paymentResponse.ok)
        setPayments((await paymentResponse.json()).results); if (companyResponse.ok)
        setCompanies((await companyResponse.json()).results); if (planResponse.ok)
        setPlans(await planResponse.json()); if (meResponse.ok)
        setRole((await meResponse.json()).role); }, []);
    useEffect(() => { void load().catch(() => setMessage("Could not load admin payments. Please refresh to retry.")).finally(() => setInitialLoading(false)); }, [load]);
    useEffect(() => {
        let active = true;
        const refreshPayments = async () => {
            try {
                const response = await apiFetch("/admin/payments");
                if (response.ok && active)
                    setPayments((await response.json()).results);
            }
            catch { /* Preserve the latest payment list during a temporary outage. */ }
        };
        const refresh = () => { if (document.visibilityState === "visible")
            void refreshPayments(); };
        const timer = window.setInterval(refresh, 15000);
        window.addEventListener("focus", refresh);
        return () => { active = false; window.clearInterval(timer); window.removeEventListener("focus", refresh); };
    }, []);
    async function recordOffline(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const formElement = event.currentTarget; setBusy(true); setMessage(""); const form = new FormData(formElement); const payload = Object.fromEntries([...form.entries()].map(([key, value]) => [key, String(value)])); payload.amount = String(Math.round(Number(payload.amount) * 100)); const response = await apiFetch("/admin/payments/offline", { method: "POST", body: JSON.stringify(payload) }); const result = await response.json(); setBusy(false); if (!response.ok) {
        setMessage(result.error || "Could not record payment.");
        return;
    } setMessage("Offline payment recorded and subscription activated."); setOfflineOpen(false); formElement.reset(); void load(); }
    async function submitRefund(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!refundPayment || busy) return;
        const form = new FormData(event.currentTarget);
        const amount = String(form.get("amount") || "").trim();
        const reason = String(form.get("reason") || "");
        const storageKey = `kriyopay_refund_intent_${refundPayment.id}`;
        let key = sessionStorage.getItem(storageKey);
        if (!key) { key = crypto.randomUUID(); sessionStorage.setItem(storageKey, key); }
        const payload: Record<string, string | number> = { reason, idempotency_key: key };
        try { if (amount) payload.amount = minorUnits(amount).toString(); }
        catch { setMessage("Enter an amount with at most two decimal places."); return; }
        setBusy(true); setMessage("");
        try {
            const response = await apiFetch(`/admin/payments/${refundPayment.id}/refund`, { method: "POST", body: JSON.stringify(payload) });
            const result = await response.json();
            if (!response.ok) {
                setMessage(typeof result.error === "string" ? result.error : typeof result.detail === "string" ? result.detail : "Refund request could not be accepted. Keep the same amount and reason when retrying.");
                return;
            }
            if (["UNKNOWN", "SUBMITTING", "RESERVED"].includes(result.status)) {
                setMessage(result.message || "Provider outcome is unknown. Submit the same request to check its status; do not create a second refund.");
                return;
            }
            sessionStorage.removeItem(storageKey);
            setMessage(`Refund ${result.razorpay_refund_id || result.intent_id}: ${String(result.status).toLowerCase()}.`);
            setRefundPayment(null); void load();
        } catch {
            setMessage("Could not confirm the refund response. Retry with the same amount and reason to check the existing request.");
        } finally { setBusy(false); }
    }
    const pagination = useListPagination(payments, "");
    if (initialLoading) return <PageSkeleton variant="table" label="Loading admin payments" />;
    return <><UiBox className="flex flex-wrap items-end justify-between gap-4"><UiBox><UiText className="text-[10px] font-bold uppercase tracking-[.15em] text-forest">Billing operations</UiText><UiH1 className="mt-2 text-3xl font-bold">Payments</UiH1><UiText className="mt-2 text-sm text-slate-500">Verified Razorpay payments, bank transfers, refunds, and provider events.</UiText></UiBox>{canManage && <UiButton onClick={() => setOfflineOpen(!offlineOpen)} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white">Record bank transfer</UiButton>}</UiBox>
    {message && <UiAlert role="status" className="mt-4 rounded-lg border border-line bg-white p-3 text-sm">{message}</UiAlert>}
    {offlineOpen && canManage && <UiForm onSubmit={recordOffline} className="mt-5 rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Record offline payment</UiH2><UiText className="mt-1 text-xs text-slate-500">Enter the settled bank receipt details. This activates the selected plan and creates a billing receipt.</UiText><UiBox className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><UiLabel className="text-xs font-semibold">Company<UiSelect name="tenant_id" required className="mt-1 block min-h-10 w-full rounded-lg border border-line bg-white px-2 text-sm">{companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold">Plan<UiSelect name="plan_id" required className="mt-1 block min-h-10 w-full rounded-lg border border-line bg-white px-2 text-sm">{plans.filter(p => p.name.toLowerCase() !== "trial").map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold">Billing cycle<UiSelect name="billing_cycle" className="mt-1 block min-h-10 w-full rounded-lg border border-line bg-white px-2 text-sm"><option>MONTHLY</option><option>QUARTERLY</option><option>ANNUAL</option></UiSelect></UiLabel><UiLabel className="text-xs font-semibold">Amount (₹)<UiInput name="amount" required type="number" min="0.01" step="0.01" className="mt-1 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel><UiLabel className="text-xs font-semibold">Method<UiSelect name="payment_method" className="mt-1 block min-h-10 w-full rounded-lg border border-line bg-white px-2 text-sm"><option value="BANK_TRANSFER">Bank transfer</option><option value="NEFT">NEFT</option><option value="RTGS">RTGS</option><option value="IMPS">IMPS</option><option value="CHEQUE">Cheque</option><option value="UPI_OFFLINE">UPI (offline)</option></UiSelect></UiLabel><UiLabel className="text-xs font-semibold">UTR / receipt reference<UiInput name="reference" required className="mt-1 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel><UiLabel className="text-xs font-semibold sm:col-span-2">Reason / memo<UiInput name="reason" required className="mt-1 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel></UiBox><UiBox className="mt-4 flex gap-2"><UiButton disabled={busy} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">{busy ? "Saving…" : "Confirm payment received"}</UiButton><UiButton type="button" onClick={() => setOfflineOpen(false)} className="rounded-lg border border-line px-4 py-2 text-sm">Cancel</UiButton></UiBox></UiForm>}
    {refundPayment && <UiModal className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4" onClose={() => setRefundPayment(null)}><UiForm onSubmit={submitRefund} className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl"><UiH2 className="font-bold">Refund payment</UiH2><UiText className="mt-1 text-xs text-slate-500">{refundPayment.tenant_name} · {money(refundPayment.amount, refundPayment.currency)} total paid</UiText><UiLabel className="mt-4 block text-xs font-semibold">Refund amount in ₹<UiInput name="amount" type="number" min="0.01" step="0.01" placeholder="Leave blank to refund remaining balance" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiLabel className="mt-3 block text-xs font-semibold">Reason<UiInput name="reason" required className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiText className="mt-3 text-xs text-amber-800">Subscription status changes only after a refund is verified by Razorpay.</UiText><UiBox className="mt-4 flex justify-end gap-2"><UiButton type="button" onClick={() => setRefundPayment(null)} className="rounded-lg border border-line px-4 py-2 text-sm">Cancel</UiButton><UiButton disabled={busy} className="rounded-lg bg-rose-700 px-4 py-2 text-sm font-semibold text-white">{busy ? "Submitting…" : "Request refund"}</UiButton></UiBox></UiForm></UiModal>}
    <UiBox className="mt-6 overflow-x-auto rounded-xl border border-line bg-white"><UiTable className="w-full min-w-[900px] text-left text-xs"><UiTableHead className="bg-slate-50 uppercase tracking-wider text-slate-500"><UiTableRow>{["Company", "Amount", "Status", "Method", "Reference / Razorpay ID", "Paid", "Action"].map(x => <UiTh key={x} className="px-4 py-3">{x}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{pagination.rows.map(payment => <UiTableRow key={payment.id} className="border-t border-line"><UiTd className="px-4 py-3 font-semibold">{payment.tenant_name}</UiTd><UiTd className="px-4 py-3">{money(payment.amount, payment.currency)}</UiTd><UiTd className="px-4 py-3">{payment.status}</UiTd><UiTd className="px-4 py-3">{payment.payment_method || "Razorpay"}</UiTd><UiTd className="px-4 py-3">{payment.offline_reference || payment.razorpay_payment_id || payment.razorpay_order_id || "—"}</UiTd><UiTd className="px-4 py-3">{payment.paid_at ? new Date(payment.paid_at).toLocaleString("en-IN") : "—"}</UiTd><UiTd className="px-4 py-3">{canManage && payment.razorpay_payment_id && ["PAID", "PARTIALLY_REFUNDED"].includes(payment.status) ? <UiButton onClick={() => setRefundPayment(payment)} className="rounded border border-line px-2 py-1 text-[10px] font-semibold hover:bg-slate-50">Refund</UiButton> : "—"}</UiTd></UiTableRow>)}{payments.length === 0 && <UiTableRow><UiTd colSpan={7} className="px-4 py-10 text-center text-slate-500">No payment records.</UiTd></UiTableRow>}</UiTableBody></UiTable></UiBox>{pagination.controls}
    <UiBox className="mt-8 grid gap-8"><AdminDataTable title="Refund request tracking" description="Reserved requests and uncertain provider outcomes. Unknown outcomes stay reserved until verified; check the same request instead of submitting another." endpoint="/admin/refunds?intents=1" columns={["tenant_name", "amount", "status", "reason", "request_key", "razorpay_refund_id", "created_at"]}/><AdminDataTable title="Refunds" description="Refund requests and verified provider outcomes." endpoint="/admin/refunds" columns={["tenant_name", "amount", "status", "reason", "payment_order_id", "payment_id", "razorpay_refund_id", "created_at", "processed_at"]}/><AdminDataTable title="Razorpay webhook events" description="Signature-verified event queue and processing status." endpoint="/admin/razorpay/events" columns={["event_id", "event_type", "status", "attempt_count", "publish_count", "next_attempt_at", "error_message", "received_at", "processed_at"]}/></UiBox>
  </>;
}
