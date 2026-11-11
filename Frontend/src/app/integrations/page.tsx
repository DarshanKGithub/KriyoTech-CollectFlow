"use client";
import { UiAlert, UiBox, UiButton, UiH1, UiH2, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSmall, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { requestConfirmation } from "@/components/product-dialogs";
import { useCallback, useContext, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { WorkspaceAccessContext } from "@/components/workspace-access-context";
import { canShowNavigation } from "@/lib/navigation-access";
import { AppLink as Link } from "@/components/product-ui";
type APIKey = {
    id: string;
    name: string;
    prefix: string;
    scopes: string[];
    created_at: string;
    last_used_at: string | null;
    revoked: boolean;
};
type Hook = {
    id: string;
    name: string;
    url: string;
    events: string[];
    active: boolean;
    created_at: string;
    latest_delivery: {
        status: string;
        created_at: string;
    } | null;
};
type Delivery = {
    id: string;
    event_id: string;
    event_type: string;
    status: string;
    attempts: number;
    cycle_attempts: number;
    manual_retry_count: number;
    retry_available: boolean;
    response_code: number | null;
    error: string;
    created_at: string;
    delivered_at: string | null;
    next_attempt_at: string | null;
};
type HookDetails = {
    id: string;
    deliveries: Delivery[];
};
type IntegrationData = {
    supported_events: string[];
    results: Hook[];
};
export default function IntegrationsPage() {
    const access = useContext(WorkspaceAccessContext);
    const [keys, setKeys] = useState<APIKey[]>([]);
    const [hooks, setHooks] = useState<Hook[]>([]);
    const [supportedEvents, setSupportedEvents] = useState<string[]>([]);
    const [events, setEvents] = useState<string[]>([]);
    const [keyName, setKeyName] = useState("");
    const [keyOnce, setKeyOnce] = useState("");
    const [hookName, setHookName] = useState("");
    const [hookUrl, setHookUrl] = useState("");
    const [hookSecret, setHookSecret] = useState("");
    const [notice, setNotice] = useState("");
    const [expandedHook, setExpandedHook] = useState("");
    const [deliveries, setDeliveries] = useState<Record<string, Delivery[]>>({});
    const load = useCallback(async () => {
        const [keyResponse, hookResponse] = await Promise.all([
            apiFetch("/api-keys"), apiFetch("/webhooks"),
        ]);
        if (keyResponse.ok)
            setKeys(await keyResponse.json());
        if (hookResponse.ok) {
            const data: IntegrationData = await hookResponse.json();
            setSupportedEvents(data.supported_events);
            setHooks(data.results);
        }
    }, []);
    useEffect(() => { void load(); }, [load]);
    async function createKey() {
        const response = await apiFetch("/api-keys", { method: "POST", body: JSON.stringify({ name: keyName, scopes: ["invoices:read"] }) });
        const data = await response.json();
        setNotice(response.ok ? "API key created. Copy it now; it will not be shown again." : data.error || "Could not create API key.");
        if (response.ok) {
            setKeyOnce(data.token);
            setKeyName("");
            await load();
        }
    }
    async function revokeKey(id: string) {
        const response = await apiFetch(`/api-keys/${id}`, { method: "PATCH", body: JSON.stringify({}) });
        setNotice(response.ok ? "API key revoked." : "Could not revoke the key.");
        if (response.ok)
            await load();
    }
    async function createHook() {
        const response = await apiFetch("/webhooks", { method: "POST", body: JSON.stringify({ name: hookName, url: hookUrl, events }) });
        const data = await response.json();
        setNotice(response.ok ? "Webhook created. Save the signing secret now; it is shown once." : data.error || "Could not create webhook.");
        if (response.ok) {
            setHookSecret(data.secret);
            setHookName("");
            setHookUrl("");
            setEvents([]);
            await load();
        }
    }
    async function toggleHook(hook: Hook) {
        const response = await apiFetch(`/webhooks/${hook.id}`, { method: "PATCH", body: JSON.stringify({ active: !hook.active }) });
        setNotice(response.ok ? `Webhook ${hook.active ? "paused" : "activated"}.` : "Could not update webhook.");
        if (response.ok)
            await load();
    }
    async function testHook(hook: Hook) {
        const response = await apiFetch(`/webhooks/${hook.id}/test`, { method: "POST", body: JSON.stringify({}) });
        const data = await response.json();
        setNotice(response.ok ? "Test event queued. Run the webhook delivery worker to send it." : data.error || "Could not queue test.");
        if (response.ok)
            await load();
    }
    async function toggleDeliveries(hook: Hook) {
        if (expandedHook === hook.id) {
            setExpandedHook("");
            return;
        }
        setExpandedHook(hook.id);
        const response = await apiFetch(`/webhooks/${hook.id}`);
        const data: HookDetails = await response.json();
        if (!response.ok) {
            setNotice("Could not load webhook delivery history.");
            return;
        }
        setDeliveries(old => ({ ...old, [hook.id]: data.deliveries || [] }));
    }
    async function retryDelivery(delivery: Delivery, hook: Hook) {
        if (!(await requestConfirmation(`Have you checked your receiving service? Queue event ${delivery.event_id} for another bounded delivery cycle? The event ID and payload stay the same so your receiver can deduplicate it.`)))
            return;
        const response = await apiFetch(`/webhooks/deliveries/${delivery.id}/retry`, { method: "POST", body: JSON.stringify({}) });
        const data = await response.json();
        setNotice(response.ok ? "Failed delivery queued for another bounded retry cycle." : data.error || "Could not retry this delivery.");
        if (response.ok) {
            const detailResponse = await apiFetch(`/webhooks/${hook.id}`);
            if (detailResponse.ok) {
                const detail: HookDetails = await detailResponse.json();
                setDeliveries(old => ({ ...old, [hook.id]: detail.deliveries || [] }));
            }
            await load();
        }
    }
    return <UiMain className="w-full min-w-0 space-y-6 px-5 py-8">
    <UiHeader><UiText className="text-xs font-bold uppercase tracking-[.14em] text-forest">Platform · Integrations</UiText><UiH1 className="mt-2 text-2xl font-bold">Connections, API keys & webhooks</UiH1><UiText className="mt-1 text-sm text-slate-500">Create scoped API keys and receive signed event callbacks at public HTTPS endpoints.</UiText></UiHeader>
    {notice && <UiAlert role="status" className="rounded-lg bg-mint px-4 py-3 text-sm text-forest">{notice}</UiAlert>}

    {canShowNavigation("/email-intake", access) && <UiSection className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white p-5">
      <UiBox><UiH2 className="text-sm font-bold">Gmail invoice intake</UiH2><UiText className="mt-1 text-sm text-slate-600">Connect your inbox and check recent imports.</UiText></UiBox>
      <Link href="/email-intake" className="rounded-lg border border-line px-3 py-2 text-sm font-semibold text-forest">Open Email intake</Link>
    </UiSection>}

    <Link href="/integrations/erp" className="block rounded-xl border border-line bg-white p-5"><UiH2 className="font-bold">ERP & accounting connections →</UiH2><UiText className="mt-2 text-sm text-slate-500">Connect TallyPrime or Zoho Books to import records and export approved transactions. More connectors are available under Advanced.</UiText></Link>

    <UiBox className="grid gap-5 lg:grid-cols-2">
      <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Create API key</UiH2><UiText className="mt-1 text-xs text-slate-500">Current scope is read-only invoice access. Keys are shown once and stored hashed.</UiText><UiBox className="mt-3 flex gap-2"><UiInput value={keyName} onChange={e => setKeyName(e.target.value)} placeholder="Key name" className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-sm"/><UiButton disabled={!keyName.trim()} onClick={() => void createKey()} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">Create key</UiButton></UiBox>{keyOnce && <UiBox className="mt-3 rounded-lg bg-amber-50 p-3"><UiText className="text-xs font-semibold">Copy this key now</UiText><UiBox className="mt-2 flex gap-2"><UiInput readOnly aria-label="New API key" value={keyOnce} className="min-w-0 flex-1 rounded border border-amber-200 bg-white px-2 py-2 text-xs"/><UiButton onClick={() => void navigator.clipboard.writeText(keyOnce)} className="rounded border border-amber-200 bg-white px-2 text-xs">Copy</UiButton></UiBox></UiBox>}<UiBox className="mt-4 divide-y divide-line">{keys.map(key => <UiBox key={key.id} className="flex items-center justify-between gap-3 py-3 text-xs"><UiSpan><UiStrong>{key.name}</UiStrong><UiSmall className="ml-2 text-slate-500">{key.prefix} · {key.revoked ? "Revoked" : key.scopes.join(", ")}</UiSmall></UiSpan>{!key.revoked && <UiButton onClick={() => void revokeKey(key.id)} className="rounded border px-2 py-1">Revoke</UiButton>}</UiBox>)}{!keys.length && <UiText className="py-4 text-xs text-slate-500">No API keys issued.</UiText>}</UiBox></UiSection>

      <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Add webhook endpoint</UiH2><UiText className="mt-1 text-xs text-slate-500">HTTPS on port 443 only. Private and local network targets are blocked.</UiText><UiBox className="mt-3 grid gap-2"><UiInput value={hookName} onChange={e => setHookName(e.target.value)} placeholder="Endpoint name" className="rounded-lg border border-line px-3 py-2 text-sm"/><UiInput value={hookUrl} onChange={e => setHookUrl(e.target.value)} type="url" placeholder="https://your-service.example/webhooks/kriyopay" className="rounded-lg border border-line px-3 py-2 text-sm"/><UiBox className="grid gap-1 sm:grid-cols-2">{supportedEvents.map(event => <UiLabel key={event} className="flex gap-2 text-xs text-slate-600"><UiInput type="checkbox" checked={events.includes(event)} onChange={e => setEvents(prev => e.target.checked ? [...prev, event] : prev.filter(value => value !== event))}/>{event}</UiLabel>)}</UiBox><UiButton disabled={!hookName.trim() || !hookUrl.trim() || !events.length} onClick={() => void createHook()} className="w-fit rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">Create webhook</UiButton></UiBox>{hookSecret && <UiBox className="mt-3 rounded-lg bg-amber-50 p-3"><UiText className="text-xs font-semibold">Copy webhook signing secret now</UiText><UiBox className="mt-2 flex gap-2"><UiInput readOnly aria-label="New webhook signing secret" value={hookSecret} className="min-w-0 flex-1 rounded border border-amber-200 bg-white px-2 py-2 text-xs"/><UiButton onClick={() => void navigator.clipboard.writeText(hookSecret)} className="rounded border border-amber-200 bg-white px-2 text-xs">Copy</UiButton></UiBox></UiBox>}</UiSection>
    </UiBox>

    <UiSection className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Webhook subscriptions</UiH2><UiBox className="mt-3 divide-y divide-line">{hooks.map(hook => <UiBox key={hook.id} className="py-4 text-sm"><UiBox className="flex flex-wrap items-center justify-between gap-3"><UiBox className="min-w-0"><UiStrong>{hook.name}</UiStrong><UiText className="truncate text-xs text-slate-500">{hook.url}</UiText><UiText className="mt-1 text-[10px] text-slate-400">{hook.events.join(" · ")} · Latest: {hook.latest_delivery?.status || "No deliveries"}</UiText></UiBox><UiBox className="flex flex-wrap gap-2"><UiButton onClick={() => void toggleDeliveries(hook)} className="rounded border border-line px-3 py-1.5 text-xs">{expandedHook === hook.id ? "Hide deliveries" : "Delivery history"}</UiButton><UiButton onClick={() => void testHook(hook)} disabled={!hook.active} className="rounded border border-line px-3 py-1.5 text-xs disabled:opacity-50">Queue test</UiButton><UiButton onClick={() => void toggleHook(hook)} className="rounded border border-line px-3 py-1.5 text-xs">{hook.active ? "Pause" : "Activate"}</UiButton></UiBox></UiBox>{expandedHook === hook.id && <UiBox className="mt-3 space-y-2 rounded-lg bg-slate-50 p-3">{(deliveries[hook.id] || []).map(delivery => <UiBox key={delivery.id} className="rounded-lg border border-line bg-white p-3"><UiBox className="flex flex-wrap items-center justify-between gap-2"><UiBox><UiStrong className="text-xs">{delivery.event_type}</UiStrong><UiSpan className="ml-2 text-[10px] text-slate-500">{delivery.status} · {delivery.attempts} total attempts · {delivery.manual_retry_count}/3 manual retries</UiSpan></UiBox>{delivery.retry_available && <UiButton onClick={() => void retryDelivery(delivery, hook)} className="rounded bg-forest px-3 py-1.5 text-[11px] font-semibold text-white">Retry delivery</UiButton>}</UiBox><UiText className="mt-1 break-all text-[10px] text-slate-400">Event ID: {delivery.event_id}</UiText><UiText className="mt-1 text-[10px] text-slate-500">{new Date(delivery.created_at).toLocaleString()} · {delivery.response_code ? `HTTP ${delivery.response_code}` : "No HTTP response"}{delivery.delivered_at ? ` · Delivered ${new Date(delivery.delivered_at).toLocaleString()}` : ""}</UiText>{delivery.error && <UiText className="mt-1 break-words text-[11px] text-rose-700">{delivery.error}</UiText>}{delivery.status === "RETRY" && delivery.next_attempt_at && <UiText className="mt-1 text-[10px] text-amber-700">Next attempt after {new Date(delivery.next_attempt_at).toLocaleString()}</UiText>}</UiBox>)}{!deliveries[hook.id]?.length && <UiText className="py-3 text-xs text-slate-500">No deliveries recorded yet.</UiText>}</UiBox>}</UiBox>)}{!hooks.length && <UiText className="py-5 text-xs text-slate-500">No webhook subscriptions created.</UiText>}</UiBox><UiText className="mt-4 text-xs text-slate-400">Events are queued in the database. Run <code>python manage.py deliver_webhooks</code> on a scheduled worker to deliver and retry. A failed event may be manually retried up to three times after checking your receiver; each cycle is bounded to six attempts.</UiText></UiSection>
  </UiMain>;
}
