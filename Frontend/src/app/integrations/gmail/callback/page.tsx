"use client";
import { UiAlert, UiBox, UiH1, UiMain, UiSection } from "@/components/product-ui";
import { useEffect, useState } from "react";
import { AppLink as Link } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
export default function GmailOAuthCallbackPage() {
    const [message, setMessage] = useState("Completing the secure Gmail connection…");
    const [finished, setFinished] = useState(false);
    useEffect(() => {
        let cancelled = false;
        async function complete() {
            const url = new URL(window.location.href);
            const code = url.searchParams.get("code") || "";
            const state = url.searchParams.get("state") || "";
            const providerError = url.searchParams.get("error");
            window.history.replaceState({}, document.title, url.pathname);
            if (providerError || !code || !state) {
                if (!cancelled) {
                    setMessage("Google authorization was cancelled or incomplete. You can start again from Integrations.");
                    setFinished(true);
                }
                return;
            }
            try {
                const response = await apiFetch("/google/gmail/oauth/callback", { method: "POST", body: JSON.stringify({ code, state }) });
                const data = await response.json();
                if (!response.ok)
                    throw new Error(data.error || "Gmail could not be connected. Try again.");
                if (!cancelled) {
                    setMessage(`Gmail connected as ${data.email}.`);
                    setFinished(true);
                }
            }
            catch (error) {
                if (!cancelled) {
                    setMessage(error instanceof Error ? error.message : "Gmail could not be connected. Try again.");
                    setFinished(true);
                }
            }
        }
        void complete();
        return () => { cancelled = true; };
    }, []);
    return <UiMain className="grid min-h-screen place-items-center bg-slate-50 px-5"><UiSection className="w-full max-w-md rounded-2xl border border-line bg-white p-7 text-center shadow-card"><UiBox className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-mint text-forest">G</UiBox><UiH1 className="mt-4 text-xl font-bold">Gmail connection</UiH1><UiAlert role="status" className="mt-2 text-sm text-slate-600">{message}</UiAlert>{finished && <Link href="/integrations" className="mt-5 inline-flex rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white">Back to integrations</Link>}</UiSection></UiMain>;
}
