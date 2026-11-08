"use client";
import { GroupedFeatureAccess } from "@/components/admin/feature-catalog";
import { PageSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiBox, UiButton, UiH1, UiH2, UiInput, UiLabel, UiSection, UiSmall, UiSpan, UiStrong, UiText } from "@/components/admin/admin-ui";
import { requestConfirmation } from "@/components/product-dialogs";
import { AppLink as Link } from "@/components/admin/admin-ui";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Detail = {
    company: {
        id: string;
        name: string;
        workspace_key: string;
        owner_email: string;
    };
    users: {
        email: string;
        name: string;
        role: string;
        active: boolean;
    }[];
    subscriptions: {
        id: string;
        plan_name: string;
        status: string;
        billing_cycle: string;
        trial_ends_at: string | null;
    }[];
    entitlements: {
        features: Record<string, {
            enabled: boolean;
            limit_value: number | null;
            source: string; name?:string; solution_name?:string; monthly_price?:number|null; price_basis?:string;
        }>;
    };
    usage: {
        id: string;
        metric: string;
        used_count: number;
        limit_value: number | null;
        period_start: string;
    }[];
    payments?: {
        id: string;
        amount: number;
        currency: string;
        status: string;
        created_at: string;
    }[];
    audit?: {
        id: string;
        action: string;
        actor_email: string;
        created_at: string;
        reason: string;
    }[];
};
const states = ["ONBOARDING", "TRIAL", "ACTIVE", "PAST_DUE", "GRACE_PERIOD", "SUSPENDED", "CANCELLED", "CHURNED"];
export default function CompanyDetailPage() {
    const { tenantId } = useParams<{
        tenantId: string;
    }>();
    const router = useRouter();
    const [data, setData] = useState<Detail | null>(null);
    const [reason, setReason] = useState("");
    const [message, setMessage] = useState("");
    const [deleteName, setDeleteName] = useState("");
    const [deleteReason, setDeleteReason] = useState("");
    const [featureBusy, setFeatureBusy] = useState(false);
    const load = useCallback(async () => { const r = await apiFetch(`/admin/companies/${tenantId}`); if (r.ok)
        setData(await r.json());
    else
        setMessage("Company details could not be loaded."); }, [tenantId]);
    useEffect(() => { if (tenantId)
        void load(); }, [tenantId, load]);
    async function changeState(status: string) { if (!reason.trim()) {
        setMessage("Enter a reason before changing lifecycle status.");
        return;
    } if (["SUSPENDED", "CANCELLED", "CHURNED"].includes(status) && !(await requestConfirmation(`Change ${data?.company.name} to ${status.replaceAll("_", " ")}? This restricts company access.`)))
        return; const r = await apiFetch(`/admin/companies/${tenantId}/lifecycle`, { method: "POST", body: JSON.stringify({ status, reason }) }); const body = await r.json(); if (!r.ok) {
        setMessage(body.error || "Lifecycle update failed.");
        return;
    } setReason(""); setMessage(`Company status changed to ${status}.`); void load(); }
    async function setEntitlement(feature_key: string, enabled: boolean) {
        if (featureBusy) return;
        setFeatureBusy(true);
        try {
            const r = await apiFetch(`/admin/companies/${tenantId}/entitlements`, { method: "PATCH", body: JSON.stringify({ feature_key, enabled, reason: reason || "Company detail admin change" }) });
            if (!r.ok) throw new Error("Could not update entitlement.");
            await load(); setMessage("Feature override recorded and audited.");
        } catch { setMessage("Could not update entitlement. Please retry."); }
        finally { setFeatureBusy(false); }
    }
    async function deleteCompany() { if (deleteName !== data?.company.name || deleteReason.trim().length < 8) {
        setMessage("Type the exact company name and provide a reason of at least 8 characters.");
        return;
    } if (!(await requestConfirmation(`Delete ${data.company.name}? Member access will be revoked. Accounting and audit data will be retained.`)))
        return; const r = await apiFetch(`/admin/companies/${tenantId}`, { method: "DELETE", body: JSON.stringify({ confirm_name: deleteName, reason: deleteReason }) }); const body = await r.json(); if (!r.ok) {
        setMessage(body.error || "Company deletion failed.");
        return;
    } router.push("/admin-console/companies"); }
    if (!data)
        return message ? <UiText role="alert" className="text-sm text-slate-500">{message}</UiText> : <PageSkeleton variant="form" label="Loading company details" />;
    return <UiBox><Link href="/admin-console/companies" className="text-xs font-semibold text-forest">← Companies</Link><UiBox className="mt-3 flex flex-wrap items-start justify-between gap-4"><UiBox><UiText className="text-[10px] font-bold uppercase tracking-wider text-forest">Customer account</UiText><UiH1 className="mt-2 text-3xl font-bold">{data.company.name}</UiH1><UiText className="mt-1 text-sm text-slate-500">{data.company.workspace_key} · Owner {data.company.owner_email || "pending"}</UiText></UiBox><UiBox className="rounded-xl border border-line bg-white px-4 py-3 text-sm"><UiText className="text-xs text-slate-500">Current subscription</UiText><UiStrong>{data.subscriptions[0]?.plan_name || "No plan"} · {data.subscriptions[0]?.status || "—"}</UiStrong></UiBox></UiBox>
    {message && <UiAlert role="status" className="mt-4 rounded-lg border border-line bg-white p-3 text-sm">{message}</UiAlert>}
    <UiSection className="mt-5 rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Lifecycle control</UiH2><UiText className="mt-1 text-xs text-slate-500">Every transition requires a reason and creates an append-only audit event.</UiText><UiBox className="mt-4 flex flex-wrap gap-2"><UiInput value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason for change" className="min-h-10 min-w-[220px] flex-1 rounded-lg border border-line px-3 text-sm"/>{states.map(state => <UiButton key={state} onClick={() => void changeState(state)} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold hover:bg-slate-50">{state.replaceAll("_", " ")}</UiButton>)}</UiBox></UiSection>
    <UiSection className="mt-5 rounded-xl border border-rose-200 bg-white p-5"><UiH2 className="font-bold text-rose-800">Delete company</UiH2><UiText className="mt-1 text-xs leading-5 text-slate-600">Revokes all workspace member access and removes this company from the active portfolio. Billing, invoice, and audit records are retained for accounting and compliance. This action is audited.</UiText><UiBox className="mt-4 grid gap-3 md:grid-cols-2"><UiLabel className="text-xs font-semibold text-slate-600">Type <UiStrong>{data.company.name}</UiStrong> to confirm<UiInput value={deleteName} onChange={e => setDeleteName(e.target.value)} className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel><UiLabel className="text-xs font-semibold text-slate-600">Reason<UiInput value={deleteReason} onChange={e => setDeleteReason(e.target.value)} minLength={8} placeholder="Required for the audit record" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel></UiBox><UiButton onClick={() => void deleteCompany()} className="mt-3 rounded-lg bg-rose-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-rose-800">Delete company and revoke access</UiButton><UiText className="mt-2 text-[10px] text-slate-400">Super Admin permission required.</UiText></UiSection>
    <UiBox className="mt-5 grid gap-4 xl:grid-cols-2"><UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Feature access</UiH2><UiText className="mt-1 text-xs text-slate-500">Changes apply to every user in this company and are audited. Sidebar access refreshes within 10 seconds; API permissions are checked on each request. Company overrides take priority over plan defaults.</UiText><GroupedFeatureAccess features={Object.entries(data.entitlements.features||{}).map(([key,item])=>({key,name:item.name||key.replaceAll("_"," "),description:"",...item}))} busy={featureBusy} onToggle={(key,enabled)=>void setEntitlement(key,enabled)}/></UiSection>
      <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Users and usage</UiH2><UiBox className="mt-3 space-y-2">{data.users.map(user => <UiBox key={user.email} className="flex justify-between rounded-lg bg-slate-50 p-3 text-xs"><UiSpan>{user.name || user.email}<UiSmall className="ml-2 text-slate-500">{user.email}</UiSmall></UiSpan><UiStrong>{user.role}</UiStrong></UiBox>)}{data.usage.map(row => <UiBox key={row.id} className="flex justify-between border-t border-line py-2 text-xs"><UiSpan>{row.metric} · {row.period_start}</UiSpan><UiStrong>{row.used_count} / {row.limit_value ?? "∞"}</UiStrong></UiBox>)}</UiBox></UiSection></UiBox>
    <UiBox className="mt-5 grid gap-4 xl:grid-cols-2">{data.payments && <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Payment records</UiH2>{data.payments.length ? data.payments.map(p => <UiBox key={p.id} className="flex justify-between border-b border-line py-3 text-xs"><UiSpan>{p.status} · {new Date(p.created_at).toLocaleDateString("en-IN")}</UiSpan><UiStrong>{p.currency} {(p.amount / 100).toLocaleString("en-IN")}</UiStrong></UiBox>) : <UiText className="mt-3 text-xs text-slate-500">No recorded payments.</UiText>}</UiSection>}{data.audit && <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">Recent admin audit</UiH2>{data.audit.map(item => <UiBox key={item.id} className="border-b border-line py-3 text-xs"><UiStrong>{item.action}</UiStrong><UiSpan className="ml-2 text-slate-500">by {item.actor_email || "deleted account"} · {new Date(item.created_at).toLocaleString("en-IN")}</UiSpan>{item.reason && <UiText className="mt-1 text-slate-500">{item.reason}</UiText>}</UiBox>)}</UiSection>}</UiBox>
  </UiBox>;
}
