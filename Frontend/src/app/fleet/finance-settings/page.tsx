"use client";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { requestInput } from "@/components/product-dialogs";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Driver = {
    id: string;
    name: string;
    status: string;
};
type Policy = {
    id: string;
    driver: Driver;
    basis: "MONTHLY" | "PER_TRIP" | "PER_KILOMETRE";
    rate: string;
    effective_from: string;
    effective_to: string | null;
};
const input = "mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-forest disabled:bg-slate-50";
const money = (value: string) => `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const basisLabel = (basis: Policy["basis"]) => basis === "MONTHLY" ? "Monthly salary" : basis === "PER_TRIP" ? "Per trip" : "Per kilometre";
export default function DriverFinanceSettingsPage() {
    const [drivers, setDrivers] = useState<Driver[]>([]);
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [canEdit, setCanEdit] = useState(false);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const load = useCallback(async () => {
        const [driversResponse, policiesResponse, profileResponse] = await Promise.all([apiFetch("/fleet/drivers"), apiFetch("/fleet/driver-pay-policies"), apiFetch("/auth/me")]);
        if (!driversResponse.ok || !policiesResponse.ok)
            throw new Error("Could not load driver finance settings.");
        setDrivers(await driversResponse.json());
        setPolicies(await policiesResponse.json());
        if (profileResponse.ok)
            setCanEdit(["OWNER", "FINANCE", "FLEET"].includes((await profileResponse.json()).role));
    }, []);
    useEffect(() => { void load().catch(error => setMessage(error.message)); }, [load]);
    async function createPolicy(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form).entries());
        if (!data.effective_to)
            delete data.effective_to;
        setBusy(true);
        setMessage("");
        const response = await apiFetch("/fleet/driver-pay-policies", { method: "POST", body: JSON.stringify(data) });
        const result = await response.json().catch(() => null);
        if (!response.ok)
            setMessage(result?.non_field_errors?.[0] || result?.error || "Could not save this pay policy.");
        else {
            form.reset();
            setMessage("Pay policy saved. New salary drafts use the monthly policy effective for their month.");
        }
        await load();
        setBusy(false);
    }
    async function closePolicy(policy: Policy) {
        const effectiveTo = (await requestInput("Last date this pay policy applies (YYYY-MM-DD)", new Date().toISOString().slice(0, 10)));
        if (!effectiveTo)
            return;
        setBusy(true);
        setMessage("");
        const response = await apiFetch(`/fleet/driver-pay-policies/${policy.id}`, { method: "PATCH", body: JSON.stringify({ effective_to: effectiveTo }) });
        const result = await response.json().catch(() => null);
        setMessage(response.ok ? "Policy end date saved." : result?.error || "Could not close this policy.");
        await load();
        setBusy(false);
    }
    return <UiMain className="w-full min-w-0 space-y-6 px-4 py-8 sm:px-6">
    <UiHeader><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Company administration · Fleet finance</UiText><UiH1 className="mt-1 text-2xl font-bold">Driver pay setup</UiH1><UiText className="mt-1 max-w-3xl text-sm text-slate-500">Configure effective-dated pay policies for this workspace. Monthly rates prefill salary drafts; trip and kilometre rates accrue from eligible trips.</UiText></UiHeader>
    {message && <UiAlert role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{message}</UiAlert>}
    <UiBox className="grid gap-3 sm:grid-cols-3"><Link href="/fleet/driver-salaries" className="rounded-xl border border-line bg-white p-4 hover:border-forest"><UiStrong className="text-sm">Salary settlements</UiStrong><UiSpan className="mt-1 block text-xs text-slate-500">Create, review, pay, and correct settlements; manage deductions and advances.</UiSpan></Link><Link href="/fleet/driver-salaries" className="rounded-xl border border-line bg-white p-4 hover:border-forest"><UiStrong className="text-sm">Driver finance ledger</UiStrong><UiSpan className="mt-1 block text-xs text-slate-500">Open the driver salary page to export dated ledger balances.</UiSpan></Link><Link href="/fleet/settings" className="rounded-xl border border-line bg-white p-4 hover:border-forest"><UiStrong className="text-sm">Fleet reminders</UiStrong><UiSpan className="mt-1 block text-xs text-slate-500">Set workspace reminder preferences and follow-up rules.</UiSpan></Link></UiBox>
    <UiForm onSubmit={event => void createPolicy(event)} className="grid gap-4 rounded-xl border border-line bg-white p-5 shadow-sm sm:grid-cols-2 lg:grid-cols-3">
      <UiBox className="sm:col-span-2 lg:col-span-3"><UiH2 className="font-semibold">Add a pay policy</UiH2><UiText className="mt-1 text-xs leading-5 text-slate-500">A driver can have one active policy for any date. Close the current policy before scheduling a replacement rate. Salary drafts remain subject to the existing independent approval process.</UiText></UiBox>
      <UiLabel className="text-xs font-semibold text-slate-600">Driver<UiSelect className={input} name="driver_id" required defaultValue="" disabled={!canEdit}><option value="" disabled>Select a driver</option>{drivers.filter(driver => driver.status === "ACTIVE").map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Pay basis<UiSelect className={input} name="basis" required defaultValue="MONTHLY" disabled={!canEdit}><option value="MONTHLY">Fixed monthly salary</option><option value="PER_TRIP">Fixed amount per trip</option><option value="PER_KILOMETRE">Rate per kilometre</option></UiSelect></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Monthly amount / rate<UiInput className={input} name="rate" type="number" min="0.01" step="0.01" required placeholder="₹ amount" disabled={!canEdit}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Effective from<UiInput className={input} name="effective_from" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} disabled={!canEdit}/></UiLabel>
      <UiLabel className="text-xs font-semibold text-slate-600">Effective to (optional)<UiInput className={input} name="effective_to" type="date" disabled={!canEdit}/></UiLabel>
      {canEdit ? <UiButton disabled={busy || drivers.length === 0} className="self-end rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save pay policy"}</UiButton> : <UiText className="self-end text-xs text-slate-500">Only workspace owners, finance users, and fleet operators can edit pay policies.</UiText>}
    </UiForm>
    <UiSection className="rounded-xl border border-line bg-white p-5 shadow-sm"><UiBox className="flex items-center justify-between gap-3"><UiBox><UiH2 className="font-semibold">Policy history</UiH2><UiText className="mt-1 text-xs text-slate-500">Previously applied rates stay visible so existing trip earnings keep their original rate snapshots.</UiText></UiBox><UiSpan className="text-xs text-slate-500">{policies.length} policies</UiSpan></UiBox><UiBox className="mt-3 divide-y divide-line">{policies.map(policy => <UiBox key={policy.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0"><UiText className="text-sm"><UiStrong>{policy.driver.name}</UiStrong><UiSpan className="text-slate-500"> · {basisLabel(policy.basis)} · {money(policy.rate)}{policy.basis === "MONTHLY" ? "/month" : policy.basis === "PER_TRIP" ? "/trip" : "/km"}</UiSpan><UiSpan className="block text-xs text-slate-500">{policy.effective_from} to {policy.effective_to || "Open ended"}</UiSpan></UiText>{canEdit && !policy.effective_to && <UiButton disabled={busy} onClick={() => void closePolicy(policy)} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Close policy</UiButton>}</UiBox>)}{policies.length === 0 && <UiText className="py-4 text-sm text-slate-500">No pay policies configured for this workspace yet.</UiText>}</UiBox></UiSection>
  </UiMain>;
}
