"use client";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiText, UiTextarea } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppLink as Link } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
type Customer = {
    id: string;
    name: string;
    status: string;
};
type Order = {
    id: string;
    order_number: string;
    customer: Customer;
    origin: string;
    destination: string;
    pickup_due_at: string | null;
    delivery_due_at: string | null;
    cargo_description: string;
    load_quantity: string | null;
    load_unit: string;
    agreed_amount: string | null;
    customer_reference: string;
    status: string;
    trip_id: string | null;
};
const input = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const statusStyle: Record<string, string> = { OPEN: "bg-sky-50 text-sky-700", ASSIGNED: "bg-violet-50 text-violet-700", LOADING: "bg-amber-50 text-amber-700", IN_TRANSIT: "bg-orange-50 text-orange-700", DELIVERED: "bg-emerald-50 text-emerald-700", CANCELLED: "bg-slate-100 text-slate-500" };
export default function TransportOrdersPage() {
    const [customers, setCustomers] = useState<Customer[]>([]);
    const [orders, setOrders] = useState<Order[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const refresh = useCallback(async () => {
        const [customerResponse, orderResponse] = await Promise.all([apiFetch("/fleet/customers"), apiFetch("/fleet/orders")]);
        if (!customerResponse.ok || !orderResponse.ok)
            throw new Error("Could not load customers or transport orders.");
        setCustomers(await customerResponse.json());
        setOrders(await orderResponse.json());
    }, []);
    useEffect(() => { void refresh().catch(error => setMessage(error.message)); }, [refresh]);
    async function createOrder(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        const form = event.currentTarget;
        const raw = Object.fromEntries(new FormData(form).entries());
        for (const key of ["pickup_due_at", "delivery_due_at", "load_quantity", "load_unit", "agreed_amount", "customer_reference", "cargo_description", "notes"])
            if (!raw[key])
                delete raw[key];
        const response = await apiFetch("/fleet/orders", { method: "POST", body: JSON.stringify(raw) });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not save the order. Check the entered details.");
        else {
            form.reset();
            setMessage("Transport order created. It is ready to assign to a trip.");
            await refresh();
        }
        setBusy(false);
    }
    const activeCustomers = customers.filter(customer => customer.status === "ACTIVE");
    const ordersPage = useListPagination(orders);
    return <UiMain className="w-full min-w-0 space-y-6 px-4 py-8 sm:px-6 lg:px-8">
    <UiHeader className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet & trips</UiText><UiH1 className="mt-1 text-2xl font-bold">Transport orders</UiH1><UiText className="mt-1 text-sm text-slate-500">Record each customer booking, then assign it to a truck and driver by creating a trip.</UiText></UiBox><UiBox className="flex gap-2"><Link href="/fleet/customers" className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">Customers</Link><Link href="/fleet/dispatch" className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">Dispatch</Link><Link href="/fleet/create-trip" className="rounded-lg bg-forest px-3 py-2 text-sm font-semibold text-white">Create trip</Link></UiBox></UiHeader>
    {message && <UiAlert role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{message}</UiAlert>}
    <UiSection className="grid gap-5 lg:grid-cols-[minmax(300px,.8fr)_minmax(0,1.5fr)]">
      <UiForm onSubmit={createOrder} className="h-fit space-y-3 rounded-xl border border-line bg-white p-5 shadow-sm"><UiH2 className="font-semibold">New transport order</UiH2><UiLabel className="block text-xs text-slate-500">Order number<UiInput className={input} name="order_number" required placeholder="e.g. ORD-2026-001"/></UiLabel><UiLabel className="block text-xs text-slate-500">Customer<UiSelect className={input} name="customer_id" required defaultValue=""><option value="" disabled>Select a customer</option>{activeCustomers.map(customer => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</UiSelect></UiLabel><UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="block text-xs text-slate-500">Pickup location<UiInput className={input} name="origin" required placeholder="City, address, or site"/></UiLabel><UiLabel className="block text-xs text-slate-500">Delivery location<UiInput className={input} name="destination" required placeholder="City, address, or site"/></UiLabel><UiLabel className="block text-xs text-slate-500">Pickup due<UiInput className={input} name="pickup_due_at" type="datetime-local"/></UiLabel><UiLabel className="block text-xs text-slate-500">Delivery due<UiInput className={input} name="delivery_due_at" type="datetime-local"/></UiLabel><UiLabel className="block text-xs text-slate-500">Cargo description<UiInput className={input} name="cargo_description" placeholder="Goods or load"/></UiLabel><UiLabel className="block text-xs text-slate-500">Customer’s booking reference<UiInput className={input} name="customer_reference" placeholder="Optional customer reference"/></UiLabel><UiLabel className="block text-xs text-slate-500">Load quantity<UiInput className={input} name="load_quantity" type="number" min="0.001" step="0.001"/></UiLabel><UiLabel className="block text-xs text-slate-500">Unit<UiInput className={input} name="load_unit" placeholder="tonne, pallet, unit"/></UiLabel><UiLabel className="block text-xs text-slate-500 sm:col-span-2">Agreed transport amount (₹)<UiInput className={input} name="agreed_amount" type="number" min="0.01" step="0.01" placeholder="Optional agreed price"/></UiLabel></UiBox><UiLabel className="block text-xs text-slate-500">Required vehicle type<UiSelect name="required_vehicle_type" className={input} defaultValue=""><option value="">Any configured type</option>{["LCV","RIGID","TRAILER","TANKER","REFRIGERATED"].map(t=><option key={t} value={t}>{t}</option>)}</UiSelect></UiLabel><UiLabel className="block text-xs text-slate-500">Notes<UiTextarea className={input} name="notes" rows={2}/></UiLabel><UiButton disabled={busy || activeCustomers.length === 0} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Create order"}</UiButton>{activeCustomers.length === 0 && <UiText className="text-xs text-amber-700">Add an active customer before creating an order.</UiText>}</UiForm>
      <UiSection className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex items-center justify-between"><UiH2 className="font-semibold">Transport orders</UiH2><UiSpan className="text-xs text-slate-500">{orders.length} orders</UiSpan></UiBox><UiBox className="mt-4 divide-y divide-line">{ordersPage.rows.map(order => <UiArticle key={order.id} className="py-4 first:pt-0"><UiBox className="flex flex-wrap items-start justify-between gap-2"><UiBox><UiH3 className="font-semibold">{order.order_number} <UiSpan className="font-normal text-slate-500">· {order.customer.name}</UiSpan></UiH3><UiText className="mt-1 text-sm text-slate-600">{order.origin} → {order.destination}</UiText><UiText className="mt-1 text-xs text-slate-500">{[order.cargo_description, order.load_quantity && `${order.load_quantity} ${order.load_unit}`.trim(), order.customer_reference && `Ref ${order.customer_reference}`].filter(Boolean).join(" · ") || "No load details"}</UiText>{order.agreed_amount && <UiText className="mt-1 text-xs text-slate-500">Agreed amount ₹{Number(order.agreed_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</UiText>}</UiBox><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusStyle[order.status] || "bg-slate-100 text-slate-600"}`}>{order.status.replaceAll("_", " ")}</UiSpan></UiBox>{order.trip_id && <UiText className="mt-2 text-xs text-slate-500">Assigned trip linked</UiText>}</UiArticle>)}{orders.length === 0 && <UiText className="py-6 text-sm text-slate-500">No transport orders yet. Create an order after adding its customer.</UiText>}</UiBox>{ordersPage.controls}</UiSection>
    </UiSection>
  </UiMain>;
}
