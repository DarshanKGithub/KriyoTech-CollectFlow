"use client";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSpan, UiText, UiTextarea } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppLink as Link } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
type Customer = {
    id: string;
    name: string;
    contact_name: string;
    email: string;
    phone: string;
    gstin: string;
    billing_address: string;
    status: string;
    notes: string;
};
const input = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
export default function FleetCustomersPage() {
    const [customers, setCustomers] = useState<Customer[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    async function saveDetention(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget);setBusy(true);try{const r=await apiFetch(`/fleet/customers/${data.get("customer_id")}`,{method:"PATCH",body:JSON.stringify({dock_free_minutes:data.get("free")?Number(data.get("free")):null,detention_rate_per_hour:data.get("rate")||null})});const d=await r.json();if(!r.ok)throw new Error(d.error||"Could not save customer detention terms.");await refresh();setMessage("Customer detention terms saved. New check-ins will use these terms.");}catch(e){setMessage(e instanceof Error?e.message:"Could not save terms.");}finally{setBusy(false);}}
    const refresh = useCallback(async () => {
        const response = await apiFetch("/fleet/customers");
        if (!response.ok)
            throw new Error("Could not load customers.");
        setCustomers(await response.json());
    }, []);
    useEffect(() => { void refresh().catch(error => setMessage(error.message)); }, [refresh]);
    async function createCustomer(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        const form = event.currentTarget;
        const response = await apiFetch("/fleet/customers", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form).entries())) });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(typeof result?.error === "string" ? result.error : "Could not save customer. Check the entered details.");
        else {
            form.reset();
            setMessage("Customer saved.");
            await refresh();
        }
        setBusy(false);
    }
    const customersPage = useListPagination(customers);
    return <UiMain className="w-full min-w-0 space-y-6 px-4 py-8 sm:px-6 lg:px-8">
    <UiHeader className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet & trips</UiText><UiH1 className="mt-1 text-2xl font-bold">Customers</UiH1><UiText className="mt-1 text-sm text-slate-500">Keep transport customer details here and attach each booking to a customer.</UiText></UiBox><Link href="/fleet/orders" className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">Transport orders</Link></UiHeader>
    {message && <UiAlert role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{message}</UiAlert>}
    <UiForm onSubmit={saveDetention} className="grid gap-3 rounded-xl border border-line p-4 sm:grid-cols-4"><UiLabel className="text-xs">Customer detention terms<select name="customer_id" required className={input} defaultValue=""><option value="" disabled>Choose customer</option>{customers.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></UiLabel><UiLabel className="text-xs">Free minutes<UiInput name="free" type="number" min="0" max="1440" className={input} placeholder="Workspace default"/></UiLabel><UiLabel className="text-xs">Rate ₹/hour<UiInput name="rate" type="number" min="0" max="100000" step="0.01" className={input} placeholder="Workspace default"/></UiLabel><UiButton disabled={busy||!customers.length}>Save detention terms</UiButton></UiForm>
    <UiSection className="grid gap-5 lg:grid-cols-[minmax(280px,.8fr)_minmax(0,1.4fr)]">
      <UiForm onSubmit={createCustomer} className="h-fit space-y-3 rounded-xl border border-line bg-white p-5 shadow-sm"><UiH2 className="font-semibold">Add customer</UiH2><UiLabel className="block text-xs text-slate-500">Business or customer name<UiInput className={input} name="name" required maxLength={180} placeholder="e.g. Acme Manufacturing"/></UiLabel><UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="block text-xs text-slate-500">Contact person<UiInput className={input} name="contact_name"/></UiLabel><UiLabel className="block text-xs text-slate-500">Phone<UiInput className={input} name="phone" type="tel"/></UiLabel><UiLabel className="block text-xs text-slate-500">Email<UiInput className={input} name="email" type="email"/></UiLabel><UiLabel className="block text-xs text-slate-500">GSTIN<UiInput className={input} name="gstin" maxLength={15}/></UiLabel></UiBox><UiLabel className="block text-xs text-slate-500">Billing address<UiTextarea className={input} name="billing_address" rows={2}/></UiLabel><UiLabel className="block text-xs text-slate-500">Notes<UiTextarea className={input} name="notes" rows={2}/></UiLabel><UiButton disabled={busy} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save customer"}</UiButton></UiForm>
      <UiSection className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex items-center justify-between"><UiH2 className="font-semibold">Customer directory</UiH2><UiSpan className="text-xs text-slate-500">{customers.length} customers</UiSpan></UiBox><UiBox className="mt-4 divide-y divide-line">{customersPage.rows.map(customer => <UiArticle key={customer.id} className="py-4 first:pt-0"><UiBox className="flex flex-wrap justify-between gap-2"><UiBox><UiH3 className="font-medium">{customer.name}</UiH3><UiText className="mt-1 text-xs text-slate-500">{[customer.contact_name, customer.phone, customer.email].filter(Boolean).join(" · ") || "No contact details"}</UiText>{customer.gstin && <UiText className="mt-1 text-xs text-slate-500">GSTIN {customer.gstin}</UiText>}</UiBox><UiSpan className={`h-fit rounded-full px-2.5 py-1 text-[10px] font-semibold ${customer.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{customer.status}</UiSpan></UiBox>{customer.billing_address && <UiText className="mt-2 whitespace-pre-line text-xs text-slate-500">{customer.billing_address}</UiText>}</UiArticle>)}{customers.length === 0 && <UiText className="py-6 text-sm text-slate-500">No customers yet. Add a customer to start creating transport orders.</UiText>}</UiBox>{customersPage.controls}</UiSection>
    </UiSection>
  </UiMain>;
}
