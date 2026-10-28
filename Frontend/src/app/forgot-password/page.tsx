"use client";
import { UiAlert, UiButton, UiForm, UiH1, UiInput, UiLabel, UiMain, UiSection, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { FormEvent, useState } from "react";
import { ArrowLeft, Mail, ReceiptIndianRupee } from "lucide-react";
import { API_URL } from "@/lib/api";
export default function ForgotPasswordPage() {
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        const form = new FormData(event.currentTarget);
        try {
            const response = await fetch(`${API_URL}/auth/password-reset/request`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: form.get("email") }) });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.detail || "Could not request a password reset. Try again shortly.");
            setMessage(data.detail);
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not reach KriyoPay. Please try again.");
        }
        finally {
            setBusy(false);
        }
    }
    return <UiMain className="grid min-h-screen place-items-center bg-[#f4f7f5] px-5 py-10"><UiSection className="w-full max-w-md rounded-2xl border border-line bg-white p-7 shadow-card sm:p-9">
    <Link href="/login" className="flex items-center gap-3"><UiSpan className="grid h-10 w-10 place-items-center rounded-xl bg-forest text-white"><ReceiptIndianRupee size={20}/></UiSpan><UiStrong className="text-lg">kriyo<UiSpan className="text-forest">pay</UiSpan></UiStrong></Link>
    <UiText className="mt-8 text-[10px] font-bold uppercase tracking-[.18em] text-forest">Account recovery</UiText><UiH1 className="mt-2 text-2xl font-bold tracking-tight text-[#10251e]">Forgot your password?</UiH1><UiText className="mt-2 text-sm leading-6 text-slate-500">Enter the email for your workspace or Super Admin account. If it matches an active account, we’ll send a reset link.</UiText>
    {message && <UiAlert role="status" className="mt-5 rounded-lg border border-emerald-100 bg-emerald-50 p-3 text-sm leading-5 text-emerald-900">{message}</UiAlert>}
    <UiForm onSubmit={submit} className="mt-6 space-y-4"><UiLabel className="block text-xs font-semibold text-slate-700">Email address<UiSpan className="relative mt-2 block"><Mail size={16} className="absolute left-3 top-3.5 text-slate-400"/><UiInput name="email" type="email" autoComplete="email" required placeholder="you@company.com" className="h-11 w-full rounded-lg border border-line pl-10 pr-3 text-sm font-normal outline-none focus:border-forest focus:ring-2 focus:ring-forest/10"/></UiSpan></UiLabel><UiButton disabled={busy} className="h-11 w-full rounded-lg bg-forest px-4 text-sm font-semibold text-white hover:bg-[#125944] disabled:opacity-60">{busy ? "Sending…" : "Send reset link"}</UiButton></UiForm>
    <Link href="/login" className="mt-6 inline-flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-forest"><ArrowLeft size={14}/>Back to sign in</Link>
  </UiSection></UiMain>;
}
