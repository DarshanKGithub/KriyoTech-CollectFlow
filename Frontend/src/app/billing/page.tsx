"use client";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiH1, UiH2, UiLabel, UiSection, UiSelect, UiSmall, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import "@/lib/razorpay-checkout";
type Plan = {
    id: string;
    name: string;
    description: string;
    monthly_price: number | null;
    quarterly_price: number | null;
    annual_price: number | null;
    currency: string;
    invoice_limit: number | null;
    user_limit: number | null;
};
type Billing = {
    subscription: {
        status: string;
        billing_cycle: string;
        trial_ends_at: string | null;
        next_billing_at: string | null;
    } | null;
    plan: {
        id: string;
        name: string;
    } | null;
    usage: {
        id: string;
        metric: string;
        used_count: number;
        limit_value: number | null;
        period_start: string;
    }[];
    available_plans: Plan[];
    payments: {
        id: string;
        amount: number;
        currency: string;
        status: string;
        paid_at: string | null;
    }[];
    billing_invoices: {
        id: string;
        invoice_number: string;
        total_amount: number;
        currency: string;
        status: string;
        created_at: string;
    }[];
    gateway_configured: boolean;
};
const money = (paise: number | null, currency = "INR") => paise == null ? "Custom" : new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(paise / 100);
export default function BillingPage() {
    const [data, setData] = useState<Billing | null>(null);
    const [planId, setPlanId] = useState("");
    const [cycle, setCycle] = useState("MONTHLY");
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const [initialLoading, setInitialLoading] = useState(true);
    const load = useCallback(async () => { const response = await apiFetch("/billing/summary"); if (!response.ok) throw new Error("Could not load billing. Please refresh to retry."); if (response.ok) {
        const value = await response.json();
        setData(value);
        setPlanId(current => current || value.plan?.id || "");
    } }, []);
    useEffect(() => { void load().catch(error => setMessage(error instanceof Error ? error.message : "Could not load billing.")).finally(() => setInitialLoading(false)); }, [load]);
    useEffect(() => { const script = document.createElement("script"); script.src = "https://checkout.razorpay.com/v1/checkout.js"; script.async = true; document.body.appendChild(script); return () => { script.remove(); }; }, []);
    async function checkout() { setBusy(true); setMessage(""); try {
        const orderResponse = await apiFetch("/billing/razorpay/create-order", { method: "POST", body: JSON.stringify({ plan_id: planId, billing_cycle: cycle }) });
        const order = await orderResponse.json();
        if (!orderResponse.ok)
            throw new Error(order.error || "Could not create payment order.");
        if (!window.Razorpay)
            throw new Error("Razorpay Checkout did not load. Retry after checking your network.");
        const widget = new window.Razorpay({ key: order.key_id, amount: order.amount, currency: order.currency, name: "KriyoPay", description: `${data?.available_plans.find(p => p.id === planId)?.name || "Plan"} · ${cycle.toLowerCase()}`, order_id: order.order_id, theme: { color: "#16734A" }, modal: { ondismiss: () => setBusy(false) }, handler: async (result) => { setMessage("Payment received by checkout. Verifying with Razorpay…"); const verify = await apiFetch("/billing/razorpay/verify-payment", { method: "POST", body: JSON.stringify(result) }); const confirmation = await verify.json(); if (!verify.ok) {
                setMessage(confirmation.error || "Payment remains pending server verification.");
                setBusy(false);
                return;
            } setMessage("Payment verified. Your subscription is active."); setBusy(false); void load(); } });
        widget.open();
    }
    catch (e) {
        setMessage(e instanceof Error ? e.message : "Unable to start checkout.");
        setBusy(false);
    } }
    const selected = data?.available_plans.find(p => p.id === planId);
    const amount = selected ? (cycle === "MONTHLY" ? selected.monthly_price : cycle === "QUARTERLY" ? selected.quarterly_price : selected.annual_price) : null;
    return <UiBox className="w-full min-w-0 px-5 py-8 md:px-8"><UiText className="text-[10px] font-bold uppercase tracking-[.15em] text-forest">Workspace account</UiText><UiH1 className="mt-2 text-3xl font-bold">Billing & plan</UiH1><UiText className="mt-2 text-sm text-slate-500">Manage your plan, monitor monthly usage, and review billing history.</UiText>
    {message && <UiAlert role="status" className="mt-5 rounded-lg border border-line bg-white p-4 text-sm">{message}</UiAlert>}{!data ? (initialLoading ? <ContentSkeleton variant="form" label="Loading billing" /> : null) : <>
      <UiBox className="mt-6 grid gap-4 md:grid-cols-3"><UiSection className="rounded-xl border border-line bg-white p-5"><UiText className="text-xs text-slate-500">Current plan</UiText><UiH2 className="mt-2 text-xl font-bold">{data.plan?.name || "No subscription"}</UiH2><UiText className="mt-1 text-xs text-slate-500">{data.subscription?.status || "—"} · {data.subscription?.billing_cycle || "—"}</UiText><UiText className="mt-2 text-xs text-slate-500">{data.subscription?.trial_ends_at ? `Trial ends ${new Date(data.subscription.trial_ends_at).toLocaleDateString("en-IN")}` : data.subscription?.next_billing_at ? `Next billing ${new Date(data.subscription.next_billing_at).toLocaleDateString("en-IN")}` : ""}</UiText></UiSection><UiSection className="rounded-xl border border-line bg-white p-5 md:col-span-2"><UiText className="font-bold">Usage this month</UiText>{data.usage.map(item => <UiBox key={item.id} className="mt-3"><UiBox className="flex justify-between text-xs"><UiSpan>{item.metric.replaceAll("_", " ")}</UiSpan><UiStrong>{item.used_count} / {item.limit_value ?? "unlimited"}</UiStrong></UiBox>{item.limit_value && <UiBox className="mt-1 h-1.5 rounded bg-slate-100"><UiBox className="h-1.5 rounded bg-forest" style={{ width: `${Math.min(100, item.used_count / item.limit_value * 100)}%` }}/></UiBox>}</UiBox>)}{!data.usage.length && <UiText className="mt-3 text-xs text-slate-500">No usage events recorded for this billing period yet.</UiText>}</UiSection></UiBox>
      <UiSection className="mt-5 rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Choose a plan</UiH2><UiText className="mt-1 text-xs text-slate-500">Payment activates the selected plan only after server verification.</UiText><UiBox className="mt-4 grid gap-3 sm:grid-cols-2">{data.available_plans.map(plan => <UiButton key={plan.id} onClick={() => setPlanId(plan.id)} className={`rounded-xl border p-4 text-left ${plan.id === planId ? "border-forest ring-1 ring-forest" : "border-line"}`}><UiSpan className="font-semibold">{plan.name}</UiSpan><UiSpan className="mt-2 block text-sm">{money(plan.monthly_price, plan.currency)} <UiSmall className="text-slate-500">/ month</UiSmall></UiSpan><UiSmall className="mt-1 block text-slate-500">{plan.invoice_limit ?? "Custom"} invoices · {plan.user_limit ?? "Custom"} users</UiSmall></UiButton>)}</UiBox><UiBox className="mt-4 flex flex-wrap items-end gap-3"><UiLabel className="text-xs font-semibold">Billing cycle<UiSelect value={cycle} onChange={e => setCycle(e.target.value)} className="mt-1.5 block min-h-10 rounded-lg border border-line bg-white px-3 text-sm"><option value="MONTHLY">Monthly</option><option value="QUARTERLY">Quarterly</option><option value="ANNUAL">Annual</option></UiSelect></UiLabel><UiBox className="pb-2 text-sm font-semibold">Due now: {money(amount, selected?.currency)}</UiBox><UiButton disabled={!data.gateway_configured || !planId || !amount || busy} onClick={() => void checkout()} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Waiting for verification…" : "Continue to secure payment"}</UiButton>{!data.gateway_configured && <UiText className="basis-full text-xs text-amber-800">Checkout is disabled until the server has Razorpay API and webhook secrets configured.</UiText>}</UiBox></UiSection>
      <UiSection className="mt-5 grid gap-4 md:grid-cols-2"><UiBox className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Billing invoices</UiH2>{data.billing_invoices.length ? data.billing_invoices.map(row => <UiBox key={row.id} className="flex justify-between border-t border-line py-3 text-xs"><UiSpan>{row.invoice_number} · {row.status}</UiSpan><UiStrong>{money(row.total_amount, row.currency)}</UiStrong></UiBox>) : <UiText className="mt-3 text-xs text-slate-500">No KriyoPay billing invoices yet.</UiText>}</UiBox><UiBox className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Payments</UiH2>{data.payments.length ? data.payments.map(row => <UiBox key={row.id} className="flex justify-between border-t border-line py-3 text-xs"><UiSpan>{row.status} · {row.paid_at ? new Date(row.paid_at).toLocaleDateString("en-IN") : "awaiting payment"}</UiSpan><UiStrong>{money(row.amount, row.currency)}</UiStrong></UiBox>) : <UiText className="mt-3 text-xs text-slate-500">No payments recorded.</UiText>}</UiBox></UiSection>
    </>}</UiBox>;
}
