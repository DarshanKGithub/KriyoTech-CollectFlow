"use client";

import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiText, UiTextarea } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AppLink as Link } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import { ArrowRight, ClipboardList, Plus, RefreshCw, Search, X } from "lucide-react";

type Customer = { id: string; name: string; status: string };
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
const statusStyle: Record<string, string> = {
    OPEN: "bg-sky-50 text-sky-700", ASSIGNED: "bg-violet-50 text-violet-700",
    LOADING: "bg-amber-50 text-amber-700", IN_TRANSIT: "bg-orange-50 text-orange-700",
    DELIVERED: "bg-emerald-50 text-emerald-700", CANCELLED: "bg-slate-100 text-slate-500",
};
const statusOptions = ["OPEN", "ASSIGNED", "LOADING", "IN_TRANSIT", "DELIVERED", "CANCELLED"];
const orderDate = (value: string | null) => value ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Not scheduled";
const orderAmount = (value: string | null) => value ? `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "Not set";

export default function TransportOrdersPage() {
    const [customers, setCustomers] = useState<Customer[]>([]);
    const [orders, setOrders] = useState<Order[]>([]);
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [createOpen, setCreateOpen] = useState(false);
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("");

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const [customerResponse, orderResponse] = await Promise.all([apiFetch("/fleet/customers"), apiFetch("/fleet/orders")]);
            if (!customerResponse.ok || !orderResponse.ok)
                throw new Error("Orders could not be loaded. Check your workspace access and try again.");
            const [customerData, orderData] = await Promise.all([customerResponse.json(), orderResponse.json()]);
            setCustomers(customerData);
            setOrders(orderData);
            setMessage("");
        }
        catch (error) {
            const detail = error instanceof Error ? error.message : "Could not load orders. Try again.";
            setMessage(detail);
            throw error;
        }
        finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);

    async function createOrder(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (saving) return;
        setSaving(true);
        setMessage("");
        const form = event.currentTarget;
        const raw = Object.fromEntries(new FormData(form).entries());
        for (const key of ["pickup_due_at", "delivery_due_at", "load_quantity", "load_unit", "agreed_amount", "customer_reference", "cargo_description", "notes", "origin_latitude", "origin_longitude", "destination_latitude", "destination_longitude"])
            if (!raw[key]) delete raw[key];
        try {
            const response = await apiFetch("/fleet/orders", { method: "POST", body: JSON.stringify(raw) });
            const result = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(typeof result?.error === "string" ? result.error : "Could not save this order. Check the required details and try again.");
            form.reset();
            setCreateOpen(false);
            setMessage("Order created and ready for dispatch.");
            await refresh().catch(() => setMessage("Order created, but the list could not refresh. Use Refresh to reload it."));
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not create the order. Please try again.");
        }
        finally {
            setSaving(false);
        }
    }

    const activeCustomers = customers.filter(customer => customer.status === "ACTIVE");
    const filteredOrders = useMemo(() => {
        const query = search.trim().toLowerCase();
        return orders.filter(order => {
            const matchesStatus = !statusFilter || order.status === statusFilter;
            const matchesSearch = !query || [order.order_number, order.customer.name, order.origin, order.destination, order.customer_reference, order.cargo_description]
                .some(value => value?.toLowerCase().includes(query));
            return matchesStatus && matchesSearch;
        });
    }, [orders, search, statusFilter]);
    const pagination = useListPagination(filteredOrders, `${statusFilter}:${search}`);
    const openCount = orders.filter(order => order.status === "OPEN").length;
    const activeCount = orders.filter(order => ["ASSIGNED", "LOADING", "IN_TRANSIT"].includes(order.status)).length;
    const deliveredCount = orders.filter(order => order.status === "DELIVERED").length;

    return <UiMain className="w-full min-w-0 space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <UiHeader className="flex flex-wrap items-end justify-between gap-4">
            <UiBox>
                <UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet operations</UiText>
                <UiH1 className="mt-1 text-2xl font-bold tracking-tight">Orders</UiH1>
                <UiText className="mt-1 max-w-2xl text-sm text-slate-500">Manage customer bookings from one place, then send ready orders to dispatch.</UiText>
            </UiBox>
            <UiBox className="flex flex-wrap gap-2">
                <UiButton type="button" onClick={() => void refresh().catch(() => undefined)} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-700"><RefreshCw size={15} className={loading ? "animate-spin" : ""}/>Refresh</UiButton>
                <UiButton type="button" onClick={() => { setMessage(""); setCreateOpen(true); }} className="inline-flex items-center gap-2 rounded-lg bg-forest px-3.5 py-2.5 text-sm font-semibold text-white"><Plus size={16}/>Create order</UiButton>
            </UiBox>
        </UiHeader>

        {message && <UiAlert role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{message}</UiAlert>}

        <UiSection aria-label="Order summary" className="grid gap-3 sm:grid-cols-3">
            {[
                { label: "All orders", value: orders.length, note: "Customer bookings" },
                { label: "Ready for dispatch", value: openCount, note: "Waiting for truck and driver" },
                { label: "On the move", value: activeCount, note: `${deliveredCount} delivered` },
            ].map((item, index) => <UiArticle key={item.label} className="rounded-xl border border-line bg-white p-4"><UiBox className="flex items-center justify-between"><UiText className="text-xs font-medium text-slate-500">{item.label}</UiText><UiSpan className={`grid h-8 w-8 place-items-center rounded-lg ${index === 0 ? "bg-slate-100 text-slate-600" : index === 1 ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}><ClipboardList size={16}/></UiSpan></UiBox><UiH2 className="mt-2 text-2xl font-bold tabular-nums">{loading ? "—" : item.value}</UiH2><UiText className="mt-1 text-xs text-slate-500">{item.note}</UiText></UiArticle>)}
        </UiSection>

        <UiSection className="overflow-hidden rounded-xl border border-line bg-white">
            <UiHeader className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4 sm:p-5">
                <UiBox><UiH2 className="text-sm font-bold">Order register</UiH2><UiText className="mt-1 text-xs text-slate-500">{filteredOrders.length} {filteredOrders.length === 1 ? "order" : "orders"}{search || statusFilter ? " match your filters" : " in this workspace"}</UiText></UiBox>
                <UiBox className="flex w-full flex-wrap gap-2 sm:w-auto">
                    <UiLabel className="relative min-w-52 flex-1 sm:flex-none"><span className="sr-only">Search orders</span><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><UiInput className={`${input} pl-9`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search order, customer, route" aria-label="Search orders" maxLength={150}/></UiLabel>
                    <UiLabel className="flex items-center gap-2 text-xs font-semibold">Status<UiSelect className={input} value={statusFilter} onChange={event => setStatusFilter(event.target.value)} aria-label="Filter orders by status"><option value="">All</option>{statusOptions.map(status => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</UiSelect></UiLabel>
                </UiBox>
            </UiHeader>

            {loading && orders.length === 0 ? <UiBox role="status" className="p-12 text-center"><RefreshCw size={18} className="mx-auto animate-spin text-forest"/><UiText className="mt-3 text-sm text-slate-500">Loading orders…</UiText></UiBox> : pagination.rows.length === 0 ? <UiBox className="p-10 text-center"><UiSpan className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-slate-100 text-slate-500"><ClipboardList size={19}/></UiSpan><UiH3 className="mt-3 text-sm font-semibold">{search || statusFilter ? "No matching orders" : "No orders yet"}</UiH3><UiText className="mx-auto mt-1 max-w-md text-sm text-slate-500">{search || statusFilter ? "Try another search or clear the status filter." : "Create a customer booking to start planning its trip."}</UiText>{search || statusFilter ? <UiButton type="button" onClick={() => { setSearch(""); setStatusFilter(""); }} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">Clear filters</UiButton> : <UiButton type="button" onClick={() => setCreateOpen(true)} disabled={activeCustomers.length === 0} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-forest px-3.5 py-2.5 text-sm font-semibold text-white"><Plus size={15}/>Create order</UiButton>}</UiBox> : <>
                <UiBox className="divide-y divide-line">
                    {pagination.rows.map(order => <UiBox component="article" key={order.id} className="px-4 py-4 transition-colors hover:bg-slate-50/60 sm:px-5">
                        <UiBox className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(190px,.8fr)_minmax(130px,.55fr)_auto] lg:items-center">
                            <UiBox className="min-w-0">
                                <UiBox className="flex flex-wrap items-center gap-x-2 gap-y-1"><UiH3 className="text-sm font-bold">{order.order_number}</UiH3><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusStyle[order.status] || "bg-slate-100 text-slate-600"}`}>{order.status.replaceAll("_", " ")}</UiSpan></UiBox>
                                <UiText className="mt-1 text-sm font-medium text-slate-700">{order.origin} <span className="px-1 text-slate-300">→</span> {order.destination}</UiText>
                                <UiText className="mt-1 truncate text-xs text-slate-500">{order.customer.name}{order.cargo_description ? ` · ${order.cargo_description}` : ""}{order.customer_reference ? ` · Ref ${order.customer_reference}` : ""}</UiText>
                            </UiBox>
                            <UiBox><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Pickup</UiText><UiText className="mt-1 text-xs text-slate-700">{orderDate(order.pickup_due_at)}</UiText><UiText className="mt-1 text-[10px] text-slate-500">Delivery · {orderDate(order.delivery_due_at)}</UiText></UiBox>
                            <UiBox><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Agreed freight</UiText><UiText className="mt-1 text-sm font-semibold text-slate-800">{orderAmount(order.agreed_amount)}</UiText><UiText className="mt-1 text-[10px] text-slate-500">{order.load_quantity ? `${order.load_quantity} ${order.load_unit || "units"}` : "Load quantity not set"}</UiText></UiBox>
                            {order.trip_id ? <Link href="/fleet/trips" className="inline-flex items-center justify-end gap-1 text-xs font-semibold text-forest">Open trip <ArrowRight size={14}/></Link> : order.status === "OPEN" ? <Link href="/fleet/dispatch" className="inline-flex items-center justify-end gap-1 text-xs font-semibold text-forest">Dispatch <ArrowRight size={14}/></Link> : <UiText className="text-right text-xs text-slate-400">—</UiText>}
                        </UiBox>
                    </UiBox>)}
                </UiBox>
                {pagination.controls}
            </>}
        </UiSection>

        <Dialog open={createOpen} onClose={() => !saving && setCreateOpen(false)} fullWidth maxWidth="md" aria-labelledby="create-order-title">
            <UiForm onSubmit={createOrder}>
                <DialogTitle id="create-order-title" sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2, pb: 1 }}>
                    <UiBox><UiH2 className="text-lg font-bold">Create order</UiH2><UiText className="mt-1 text-xs font-normal text-slate-500">Add the booking details. You can assign a truck and driver later in Dispatch.</UiText></UiBox>
                    <UiButton type="button" aria-label="Close create order" onClick={() => !saving && setCreateOpen(false)} disabled={saving} className="min-w-0 p-2 text-slate-500"><X size={17}/></UiButton>
                </DialogTitle>
                <DialogContent dividers>
                    {activeCustomers.length === 0 ? <UiBox className="rounded-lg border border-amber-200 bg-amber-50 p-4"><UiText className="text-sm font-semibold text-amber-900">Add a customer before creating an order.</UiText><UiText className="mt-1 text-xs text-amber-800">Orders need an active customer record.</UiText><Link href="/fleet/customers" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-forest">Open customers <ArrowRight size={14}/></Link></UiBox> : <UiBox className="space-y-5">
                        <UiBox><UiH3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-500">Booking details</UiH3><UiBox className="grid gap-3 sm:grid-cols-2">
                            <UiLabel className="block text-xs text-slate-600">Order number<UiInput className={`${input} mt-1`} name="order_number" required maxLength={64} placeholder="e.g. ORD-2026-001"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Customer<UiSelect className={`${input} mt-1`} name="customer_id" required defaultValue=""><option value="" disabled>Select a customer</option>{activeCustomers.map(customer => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</UiSelect></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Pickup location<UiInput className={`${input} mt-1`} name="origin" required maxLength={240} placeholder="City, address, or site"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Delivery location<UiInput className={`${input} mt-1`} name="destination" required maxLength={240} placeholder="City, address, or site"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Pickup due<UiInput className={`${input} mt-1`} name="pickup_due_at" type="datetime-local"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Delivery due<UiInput className={`${input} mt-1`} name="delivery_due_at" type="datetime-local"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Cargo description<UiInput className={`${input} mt-1`} name="cargo_description" maxLength={240} placeholder="Goods or load"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Customer reference<UiInput className={`${input} mt-1`} name="customer_reference" maxLength={100} placeholder="Optional reference"/></UiLabel>
                        </UiBox></UiBox>
                        <details className="rounded-lg border border-line px-3 py-2"><summary className="cursor-pointer text-xs font-semibold text-slate-600">Route coordinates (optional)</summary><UiBox className="mt-3 grid gap-3 sm:grid-cols-2"><UiLabel className="block text-xs text-slate-600">Pickup latitude<UiInput className={`${input} mt-1`} name="origin_latitude" type="number" min="-90" max="90" step="0.000001" placeholder="e.g. 19.076000"/></UiLabel><UiLabel className="block text-xs text-slate-600">Pickup longitude<UiInput className={`${input} mt-1`} name="origin_longitude" type="number" min="-180" max="180" step="0.000001" placeholder="e.g. 72.877700"/></UiLabel><UiLabel className="block text-xs text-slate-600">Delivery latitude<UiInput className={`${input} mt-1`} name="destination_latitude" type="number" min="-90" max="90" step="0.000001" placeholder="e.g. 18.520400"/></UiLabel><UiLabel className="block text-xs text-slate-600">Delivery longitude<UiInput className={`${input} mt-1`} name="destination_longitude" type="number" min="-180" max="180" step="0.000001" placeholder="e.g. 73.856700"/></UiLabel></UiBox></details>
                        <UiBox><UiH3 className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-500">Freight and vehicle</UiH3><UiBox className="grid gap-3 sm:grid-cols-2">
                            <UiLabel className="block text-xs text-slate-600">Load quantity<UiInput className={`${input} mt-1`} name="load_quantity" type="number" min="0.001" step="0.001" placeholder="Optional"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Load unit<UiInput className={`${input} mt-1`} name="load_unit" maxLength={32} placeholder="tonne, pallet, unit"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Agreed freight (₹)<UiInput className={`${input} mt-1`} name="agreed_amount" type="number" min="0.01" step="0.01" placeholder="Optional"/></UiLabel>
                            <UiLabel className="block text-xs text-slate-600">Required vehicle type<UiSelect name="required_vehicle_type" className={`${input} mt-1`} defaultValue=""><option value="">Any configured type</option>{["LCV", "RIGID", "TRAILER", "TANKER", "REFRIGERATED"].map(type => <option key={type} value={type}>{type}</option>)}</UiSelect></UiLabel>
                            <UiLabel className="block text-xs text-slate-600 sm:col-span-2">Notes<UiTextarea className={`${input} mt-1`} name="notes" rows={2} maxLength={1000} placeholder="Optional instructions for operations"/></UiLabel>
                        </UiBox></UiBox>
                    </UiBox>}
                </DialogContent>
                <DialogActions sx={{ p: 2, gap: 1 }}>
                    <UiButton type="button" onClick={() => setCreateOpen(false)} disabled={saving} className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">Cancel</UiButton>
                    {activeCustomers.length > 0 && <UiButton type="submit" disabled={saving} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">{saving ? "Creating…" : "Create order"}</UiButton>}
                </DialogActions>
            </UiForm>
        </Dialog>
    </UiMain>;
}
