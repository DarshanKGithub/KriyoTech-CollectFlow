"use client";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiH4, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { requestInput } from "@/components/product-dialogs";
import { useListPagination } from "@/components/list-pagination";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { LiveData } from "@/components/live-data";
type Customer = {
    id: string;
    name: string;
};
type Order = {
    id: string;
    order_number: string;
    customer: Customer;
    origin: string;
    destination: string;
    agreed_amount: string | null;
    status: string;
    trip_id: string | null;
};
type Trip = {
    id: string;
    trip_number: string;
    delivery_at: string | null;
    delivery_proof_name: string | null;
    delivery_signature_name: string;
    transport_order: {
        id: string;
        order_number: string;
        customer_name: string;
    } | null;
};
type Collection = {
    id: string;
    amount: string;
    received_date: string;
    method: string;
    reference: string;
};
type Invoice = {
    id: string;
    invoice_number: string;
    customer: Customer;
    order: {
        id: string;
        order_number: string;
    };
    trip: {
        id: string;
        trip_number: string;
    };
    invoice_date: string;
    due_date: string | null;
    amount: string;
    paid_amount: string;
    outstanding_amount: string;
    status: string;
    collections: Collection[];
};
const input = "rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const money = (value: string) => `₹${Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export default function TransportCustomerInvoicesPage() {
    const [orders, setOrders] = useState<Order[]>([]);
    const [trips, setTrips] = useState<Trip[]>([]);
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState("");
    const refresh = useCallback(async () => {
        const [ordersResponse, tripsResponse, invoicesResponse] = await Promise.all([apiFetch("/fleet/orders"), apiFetch("/fleet/trips"), apiFetch("/fleet/customer-invoices")]);
        if (!ordersResponse.ok || !tripsResponse.ok || !invoicesResponse.ok)
            throw new Error("Could not load transport billing records.");
        setOrders(await ordersResponse.json());
        setTrips(await tripsResponse.json());
        setInvoices(await invoicesResponse.json());
    }, []);
    useEffect(() => { void refresh().catch(error => setMessage(error.message)); }, [refresh]);
    async function createInvoice(order: Order) {
        if (!order.trip_id)
            return;
        const proposed = `TR-${order.order_number}`;
        const invoiceNumber = (await requestInput("Customer invoice number", proposed));
        if (invoiceNumber === null)
            return;
        const dueDate = (await requestInput("Payment due date (YYYY-MM-DD), or leave blank", ""));
        if (dueDate === null)
            return;
        setBusy(order.id);
        setMessage("");
        const response = await apiFetch("/fleet/customer-invoices", { method: "POST", body: JSON.stringify({ trip_id: order.trip_id, order_id: order.id, invoice_number: invoiceNumber, ...(dueDate.trim() ? { due_date: dueDate.trim() } : {}) }) });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not create the customer invoice.");
        else
            setMessage("Draft customer invoice created. Review the amount, then issue it to begin collection tracking.");
        await refresh();
        setBusy("");
    }
    async function issueInvoice(invoice: Invoice) {
        setBusy(invoice.id);
        setMessage("");
        const response = await apiFetch(`/fleet/customer-invoices/${invoice.id}/issue`, { method: "POST", body: "{}" });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(result?.error || "Could not issue the invoice.");
        else
            setMessage(`Invoice ${invoice.invoice_number} issued for collection tracking.`);
        await refresh();
        setBusy("");
    }
    async function recordCollection(event: FormEvent<HTMLFormElement>, invoice: Invoice) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form).entries());
        setBusy(invoice.id);
        setMessage("");
        const response = await apiFetch(`/fleet/customer-invoices/${invoice.id}/collections`, { method: "POST", body: JSON.stringify({ ...data, idempotency_key: crypto.randomUUID() }) });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not record the collection.");
        else {
            setMessage("Customer collection recorded.");
            form.reset();
        }
        await refresh();
        setBusy("");
    }
    const invoicedOrderIds = new Set(invoices.map(invoice => invoice.order.id));
    const tripById = new Map(trips.map(trip => [trip.id, trip]));
    const readyOrders = orders.filter(order => order.status === "DELIVERED" && order.trip_id && !invoicedOrderIds.has(order.id) && Number(order.agreed_amount) > 0 && tripById.get(order.trip_id)?.delivery_at && (tripById.get(order.trip_id)?.delivery_proof_name || tripById.get(order.trip_id)?.delivery_signature_name));
    const readyOrdersPage = useListPagination(readyOrders);
    const invoicesPage = useListPagination(invoices);
    return <UiMain className="w-full min-w-0 space-y-6 px-4 py-8 sm:px-6 lg:px-8">
    <UiHeader><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet & trips</UiText><UiH1 className="mt-1 text-2xl font-bold">Customer invoices & collections</UiH1><UiText className="mt-1 max-w-3xl text-sm text-slate-500">Create a draft from a delivered order, issue it after review, then record full or partial customer payments.</UiText></UiHeader>
    <LiveData onRefresh={refresh} paused={Boolean(busy)} interval={20000}/>
    {message && <UiAlert role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{message}</UiAlert>}
    <UiSection className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex flex-wrap items-center justify-between gap-2"><UiBox><UiH2 className="font-semibold">Delivered trips ready to invoice</UiH2><UiText className="mt-1 text-xs text-slate-500">Only trips with a delivered milestone, delivery proof or signature, and an agreed order amount appear here.</UiText></UiBox><UiSpan className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">{readyOrders.length} ready</UiSpan></UiBox>
      <UiBox className="mt-4 divide-y divide-line">{readyOrdersPage.rows.map(order => <UiArticle key={order.id} className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0"><UiBox><UiH3 className="font-semibold">{order.order_number} <UiSpan className="font-normal text-slate-500">· {order.customer.name}</UiSpan></UiH3><UiText className="mt-1 text-sm text-slate-600">{order.origin} → {order.destination} · Trip {tripById.get(order.trip_id!)?.trip_number}</UiText><UiText className="mt-1 text-sm font-medium">Agreed amount {money(order.agreed_amount || "0")}</UiText></UiBox><UiButton disabled={!!busy} onClick={() => void createInvoice(order)} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === order.id ? "Creating…" : "Create draft invoice"}</UiButton></UiArticle>)}{readyOrders.length === 0 && <UiText className="py-5 text-sm text-slate-500">No delivered orders are ready to invoice. Check delivery proof and agreed order amounts.</UiText>}</UiBox>
    {readyOrdersPage.controls}</UiSection>
    <UiSection className="space-y-3"><UiBox className="flex items-center justify-between"><UiH2 className="font-semibold">Customer receivables</UiH2><UiSpan className="text-xs text-slate-500">{invoices.length} invoices</UiSpan></UiBox>
      {invoicesPage.rows.map(invoice => <UiArticle key={invoice.id} className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiBox className="flex flex-wrap items-center gap-2"><UiH3 className="font-semibold">{invoice.invoice_number}</UiH3><UiSpan className={`rounded-full px-2 py-1 text-[10px] font-semibold ${invoice.status === "PAID" ? "bg-emerald-50 text-emerald-700" : invoice.status === "DRAFT" ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-700"}`}>{invoice.status.replaceAll("_", " ")}</UiSpan></UiBox><UiText className="mt-1 text-sm text-slate-600">{invoice.customer.name} · Order {invoice.order.order_number} · Trip {invoice.trip.trip_number}</UiText><UiText className="mt-1 text-xs text-slate-500">Invoice date {invoice.invoice_date}{invoice.due_date ? ` · Due ${invoice.due_date}` : " · No due date"}</UiText></UiBox><UiBox className="grid grid-cols-3 gap-4 text-right text-xs"><UiBox><UiSpan className="block text-slate-500">Invoice</UiSpan><UiStrong className="mt-1 block text-sm">{money(invoice.amount)}</UiStrong></UiBox><UiBox><UiSpan className="block text-slate-500">Received</UiSpan><UiStrong className="mt-1 block text-sm text-emerald-700">{money(invoice.paid_amount)}</UiStrong></UiBox><UiBox><UiSpan className="block text-slate-500">Outstanding</UiSpan><UiStrong className="mt-1 block text-sm">{money(invoice.outstanding_amount)}</UiStrong></UiBox></UiBox></UiBox>
        {invoice.status === "DRAFT" && <UiButton disabled={!!busy} onClick={() => void issueInvoice(invoice)} className="mt-4 rounded-lg bg-forest px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === invoice.id ? "Issuing…" : "Issue invoice"}</UiButton>}
        {invoice.status !== "DRAFT" && invoice.status !== "PAID" && <UiForm onSubmit={event => void recordCollection(event, invoice)} className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4"><UiLabel className="text-xs text-slate-500">Received amount<UiInput className={`${input} mt-1 block w-36`} name="amount" type="number" min="0.01" max={invoice.outstanding_amount} step="0.01" required/></UiLabel><UiLabel className="text-xs text-slate-500">Date<UiInput className={`${input} mt-1 block`} name="received_date" type="date" required defaultValue={new Date().toISOString().slice(0, 10)}/></UiLabel><UiLabel className="text-xs text-slate-500">Method<UiSelect className={`${input} mt-1 block`} name="method" defaultValue="BANK"><option value="BANK">Bank transfer</option><option value="UPI">UPI</option><option value="CASH">Cash</option><option value="CHEQUE">Cheque</option><option value="OTHER">Other</option></UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Reference<UiInput className={`${input} mt-1 block w-40`} name="reference" placeholder="Txn / cheque ref"/></UiLabel><UiButton disabled={!!busy} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === invoice.id ? "Saving…" : "Record collection"}</UiButton></UiForm>}
        {invoice.collections.length > 0 && <UiBox className="mt-4 border-t border-line pt-3"><UiH4 className="text-xs font-semibold text-slate-600">Collection history</UiH4><UiBox className="mt-2 flex flex-wrap gap-x-5 gap-y-2">{invoice.collections.map(item => <UiText key={item.id} className="text-xs text-slate-500">{item.received_date} · {money(item.amount)} · {item.method}{item.reference ? ` · ${item.reference}` : ""}</UiText>)}</UiBox></UiBox>}
      </UiArticle>)}
      {invoices.length === 0 && <UiBox className="rounded-xl border border-dashed border-line bg-white p-8 text-center text-sm text-slate-500">Customer invoices created from delivered transport orders will appear here.</UiBox>}
    {invoicesPage.controls}</UiSection>
  </UiMain>;
}
