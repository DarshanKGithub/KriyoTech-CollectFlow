"use client";
import { QuickDetails } from "@/components/quick-details";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiBox, UiButton, UiForm, UiH1, UiInput, UiMain, UiSection, UiSpan, UiSpinner, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Plus, ShieldCheck } from "lucide-react";
type Vendor = {
    id: string;
    name: string;
    gstin: string;
    contact_phone: string;
    external_code: string;
    approved: boolean;
};
export default function VendorsPage() {
    const [rows, setRows] = useState<Vendor[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const [canEdit, setCanEdit] = useState(false);
    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [r, p] = await Promise.all([apiFetch("/vendors"), apiFetch("/auth/me")]);
            if (!r.ok)
                throw new Error(r.status === 401 ? "Sign in to view vendors." : "Could not load vendors.");
            setRows(await r.json());
            if (p.ok) {
                const profile = await p.json();
                setCanEdit(["OWNER", "FINANCE", "PURCHASE"].includes(profile.role));
            }
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not load vendors.");
        }
        finally {
            setLoading(false);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    async function create(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        setBusy("new");
        try {
            const r = await apiFetch("/vendors", { method: "POST", body: JSON.stringify({ name: form.get("name"), gstin: form.get("gstin"), contact_phone: form.get("contact_phone"), external_code: form.get("external_code"), approved: false }) });
            const data = await r.json();
            if (!r.ok)
                throw new Error(data.error?.message || "Could not create vendor.");
            formElement.reset();
            setMessage("Vendor created. Approve it after supplier validation.");
            await load();
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not create vendor.");
        }
        finally {
            setBusy("");
        }
    }
    async function toggle(vendor: Vendor) {
        setBusy(vendor.id);
        try {
            const r = await apiFetch(`/vendors/${vendor.id}`, { method: "PATCH", body: JSON.stringify({ approved: !vendor.approved }) });
            const data = await r.json();
            if (!r.ok)
                throw new Error(data.error?.message || "Could not update vendor.");
            setMessage(`${vendor.name} ${data.approved ? "approved" : "marked unapproved"}.`);
            await load();
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not update vendor.");
        }
        finally {
            setBusy("");
        }
    }
    const pagination = useListPagination(rows, "");
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiBox className="mt-6 flex items-end justify-between"><UiBox><UiH1 className="text-2xl font-bold">Vendors</UiH1><UiText className="mt-1 text-sm text-slate-500">Maintain the tenant vendor list used to validate invoice suppliers.</UiText></UiBox><UiSpan className="text-xs text-slate-500">{rows.length} vendors</UiSpan></UiBox>{message && <WorkflowFeedback message={message} onRefresh={()=>load()} />}{canEdit && <UiForm onSubmit={create} className="mt-5 grid gap-3 rounded-xl border border-line bg-white p-4 shadow-card sm:grid-cols-[1.2fr_1fr_1fr_1fr_auto]"><UiInput name="name" required placeholder="Vendor name" className="rounded-lg border border-line px-3 py-2.5 text-xs"/><UiInput name="gstin" placeholder="GSTIN" maxLength={15} className="rounded-lg border border-line px-3 py-2.5 text-xs"/><UiInput name="contact_phone" type="tel" placeholder="Vendor WhatsApp (+91…)" className="rounded-lg border border-line px-3 py-2.5 text-xs"/><UiInput name="external_code" placeholder="Vendor code (optional)" className="rounded-lg border border-line px-3 py-2.5 text-xs"/><UiButton disabled={busy === "new"} className="inline-flex items-center justify-center gap-2 rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === "new" ? <UiSpinner className="animate-spin" size={14}/> : <Plus size={14}/>}Add vendor</UiButton></UiForm>}<UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white shadow-card">{loading ? <ContentSkeleton variant="table" label="Loading vendors" /> : rows.length === 0 ? <EmptyState description="No vendors yet. Add or import vendor records before matching invoices." onAction={()=>void load()} actionLabel="Refresh data" /> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[700px] text-left"><UiTableHead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><UiTableRow>{["Vendor", "GSTIN", "WhatsApp number", "Vendor code", "Status", "Action"].map(x => <UiTh key={x} className="px-5 py-3">{x}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{pagination.rows.map(v => <UiTableRow key={v.id} className="border-t border-line text-xs"><UiTd className="px-5 py-4 font-semibold"><QuickDetails title={v.name} label={v.name} fields={{Name:v.name,GSTIN:v.gstin,WhatsApp:v.contact_phone,"Vendor code":v.external_code,Status:v.approved ? "Approved" : "Unapproved"}}/></UiTd><UiTd className="px-5 py-4 text-slate-500">{v.gstin || "—"}</UiTd><UiTd className="px-5 py-4 text-slate-500">{v.contact_phone || "—"}</UiTd><UiTd className="px-5 py-4 text-slate-500">{v.external_code || "—"}</UiTd><UiTd className="px-5 py-4"><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${v.approved ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{v.approved ? "Approved" : "Unapproved"}</UiSpan></UiTd><UiTd className="px-5 py-4">{canEdit ? <UiButton disabled={busy === v.id} onClick={() => void toggle(v)} className="inline-flex items-center gap-1 font-semibold text-forest disabled:opacity-50">{busy === v.id ? <UiSpinner size={13} className="animate-spin"/> : <ShieldCheck size={13}/>}Mark {v.approved ? "unapproved" : "approved"}</UiButton> : "—"}</UiTd></UiTableRow>)}</UiTableBody></UiTable></UiBox>}{pagination.controls}</UiSection></UiMain>;
}
