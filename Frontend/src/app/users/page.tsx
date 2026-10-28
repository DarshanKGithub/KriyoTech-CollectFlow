"use client";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { ContentSkeleton } from "@/components/content-skeleton";
import { UiBox, UiButton, UiForm, UiH1, UiInput, UiMain, UiSection, UiSelect, UiSpan, UiSpinner, UiStrong, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Send } from "lucide-react";
type Member = {
    id: string;
    email: string;
    name: string;
    role: string;
    is_active: boolean;
};
const roles = ["OWNER", "FINANCE", "PURCHASE", "STORE", "APPROVER", "AUDITOR", "FLEET", "DRIVER"];
export default function UsersPage() {
    const [rows, setRows] = useState<Member[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const [canManage, setCanManage] = useState(false);
    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [r, p] = await Promise.all([apiFetch("/users"), apiFetch("/auth/me")]);
            if (!r.ok)
                throw new Error(r.status === 401 ? "Sign in to manage workspace users." : "Could not load users.");
            setRows(await r.json());
            if (p.ok) {
                const profile = await p.json();
                setCanManage(profile.role === "OWNER");
            }
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not load users.");
        }
        finally {
            setLoading(false);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    async function invite(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        setBusy("invite");
        try {
            const r = await apiFetch("/users/invite", { method: "POST", body: JSON.stringify({ email: form.get("email"), role: form.get("role") }) });
            const data = await r.json();
            if (!r.ok)
                throw new Error(data.error?.message || "Could not invite user.");
            formElement.reset();
            setMessage(`Invitation created for ${data.email}. The invite link was sent through the configured email backend.`);
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not invite user.");
        }
        finally {
            setBusy("");
        }
    }
    async function changeRole(member: Member, role: string) {
        setBusy(member.id);
        try {
            const r = await apiFetch(`/users/${member.id}/role`, { method: "PATCH", body: JSON.stringify({ role }) });
            const data = await r.json();
            if (!r.ok)
                throw new Error(data.error?.message || "Could not change role.");
            setMessage(`Role updated for ${member.email}.`);
            await load();
        }
        catch (e) {
            setMessage(e instanceof Error ? e.message : "Could not update role.");
        }
        finally {
            setBusy("");
        }
    }
    const pagination = useListPagination(rows, "");
    return <UiMain className="w-full min-w-0 min-h-screen px-5 py-8"><Link href="/" className="text-xs font-semibold text-forest">← Overview</Link><UiBox className="mt-6"><UiH1 className="text-2xl font-bold">Users and roles</UiH1><UiText className="mt-1 text-sm text-slate-500">Control who can review, match, approve, and audit workspace invoices.</UiText></UiBox>{message && <WorkflowFeedback message={message} onRefresh={()=>load()} />}{canManage && <UiForm onSubmit={invite} className="mt-5 grid gap-3 rounded-xl border border-line bg-white p-4 shadow-card sm:grid-cols-[1fr_180px_auto]"><UiInput type="email" name="email" required placeholder="teammate@company.com" className="rounded-lg border border-line px-3 py-2.5 text-xs"/><UiSelect name="role" className="rounded-lg border border-line px-3 py-2.5 text-xs">{roles.filter(role => role !== "OWNER").map(role => <option key={role} value={role}>{role}</option>)}</UiSelect><UiButton disabled={busy === "invite"} className="inline-flex items-center justify-center gap-2 rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === "invite" ? <UiSpinner className="animate-spin" size={14}/> : <Send size={14}/>}Invite user</UiButton></UiForm>}<UiSection className="mt-5 overflow-hidden rounded-xl border border-line bg-white shadow-card">{loading ? <ContentSkeleton variant="table" label="Loading users" /> : rows.length === 0 ? <EmptyState description="No members found in this workspace." onAction={()=>void load()} actionLabel="Refresh data" /> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[700px] text-left"><UiTableHead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><UiTableRow>{["Member", "Role", "Access", "Update role"].map(x => <UiTh key={x} className="px-5 py-3">{x}</UiTh>)}</UiTableRow></UiTableHead><UiTableBody>{pagination.rows.map(member => <UiTableRow key={member.id} className="border-t border-line text-xs"><UiTd className="px-5 py-4"><UiStrong className="block">{member.name || member.email}</UiStrong>{member.name && <UiSpan className="text-slate-500">{member.email}</UiSpan>}</UiTd><UiTd className="px-5 py-4"><UiSpan className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold">{member.role}</UiSpan></UiTd><UiTd className="px-5 py-4">{member.is_active ? <UiSpan className="text-emerald-700">Active</UiSpan> : <UiSpan className="text-rose-700">Inactive</UiSpan>}</UiTd><UiTd className="px-5 py-4">{canManage ? <UiBox className="flex items-center gap-2"><UiSelect aria-label={`Role for ${member.email}`} value={member.role} disabled={busy === member.id} onChange={event => void changeRole(member, event.target.value)} className="rounded-md border border-line px-2 py-1.5 text-[11px]">{roles.map(role => <option key={role}>{role}</option>)}</UiSelect>{busy === member.id && <UiSpinner size={13} className="animate-spin"/>}</UiBox> : "—"}</UiTd></UiTableRow>)}</UiTableBody></UiTable></UiBox>}{pagination.controls}</UiSection></UiMain>;
}
