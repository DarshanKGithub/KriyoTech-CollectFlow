"use client";
import { PageSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiSelect, UiSpan, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/admin/admin-ui";
import { useListPagination } from "@/components/list-pagination";
import { AppLink as Link } from "@/components/admin/admin-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { AdminCompanyCheckout } from "@/components/admin-company-checkout";
type Company = {
    id: string;
    name: string;
    workspace_key: string;
    owner_email: string | null;
    created_at: string;
    subscription_status: string | null;
};
type Plan = {
    id: string;
    name: string;
    slug: string;
    trial_days: number;
    monthly_price: number | null;
    quarterly_price: number | null;
    annual_price: number | null;
    currency: string;
    is_active: boolean;
};
export default function CompaniesPage() {
    const [rows, setRows] = useState<Company[]>([]);
    const [plans, setPlans] = useState<Plan[]>([]);
    const [query, setQuery] = useState("");
    const [show, setShow] = useState(false);
    const [message, setMessage] = useState("");
    const [initialLoading, setInitialLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [paymentCompany, setPaymentCompany] = useState<{
        id: string;
        name: string;
    } | null>(null);
    const [mode, setMode] = useState("TRIAL");
    const [planId, setPlanId] = useState("");
    const [cycle, setCycle] = useState("MONTHLY");
    const [gatewayConfigured, setGatewayConfigured] = useState(false);
    useEffect(() => { apiFetch("/admin/auth/me").then(async (response) => { if (response.ok)
        setGatewayConfigured((await response.json()).razorpay_configured); }).catch(() => { }); }, []);
    useEffect(()=>{if(new URLSearchParams(window.location.search).get("create")==="1")setShow(true);},[]);
    const selectedPlan = plans.find(plan => plan.id === planId);
    const price = selectedPlan ? (cycle === "ANNUAL" ? selectedPlan.annual_price : cycle === "QUARTERLY" ? selectedPlan.quarterly_price : selectedPlan.monthly_price) : null;
    const payable = mode !== "PAY_NOW" || (gatewayConfigured && !!price && price > 0);
    const load = useCallback(async () => { const [companies, plansResponse] = await Promise.all([apiFetch(`/admin/companies?q=${encodeURIComponent(query)}`), apiFetch("/admin/plans")]); if (companies.ok)
        setRows((await companies.json()).results); if (plansResponse.ok)
        setPlans(await plansResponse.json()); }, [query]);
    useEffect(() => { void load().catch(() => setMessage("Could not load company portfolio. Please refresh to retry.")).finally(() => setInitialLoading(false)); }, [load]);
    async function onboard(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const formElement = event.currentTarget;
        setBusy(true);
        setMessage("");
        const form = new FormData(formElement);
        const payload: Record<string, string | boolean> = Object.fromEntries([...form.entries()].map(([key, value]) => [key, String(value)]));
        payload.trial_enabled = mode === "TRIAL";
        payload.collect_payment = mode === "PAY_NOW";
        try {
            const response = await apiFetch("/admin/companies", { method: "POST", body: JSON.stringify(payload) });
            const body = await response.json();
            if (!response.ok)
                throw new Error(body.error || "Unable to onboard company.");
            const delivery = body.owner_invitation.status === "PENDING" ? "The owner invitation is queued for delivery; its status is visible on the company record." : `The invitation delivery status is ${body.owner_invitation.status}.`;
            setMessage(`Company created. ${delivery}`);
            if (mode === "PAY_NOW")
                setPaymentCompany({ id: body.company.id, name: body.company.name });
            formElement.reset();
            setPlanId("");
            setCycle("MONTHLY");
            setShow(false);
            void load();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Unable to onboard company.");
        }
        finally {
            setBusy(false);
        }
    }
    const pagination = useListPagination(rows, query);
    if (initialLoading) return <PageSkeleton variant="table" label="Loading company portfolio" />;
    return <UiBox><UiBox className="flex flex-wrap items-end justify-between gap-4"><UiBox><UiText className="text-[10px] font-bold uppercase tracking-[.15em] text-forest">Customer portfolio</UiText><UiH1 className="mt-2 text-3xl font-bold">Companies</UiH1><UiText className="mt-2 text-sm text-slate-500">Onboard and inspect customer workspaces.</UiText></UiBox><UiButton onClick={() => setShow(!show)} className="flex items-center gap-2 rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white"><Plus size={16}/>Onboard company</UiButton></UiBox>
    {message && <UiAlert role="status" className="mt-4 rounded-lg border border-line bg-white p-3 text-sm">{message}</UiAlert>}
    {paymentCompany && <AdminCompanyCheckout key={paymentCompany.id} companyId={paymentCompany.id} companyName={paymentCompany.name} onPaid={load} autoOpen/>}
    {show && <UiForm onSubmit={onboard} className="mt-5 rounded-xl border border-line bg-white p-5"><UiBox className="flex items-start justify-between"><UiBox><UiH2 className="font-bold">New company onboarding</UiH2><UiText className="mt-1 text-xs text-slate-500">Choose a plan, invite the owner, and collect payment or start a trial.</UiText></UiBox><UiButton type="button" className="text-sm text-slate-500" onClick={() => setShow(false)}>Close</UiButton></UiBox><UiBox className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{[["company_name", "Company name"], ["owner_name", "Owner full name"], ["owner_email", "Owner work email"], ["phone", "Phone (optional)"], ["gstin", "GSTIN (optional)"], ["industry", "Industry (optional)"], ["city", "City (optional)"], ["state", "State (optional)"], ["workspace_key", "Workspace key (optional)"], ["notes", "Internal onboarding notes"]].map(([name, label]) => <UiLabel key={name} className="text-xs font-semibold text-slate-600">{label}<UiInput name={name} required={name === "company_name" || name === "owner_name" || name === "owner_email"} className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel>)}<UiLabel className="text-xs font-semibold text-slate-600">Plan<UiSelect required name="plan_id" value={planId} onChange={event => setPlanId(event.target.value)} className="mt-1.5 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal"><option value="">Select plan</option>{plans.filter(p => p.is_active && p.slug !== "trial").map(p => <option key={p.id} value={p.id}>{p.name}</option>)}{plans.filter(p => p.is_active && p.slug === "trial").map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold text-slate-600">Billing cycle<UiSelect name="billing_cycle" value={cycle} onChange={event => setCycle(event.target.value)} className="mt-1.5 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal"><option>MONTHLY</option><option>QUARTERLY</option><option>ANNUAL</option></UiSelect></UiLabel><UiLabel className="text-xs font-semibold text-slate-600">Trial days<UiInput disabled={mode !== "TRIAL"} name="trial_days" type="number" min="1" max="365" defaultValue="14" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiLabel className="text-xs font-semibold text-slate-600">Activation<UiSelect value={mode} onChange={event => setMode(event.target.value)} className="mt-1.5 min-h-10 w-full rounded-lg border border-line bg-white px-3 text-sm"><option value="TRIAL">Start with trial</option><option value="PAY_NOW">Collect payment now · Razorpay</option><option value="LATER">Collect payment later</option></UiSelect></UiLabel></UiBox>{mode === "PAY_NOW" && <UiText className="mt-4 text-sm text-slate-600">{price && price > 0 ? `Due now: ${new Intl.NumberFormat("en-IN", { style: "currency", currency: selectedPlan?.currency || "INR" }).format(price / 100)}. Plan activates after verified payment.` : "Select a plan and billing cycle with a configured price."}{!gatewayConfigured && " Razorpay is not configured on the server."}</UiText>}<UiButton disabled={busy || !payable} className="mt-5 rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Creating…" : mode === "PAY_NOW" ? "Create company & open Razorpay" : "Create company"}</UiButton></UiForm>}
    <UiBox className="mt-6 flex items-center gap-2 rounded-lg border border-line bg-white px-3"><Search size={16} className="text-slate-400"/><UiInput aria-label="Search companies" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search company or workspace" className="h-11 w-full text-sm outline-none"/></UiBox>
    <UiBox className="mt-3 overflow-x-auto rounded-xl border border-line bg-white"><UiTable className="w-full min-w-[680px] text-left text-sm"><UiTableHead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500"><UiTableRow><UiTh className="px-4 py-3">Company</UiTh><UiTh className="px-4 py-3">Workspace</UiTh><UiTh className="px-4 py-3">Owner</UiTh><UiTh className="px-4 py-3">Created</UiTh><UiTh className="px-4 py-3">Subscription</UiTh></UiTableRow></UiTableHead><UiTableBody>{pagination.rows.map(company => <UiTableRow key={company.id} className="border-t border-line"><UiTd className="px-4 py-3 font-semibold"><Link href={`/admin-console/companies/${company.id}`} className="text-forest hover:underline">{company.name}</Link></UiTd><UiTd className="px-4 py-3 text-slate-600">{company.workspace_key}</UiTd><UiTd className="px-4 py-3 text-slate-600">{company.owner_email || "—"}</UiTd><UiTd className="px-4 py-3 text-slate-600">{new Date(company.created_at).toLocaleDateString("en-IN")}</UiTd><UiTd className="px-4 py-3"><UiSpan className="text-xs">{company.subscription_status || "No subscription"}</UiSpan>{["ONBOARDING", "TRIAL"].includes(company.subscription_status || "") && <UiButton disabled={busy} onClick={() => setPaymentCompany({ id: company.id, name: company.name })} className="ml-3 text-xs font-semibold text-forest underline">Collect payment</UiButton>}</UiTd></UiTableRow>)}{rows.length === 0 && <UiTableRow><UiTd className="px-4 py-8 text-center text-slate-500" colSpan={5}>No companies found.</UiTd></UiTableRow>}</UiTableBody></UiTable></UiBox>{pagination.controls}
  </UiBox>;
}
