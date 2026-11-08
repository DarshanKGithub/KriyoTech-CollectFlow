"use client";
import { ProductName } from "@/components/partner-brand";

import { partnerHeaders } from "@/lib/partner";
import { UiAlert, UiButton, UiForm, UiH1, UiInput, UiLabel, UiMain, UiSection, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useEffect, useState } from "react";
import { ArrowLeft, LockKeyhole, ReceiptIndianRupee } from "lucide-react";
import { API_URL } from "@/lib/api";
export default function ResetPasswordPage() {
    const [uid, setUid] = useState("");
    const [token, setToken] = useState("");
    const [message, setMessage] = useState("");
    const [done, setDone] = useState(false);
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        setUid(params.get("uid") || "");
        setToken(params.get("token") || "");
    }, []);
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        const form = new FormData(event.currentTarget);
        try {
            const response = await fetch(`${API_URL}/auth/password-reset/confirm`, { method: "POST", headers: { "Content-Type": "application/json", ...partnerHeaders() }, body: JSON.stringify({ uid, token, new_password: form.get("new_password") }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.error || "This reset link is invalid or has expired.");
            setDone(true);
            setMessage(data.detail);
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not reset your password. Please request a new link.");
        }
        finally {
            setBusy(false);
        }
    }
    return <UiMain className="grid min-h-screen place-items-center bg-[#F5F7F5] px-5 py-10"><UiSection className="w-full max-w-md rounded-2xl border border-line bg-white p-7 shadow-card sm:p-9">
    <Link href="/login" className="flex items-center gap-3"><UiSpan className="grid h-10 w-10 place-items-center rounded-xl bg-forest text-white"><ReceiptIndianRupee size={20}/></UiSpan><UiStrong className="text-lg"><ProductName/></UiStrong></Link>
    <UiText className="mt-8 text-[10px] font-bold uppercase tracking-[.18em] text-forest">Account recovery</UiText><UiH1 className="mt-2 text-2xl font-bold tracking-tight text-ink">Set a new password</UiH1><UiText className="mt-2 text-sm leading-6 text-slate-500">Choose a password with at least 12 characters.</UiText>
    {message && <UiAlert role={done ? "status" : "alert"} className={`mt-5 rounded-lg p-3 text-sm leading-5 ${done ? "border border-emerald-100 bg-emerald-50 text-emerald-900" : "border border-rose-100 bg-rose-50 text-rose-800"}`}>{message}</UiAlert>}
    {!uid || !token ? <UiAlert role="alert" className="mt-5 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This reset link is incomplete. Request another link to continue.</UiAlert> : !done && <UiForm onSubmit={submit} className="mt-6 space-y-4"><UiLabel className="block text-xs font-semibold text-slate-700">New password<UiSpan className="relative mt-2 block"><LockKeyhole size={16} className="absolute left-3 top-3.5 text-slate-400"/><UiInput name="new_password" type="password" autoComplete="new-password" minLength={12} required placeholder="At least 12 characters" className="h-11 w-full rounded-lg border border-line pl-10 pr-3 text-sm font-normal outline-none focus:border-forest focus:ring-2 focus:ring-forest/10"/></UiSpan></UiLabel><UiButton disabled={busy} className="h-11 w-full rounded-lg bg-forest px-4 text-sm font-semibold text-white hover:bg-[#172F21] disabled:opacity-60">{busy ? "Updating password…" : "Reset password"}</UiButton></UiForm>}
    <Link href="/login" className="mt-6 inline-flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-forest"><ArrowLeft size={14}/>{done ? "Go to sign in" : "Back to sign in"}</Link>
  </UiSection></UiMain>;
}
