"use client";
import { UiAlert, UiBox, UiButton, UiForm, UiH1, UiH2, UiInput, UiLabel, UiSpan, UiText } from "@/components/admin/admin-ui";
import { FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";
import { ExtractionHealth } from "@/components/extraction-health";
export default function AdminSecurityPage() {
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    async function changePassword(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        const response = await apiFetch("/admin/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: form.get("current_password"), new_password: form.get("new_password") }) });
        const data = await response.json();
        setBusy(false);
        if (!response.ok) {
            setMessage(data.error || "Could not change password.");
            return;
        }
        formElement.reset();
        setMessage("Password changed. Use your new password next time you sign in.");
    }
    async function createSuperAdmin(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        const response = await apiFetch("/admin/staff/super-admins", { method: "POST", body: JSON.stringify({ name: form.get("name"), email: form.get("email"), password: form.get("password") }) });
        const data = await response.json();
        setBusy(false);
        if (!response.ok) {
            setMessage(data.error || "Could not create Super Admin.");
            return;
        }
        formElement.reset();
        setMessage(`Super Admin ${data.email} was created. Share the initial password with them securely.`);
    }
    return <UiBox className="w-full"><UiText className="text-[10px] font-bold uppercase tracking-[.15em] text-forest">Control plane access</UiText><UiH1 className="mt-2 text-3xl font-bold">Security</UiH1><UiText className="mt-2 text-sm text-slate-500">Manage your own password and provision trusted Super Admins.</UiText>
    {message && <UiAlert role="status" className="mt-5 rounded-lg border border-line bg-white p-3 text-sm">{message}</UiAlert>}
    <ExtractionHealth />
    <UiBox className="mt-6 grid gap-5 lg:grid-cols-2">
      <UiForm onSubmit={changePassword} className="space-y-4 rounded-xl border border-line bg-white p-5"><UiBox><UiH2 className="font-bold">Change your password</UiH2><UiText className="mt-1 text-xs text-slate-500">Choose at least 12 characters. Your current password is required.</UiText></UiBox><UiLabel className="block text-xs font-semibold text-slate-600">Current password<UiInput name="current_password" type="password" autoComplete="current-password" required className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel><UiLabel className="block text-xs font-semibold text-slate-600">New password<UiInput name="new_password" type="password" autoComplete="new-password" minLength={12} required className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel><UiButton disabled={busy} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Saving…" : "Change password"}</UiButton></UiForm>
      <UiForm onSubmit={createSuperAdmin} className="space-y-4 rounded-xl border border-line bg-white p-5"><UiBox><UiH2 className="font-bold">Create a Super Admin</UiH2><UiText className="mt-1 text-xs text-slate-500">They will have full access to companies, billing, plans and staff administration.</UiText></UiBox><UiLabel className="block text-xs font-semibold text-slate-600">Full name<UiInput name="name" required autoComplete="name" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel><UiLabel className="block text-xs font-semibold text-slate-600">Email address<UiInput name="email" type="email" required autoComplete="email" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/></UiLabel><UiLabel className="block text-xs font-semibold text-slate-600">Initial password<UiInput name="password" type="password" minLength={12} required autoComplete="new-password" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm"/><UiSpan className="mt-1 block font-normal text-slate-400">At least 12 characters; give it to the new admin securely.</UiSpan></UiLabel><UiButton disabled={busy} className="rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Creating…" : "Create Super Admin"}</UiButton></UiForm>
    </UiBox>
  </UiBox>;
}
