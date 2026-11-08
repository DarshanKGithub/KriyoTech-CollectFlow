"use client";
import { ProductName } from "@/components/partner-brand";

import { InvitationProgress } from "@/components/workflow-progress";
import { UiAlert, UiButton, UiForm, UiH1, UiInput, UiLabel, UiMain, UiSection, UiSpan, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
export default function AcceptInvitePage() {
    const [token, setToken] = useState("");
    const [message, setMessage] = useState("");
    const [done, setDone] = useState(false);
    const [busy, setBusy] = useState(false);
    useEffect(() => { setToken(new URLSearchParams(window.location.search).get("token") || ""); }, []);
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        const form = new FormData(event.currentTarget);
        const response = await apiFetch("/auth/accept-invitation", { method: "POST", body: JSON.stringify({ token, password: form.get("password"), name: form.get("name") }) });
        const data = await response.json();
        setBusy(false);
        if (!response.ok) {
            setMessage(data.error?.message || data.error || "Invitation could not be accepted.");
            return;
        }
        setDone(true);
        setMessage("Your account is ready. Sign in to enter your workspace.");
    }
    return <UiMain className="grid min-h-screen place-items-center bg-[#F5F7F5] p-5"><UiSection className="w-full max-w-md rounded-2xl border border-line bg-white p-7"><UiText className="text-[10px] font-bold uppercase tracking-[.15em] text-forest">Workspace invitation</UiText><UiH1 className="mt-2 text-2xl font-bold">Set up your <ProductName/> account</UiH1><UiText className="mt-2 text-sm text-slate-500">Choose a secure password to accept your company invitation.</UiText><InvitationProgress complete={done}/>{!token && <UiAlert role="alert" className="mt-4 text-sm text-rose-700">This invitation link is missing its token.</UiAlert>}{message && <UiAlert role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{message}</UiAlert>}{!done && <UiForm onSubmit={submit} className="mt-5 space-y-4"><UiLabel className="block text-xs font-semibold">Your name<UiInput name="name" required className="mt-1.5 min-h-11 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel><UiLabel className="block text-xs font-semibold">Password<UiInput name="password" type="password" minLength={10} required autoComplete="new-password" className="mt-1.5 min-h-11 w-full rounded-lg border border-line px-3 text-sm font-normal"/><UiSpan className="mt-1 block font-normal text-slate-500">Use at least 10 characters.</UiSpan></UiLabel><UiButton disabled={busy || !token} className="w-full rounded-lg bg-forest py-3 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Setting up…" : "Accept invitation"}</UiButton></UiForm>}{done && <Link href="/login" className="mt-5 inline-block rounded-lg bg-forest px-4 py-3 text-sm font-semibold text-white">Go to sign in</Link>}</UiSection></UiMain>;
}
