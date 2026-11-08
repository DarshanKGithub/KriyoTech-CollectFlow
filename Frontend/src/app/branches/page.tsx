"use client";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSmall, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Building2, Plus, UserRoundPlus } from "lucide-react";
type Member = {
    membership_id: string;
    user_id: string;
    email: string;
    role: string;
};
type Branch = {
    id: string;
    name: string;
    code: string;
    active: boolean;
    is_default: boolean;
    members: Member[];
};
type WorkspaceMember = {
    id: string;
    email: string;
    name: string;
    role: string;
    is_active: boolean;
};
export default function BranchesPage() {
    const [branches, setBranches] = useState<Branch[]>([]);
    const [members, setMembers] = useState<WorkspaceMember[]>([]);
    const [role, setRole] = useState("");
    const [name, setName] = useState("");
    const [code, setCode] = useState("");
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState(false);
    async function load() {
        const [branchResponse, memberResponse, profileResponse] = await Promise.all([apiFetch("/branches"), apiFetch("/users"), apiFetch("/auth/me")]);
        if (branchResponse.ok) {
            const data = await branchResponse.json();
            setBranches(data.branches);
        }
        if (memberResponse.ok)
            setMembers(await memberResponse.json());
        if (profileResponse.ok)
            setRole((await profileResponse.json()).role);
    }
    useEffect(() => { void load(); }, []);
    async function create(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setNotice("");
        const response = await apiFetch("/branches", { method: "POST", body: JSON.stringify({ name, code }) });
        const data = await response.json();
        setBusy(false);
        if (!response.ok) {
            setNotice(data.error || "Could not create branch.");
            return;
        }
        setName("");
        setCode("");
        setNotice("Branch created.");
        await load();
    }
    async function assign(branch: Branch, membershipId: string, action: "assign" | "unassign") {
        setBusy(true);
        setNotice("");
        const response = await apiFetch("/branch-assignments", { method: "POST", body: JSON.stringify({ branch_id: branch.id, membership_id: membershipId, action }) });
        const data = await response.json();
        setBusy(false);
        if (!response.ok) {
            setNotice(data.error || "Could not update branch access.");
            return;
        }
        setNotice(action === "assign" ? "Member assigned to branch." : "Member removed from branch.");
        await load();
    }
    async function toggle(branch: Branch) {
        setBusy(true);
        setNotice("");
        const response = await apiFetch("/branches/" + branch.id, { method: "PATCH", body: JSON.stringify({ active: !branch.active }) });
        const data = await response.json();
        setBusy(false);
        if (!response.ok) {
            setNotice(data.error || "Could not update branch.");
            return;
        }
        await load();
    }
    const canManage = role === "OWNER";
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><UiText className="text-[10px] font-bold uppercase tracking-[.16em] text-forest">Company structure</UiText><UiH1 className="mt-2 text-2xl font-bold">Branches and access</UiH1><UiText className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">Manage branch directory and assign workspace members. Assignments are recorded in the audit log. Branch-level filtering for invoices and payments is not enabled yet.</UiText>{notice && <UiAlert role="status" className="mt-4 rounded-lg border border-line bg-white px-4 py-3 text-sm text-slate-600">{notice}</UiAlert>}
    {canManage && <UiForm onSubmit={create} className="mt-6 grid gap-3 rounded-xl border border-line bg-white p-5 shadow-card sm:grid-cols-[1fr_1fr_auto]"><UiLabel className="text-xs font-semibold">Branch name<UiInput required maxLength={120} value={name} onChange={event => setName(event.target.value)} placeholder="Pune office" className="mt-1.5 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiLabel className="text-xs font-semibold">Code<UiInput maxLength={80} value={code} onChange={event => setCode(event.target.value)} placeholder="pune-office" className="mt-1.5 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiButton disabled={busy} className="mt-auto inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-forest px-4 text-xs font-semibold text-white disabled:opacity-50"><Plus size={15}/>Add branch</UiButton></UiForm>}
    <UiSection className="mt-6 grid gap-4 md:grid-cols-2">{branches.map(branch => <UiArticle key={branch.id} className="rounded-xl border border-line bg-white p-5 shadow-card"><UiHeader className="flex items-start justify-between gap-3"><UiBox className="flex items-center gap-3"><UiSpan className="grid h-10 w-10 place-items-center rounded-lg bg-mint text-forest"><Building2 size={18}/></UiSpan><UiBox><UiH2 className="text-sm font-bold">{branch.name}</UiH2><UiText className="mt-0.5 text-xs text-slate-500">{branch.code}{branch.is_default ? " · Default branch" : ""}</UiText></UiBox></UiBox><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${branch.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{branch.active ? "Active" : "Inactive"}</UiSpan></UiHeader>{canManage && <UiBox className="mt-4 flex gap-2"><UiSelect aria-label={`Assign member to ${branch.name}`} disabled={!branch.active || busy} defaultValue="" onChange={event => {
                    const id = event.target.value;
                    if (id)
                        void assign(branch, id, "assign");
                    event.target.value = "";
                }} className="min-w-0 flex-1 rounded-lg border border-line bg-white px-3 py-2 text-xs"><option value="">Assign a member…</option>{members.filter(member => member.is_active && !branch.members.some(item => item.membership_id === member.id)).map(member => <option key={member.id} value={member.id}>{member.name || member.email} · {member.role}</option>)}</UiSelect><UiButton disabled={busy || branch.is_default} onClick={() => void toggle(branch)} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-40">{branch.active ? "Deactivate" : "Activate"}</UiButton></UiBox>}<UiBox className="mt-5 border-t border-line pt-4"><UiH3 className="flex items-center gap-2 text-xs font-semibold"><UserRoundPlus size={14}/>Assigned members <UiSpan className="text-slate-400">{branch.members.length}</UiSpan></UiH3>{branch.members.length ? <ul className="mt-3 space-y-2">{branch.members.map(member => <li key={member.membership_id} className="flex items-center justify-between gap-3 text-xs"><UiSpan className="min-w-0"><UiStrong className="block truncate">{member.email}</UiStrong><UiSmall className="text-slate-400">{member.role.replaceAll("_", " ")}</UiSmall></UiSpan>{canManage && <UiButton disabled={busy} onClick={() => void assign(branch, member.membership_id, "unassign")} className="rounded border border-line px-2 py-1 text-[10px] text-slate-500 disabled:opacity-50">Remove</UiButton>}</li>)}</ul> : <UiText className="mt-2 text-xs text-slate-400">No members assigned.</UiText>}</UiBox></UiArticle>)}{!branches.length && <ContentSkeleton variant="table" label="Loading branches" />}</UiSection>
  </UiMain>;
}
