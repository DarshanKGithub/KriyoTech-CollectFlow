"use client";
import { Switch } from "@/components/ui/switch";
import { PageSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiSection, UiSmall, UiSpan, UiStrong, UiText } from "@/components/admin/admin-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Plan = {
    id: string;
    name: string;
    slug: string;
    description: string;
    is_active: boolean;
    is_public: boolean;
    monthly_price: number | null;
    quarterly_price: number | null;
    annual_price: number | null;
    invoice_limit: number | null;
    user_limit: number | null;
    trial_days: number;
};
type Feature = {
    key: string;
    name: string;
    description: string;
};
type Catalog = {
    features: Feature[];
    plan_entitlements: {
        plan_id: string;
        feature_key: string;
        enabled: boolean;
        limit_value: number | null;
    }[];
};
const rupees = (paise: number | null) => paise == null ? "Custom" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(paise / 100);
export default function PlansPage() {
    const [plans, setPlans] = useState<Plan[]>([]);
    const [catalog, setCatalog] = useState<Catalog>({ features: [], plan_entitlements: [] });
    const [selected, setSelected] = useState("");
    const [message, setMessage] = useState("");
    const [initialLoading, setInitialLoading] = useState(true);
    const [createOpen, setCreateOpen] = useState(false);
    const [featureBusy, setFeatureBusy] = useState(false);
    const load = useCallback(async () => { const [p, f] = await Promise.all([apiFetch("/admin/plans"), apiFetch("/admin/features")]); if (p.ok) {
        const data = await p.json();
        setPlans(data);
        setSelected(current => current || (data.length ? data[0].id : ""));
    } if (f.ok)
        setCatalog(await f.json()); }, []);
    useEffect(() => { void load().catch(() => setMessage("Could not load plans and features. Please refresh to retry.")).finally(() => setInitialLoading(false)); }, [load]);
    async function createPlan(e: FormEvent<HTMLFormElement>) { e.preventDefault(); const form = new FormData(e.currentTarget); const price = (key: string) => { const v = String(form.get(key) || "").trim(); return v === "" ? null : Math.round(Number(v) * 100); }; const payload = { name: form.get("name"), slug: form.get("slug"), description: form.get("description"), monthly_price: price("monthly"), quarterly_price: price("quarterly"), annual_price: price("annual"), invoice_limit: form.get("invoice_limit") ? Number(form.get("invoice_limit")) : null, user_limit: form.get("user_limit") ? Number(form.get("user_limit")) : null, trial_days: Number(form.get("trial_days") || 0) }; const r = await apiFetch("/admin/plans", { method: "POST", body: JSON.stringify(payload) }); const data = await r.json(); if (!r.ok) {
        setMessage(JSON.stringify(data));
        return;
    } setMessage("Plan created."); setCreateOpen(false); await load(); }
    async function toggleFeature(featureKey: string, enabled: boolean) {
        if (featureBusy) return;
        setFeatureBusy(true);
        try {
            const response = await apiFetch(`/admin/plans/${selected}/features`, { method: "PATCH", body: JSON.stringify({ feature_key: featureKey, enabled }) });
            if (!response.ok) throw new Error("Could not update this entitlement.");
            await load(); setMessage("Plan feature access updated.");
        } catch { setMessage("Could not update this entitlement. Please retry."); }
        finally { setFeatureBusy(false); }
    }
    const activePlan = plans.find(p => p.id === selected);
    if (initialLoading) return <PageSkeleton variant="cards" label="Loading plans and features" />;
    return <UiBox><UiBox className="flex flex-wrap items-end justify-between gap-4"><UiBox><UiText className="text-[10px] font-bold uppercase tracking-[.15em] text-forest">Commercial configuration</UiText><UiH1 className="mt-2 text-3xl font-bold">Plans & features</UiH1><UiText className="mt-2 text-sm text-slate-500">Prices are stored in paise. Feature access is configured separately from plan names.</UiText></UiBox><UiButton onClick={() => setCreateOpen(!createOpen)} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white">{createOpen ? "Close" : "Create plan"}</UiButton></UiBox>
    {message && <UiAlert role="status" className="mt-4 rounded-lg border border-line bg-white p-3 text-sm">{message}</UiAlert>}
    {createOpen && <UiForm onSubmit={createPlan} className="mt-5 rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Create configurable plan</UiH2><UiBox className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[["name", "Plan name"], ["slug", "Stable slug"], ["description", "Description"], ["monthly", "Monthly price (₹)"], ["quarterly", "Quarterly price (₹)"], ["annual", "Annual price (₹)"], ["invoice_limit", "Monthly invoice limit"], ["user_limit", "User limit"], ["trial_days", "Trial days"]].map(([name, label]) => <UiLabel key={name} className="text-xs font-semibold text-slate-600">{label}<UiInput name={name} required={name === "name" || name === "slug"} type={["monthly", "quarterly", "annual", "invoice_limit", "user_limit", "trial_days"].includes(name) ? "number" : "text"} min="0" step={["monthly", "quarterly", "annual"].includes(name) ? "0.01" : "1"} className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel>)}</UiBox><UiButton className="mt-4 rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white">Save plan</UiButton></UiForm>}
    <UiBox className="mt-6 grid gap-4 lg:grid-cols-[320px_1fr]"><UiSection className="space-y-2">{plans.map(p => <UiButton key={p.id} onClick={() => setSelected(p.id)} disabled={featureBusy} className={`block h-auto w-full whitespace-normal rounded-xl border bg-white p-4 text-left ${selected === p.id ? "border-forest ring-1 ring-forest" : "border-line"}`}><UiSpan className="flex justify-between font-semibold">{p.name}<UiSpan className={`text-[10px] uppercase ${p.is_active ? "text-emerald-700" : "text-slate-400"}`}>{p.is_active ? "Active" : "Archived"}</UiSpan></UiSpan><UiSpan className="mt-2 block text-xs text-slate-500">Monthly {rupees(p.monthly_price)} · Annual {rupees(p.annual_price)}</UiSpan><UiSpan className="mt-1 block text-[10px] text-slate-400">{p.invoice_limit ?? "Custom"} invoices · {p.user_limit ?? "Custom"} users</UiSpan></UiButton>)}</UiSection>
      <UiSection className="rounded-xl border border-line bg-white p-5">{activePlan ? <><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiH2 className="text-xl font-bold">{activePlan.name} entitlements</UiH2><UiText className="mt-1 text-xs text-slate-500">Toggle to update default access for companies on this plan. Signed-in users refresh access within 10 seconds. Company-specific overrides take priority.</UiText></UiBox><UiSpan className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">{activePlan.slug}</UiSpan></UiBox><UiBox className="mt-5 divide-y divide-line">{catalog.features.map(feature => { const row = catalog.plan_entitlements.find(r => r.plan_id === selected && r.feature_key === feature.key); return <UiLabel key={feature.key} className={`flex min-h-14 items-center gap-3 ${feature.key === "fleet_management" ? "rounded-lg bg-emerald-50/60 px-3" : ""}`}><Switch className="data-[state=checked]:border-emerald-700 data-[state=checked]:bg-emerald-600 data-[state=unchecked]:border-slate-400 data-[state=unchecked]:bg-slate-300 [&>span]:bg-white" aria-label={feature.name} checked={Boolean(row?.enabled)} disabled={featureBusy} onCheckedChange={enabled => void toggleFeature(feature.key, enabled)}/><UiSpan className="flex-1"><UiStrong className="block text-sm">{feature.name}</UiStrong><UiSmall className="text-xs text-slate-500">{feature.key}</UiSmall></UiSpan><UiSpan className={`rounded-full px-2.5 py-1 text-xs font-semibold ${row?.enabled ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>{row?.enabled ? "Enabled" : "Disabled"}</UiSpan><UiSpan className="hidden max-w-[240px] text-xs leading-5 text-slate-400 xl:block">{feature.description}</UiSpan></UiLabel>; })}</UiBox></> : <UiText className="text-sm text-slate-500">Seed the catalog, then select a plan.</UiText>}</UiSection></UiBox>
  </UiBox>;
}
