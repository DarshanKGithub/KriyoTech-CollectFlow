"use client";
import { UiAlert, UiBox, UiButton, UiH2, UiSection, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { CheckoutResult, loadRazorpay } from "@/lib/razorpay-checkout";
export function AdminCompanyCheckout({ companyId, companyName, autoOpen = false, onPaid }: {
    companyId: string;
    companyName: string;
    autoOpen?: boolean;
    onPaid?: () => void;
}) {
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [paid, setPaid] = useState(false);
    const started = useRef(false);
    const locked = useRef(false);
    const [confirmation, setConfirmation] = useState<CheckoutResult | null>(null);
    const verify = useCallback(async (result: CheckoutResult) => {
        setMessage("Confirming payment with Razorpay…");
        const response = await apiFetch(`/admin/companies/${companyId}/checkout/verify`, { method: "POST", body: JSON.stringify(result) });
        const body = await response.json();
        if (!response.ok)
            throw new Error(body.error || "Payment is awaiting verification. Check Payments before paying again.");
        setPaid(true);
        setConfirmation(null);
        setMessage("Payment verified. Subscription activated and Payments updated.");
        onPaid?.();
    }, [companyId, onPaid]);
    useEffect(() => {
        if (paid)
            return;
        let active = true;
        const refresh = async () => {
            try {
                const response = await apiFetch(`/admin/companies/${companyId}/checkout`);
                if (!response.ok)
                    return;
                const status = await response.json();
                if (active && status.paid) {
                    setPaid(true);
                    setConfirmation(null);
                    setMessage("Payment verified. Subscription activated and Payments updated.");
                    onPaid?.();
                }
            }
            catch { /* Retain checkout state during a temporary connection failure. */ }
        };
        const timer = window.setInterval(() => void refresh(), 10000);
        return () => { active = false; window.clearInterval(timer); };
    }, [companyId, paid, onPaid]);
    const checkout = useCallback(async () => {
        if (locked.current)
            return;
        locked.current = true;
        setBusy(true);
        setMessage("");
        try {
            await loadRazorpay();
            const response = await apiFetch(`/admin/companies/${companyId}/checkout`, { method: "POST", body: "{}" });
            const order = await response.json();
            if (!response.ok)
                throw new Error(order.error || "Unable to start payment.");
            if (!window.Razorpay)
                throw new Error("Razorpay did not load. Resume payment to retry.");
            const widget = new window.Razorpay({ key: order.key_id, amount: order.amount, currency: order.currency,
                name: "KriyoPay", description: `${order.plan_name} · ${order.billing_cycle.toLowerCase()} · ${order.company_name}`,
                order_id: order.order_id, prefill: order.prefill, theme: { color: "#176b57" },
                modal: { ondismiss: () => { locked.current = false; setBusy(false); setMessage("Checkout closed. Check Payments if money was debited; otherwise resume payment when ready."); } },
                handler: async (result) => {
                    setConfirmation(result);
                    try {
                        await verify(result);
                    }
                    catch (error) {
                        setMessage(error instanceof Error ? error.message : "Check Payments before paying again.");
                    }
                    finally {
                        locked.current = false;
                        setBusy(false);
                    }
                } });
            widget.open();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Unable to start payment.");
            locked.current = false;
            setBusy(false);
        }
    }, [companyId, verify]);
    useEffect(() => { if (autoOpen && !started.current) {
        started.current = true;
        void checkout();
    } }, [autoOpen, checkout]);
    async function retryVerification() {
        if (!confirmation || locked.current)
            return;
        locked.current = true;
        setBusy(true);
        try {
            await verify(confirmation);
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Unable to confirm payment.");
        }
        finally {
            locked.current = false;
            setBusy(false);
        }
    }
    return <UiSection className="mt-4 rounded-xl border border-line bg-white p-5">
    <UiH2 className="font-bold">Subscription payment · {companyName}</UiH2>
    <UiText className="mt-1 text-sm text-slate-500">The company is saved. Payment activates its selected plan after verification.</UiText>
    {message && <UiAlert role="status" className="mt-3 text-sm">{message}</UiAlert>}
    <UiBox className="mt-4 flex flex-wrap items-center gap-4">
      {!paid && <UiButton disabled={busy} onClick={() => void (confirmation ? retryVerification() : checkout())} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Processing…" : confirmation ? "Verify payment again" : "Resume Razorpay payment"}</UiButton>}
      <Link className="text-sm font-semibold text-forest underline" href="/admin-console/payments">View Payments</Link>
      <Link className="text-sm font-semibold text-forest underline" href={`/admin-console/companies/${companyId}`}>View company</Link>
    </UiBox>
  </UiSection>;
}
