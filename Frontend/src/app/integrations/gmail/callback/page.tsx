"use client";
import { UiAlert, UiBox, UiH1, UiMain, UiSection } from "@/components/product-ui";
import { useEffect, useRef, useState } from "react";
import { AppLink as Link } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
export default function GmailOAuthCallbackPage() {
    const [message, setMessage] = useState("Completing the secure Gmail connection…");
    const [finished, setFinished] = useState(false);
    const callback = useRef<{ code: string; state: string; error: boolean }>();
    const exchange = useRef<Promise<{ email: string; mobile_return_uri?: string }>>();
    useEffect(() => {
        let cancelled = false;
        async function complete() {
            if (!callback.current) {
                const url = new URL(window.location.href);
                callback.current = { code: url.searchParams.get("code") || "", state: url.searchParams.get("state") || "", error: url.searchParams.has("error") };
                window.history.replaceState({}, document.title, url.pathname);
            }
            const { code, state, error } = callback.current;
            if (error || !code || !state) {
                if (!cancelled) {
                    setMessage("Google authorization was cancelled or incomplete. You can start again from Email intake.");
                    setFinished(true);
                }
                return;
            }
            try {
                exchange.current ??= apiFetch("/google/gmail/oauth/callback", { method: "POST", body: JSON.stringify({ code, state }) }).then(async response => {
                    const data = await response.json();
                    if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "Gmail could not be connected. Try again.");
                    return data;
                });
                const data = await exchange.current;
                if (!cancelled) {
                    if (typeof data.mobile_return_uri === "string" && /^(kriyopay|exp):/.test(data.mobile_return_uri)) window.location.assign(data.mobile_return_uri);
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
    return <UiMain className="grid min-h-screen place-items-center bg-slate-50 px-5"><UiSection className="w-full max-w-md rounded-2xl border border-line bg-white p-7 text-center shadow-card"><UiBox className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-mint text-forest">G</UiBox><UiH1 className="mt-4 text-xl font-bold">Gmail connection</UiH1><UiAlert role="status" className="mt-2 text-sm text-slate-600">{message}</UiAlert>{finished && <Link href="/email-intake" className="mt-5 inline-flex rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white">Back to Email intake</Link>}</UiSection></UiMain>;
}
