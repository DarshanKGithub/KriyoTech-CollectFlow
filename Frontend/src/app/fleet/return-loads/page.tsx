"use client";

import { EmptyState } from "@/components/empty-state";
import { PageSkeleton } from "@/components/content-skeleton";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { AppLink } from "@/components/product-ui";
import { UiBox, UiButton, UiH1, UiHeader, UiMain, UiSection, UiText } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
import { ArrowRight, MapPin, Truck } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

type Suggestion = {
    id: string;
    source_trip: { id: string; trip_number: string; delivered_at: string; destination: string; vehicle: string; capacity: string | null; driver: string };
    order: { id: string; order_number: string; customer: string; origin: string; destination: string; pickup_due_at: string | null; load_quantity: string | null; load_unit: string; agreed_amount: string | null };
    match_reason: string;
    location_match_score: number;
    availability_gap_minutes: number | null;
    historical_lane: { sample_count: number; median_travel_minutes: number | null; estimated_arrival_at: string | null };
    profitability: { status: "ESTIMATED" | "INSUFFICIENT_HISTORY"; sample_count: number; historical_cost_per_km: string | null; historical_distance_km: string | null; estimated_cost: string | null; estimated_profit: string | null; estimated_margin_percent: string | null; basis: string };
    warnings: string[];
    offer: { id: string; status: "OFFERED" | "DECLINED" | "BOOKED"; proposed_amount: string; notes: string; booked_trip_id: string | null } | null;
};

export default function ReturnLoadsPage() {
    const [rows, setRows] = useState<Suggestion[]>([]);
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [actingOn, setActingOn] = useState("");

    const load = useCallback(async () => {
        setBusy(true);
        try {
            const response = await apiFetch("/fleet/return-loads");
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || payload.detail || "Could not load return-load suggestions.");
            setRows(payload.suggestions || []);
            setMessage("");
        } catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not load return-load suggestions.");
        } finally {
            setBusy(false);
            setLoading(false);
        }
    }, []);

    async function recordOffer(event: FormEvent<HTMLFormElement>, item: Suggestion) {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setActingOn(`${item.id}:offer`);
        try {
            const response = await apiFetch(`/fleet/return-loads/${item.source_trip.id}/${item.order.id}/offer`, {
                method: "POST", body: JSON.stringify({ proposed_amount: form.get("amount"), notes: form.get("notes") }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not record the customer offer.");
            await load();
            setMessage("Offer recorded. Contact the customer through your usual channel; KriyoPay has not sent a message.");
        } catch (error) { setMessage(error instanceof Error ? error.message : "Could not record the offer."); }
        finally { setActingOn(""); }
    }

    async function offerAction(item: Suggestion, action: "confirm" | "decline", formElement?: HTMLFormElement) {
        const form = formElement ? new FormData(formElement) : null;
        setActingOn(`${item.id}:${action}`);
        try {
            const body = action === "confirm"
                ? { customer_accepted: form?.get("customer_accepted") === "on", suitability_confirmed:form?.get("suitability_confirmed")==="on", accepted_amount: form?.get("accepted_amount"), notes: form?.get("notes") }
                : { notes: form?.get("notes") };
            const response = await apiFetch(`/fleet/return-loads/${item.source_trip.id}/${item.order.id}/${action}`, {
                method: "POST", body: JSON.stringify(body),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not update this return-load offer.");
            await load();
            setMessage(action === "confirm" ? `Customer acceptance recorded. ${result.trip_number} is assigned and ready for dispatch.` : "Offer marked as declined.");
        } catch (error) { setMessage(error instanceof Error ? error.message : "Could not update the offer."); }
        finally { setActingOn(""); }
    }

    useEffect(() => { void load(); }, [load]);
    if (loading) return <PageSkeleton variant="table" label="Finding possible return loads" />;

    return <UiMain className="w-full min-w-0 space-y-5 px-5 py-8">
        <UiHeader className="flex flex-wrap items-end justify-between gap-3">
            <UiBox>
                <UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet · Dispatch</UiText>
                <UiH1 className="mt-1 text-2xl font-bold">Find a return load</UiH1>
                <UiText className="mt-1 max-w-3xl text-sm text-slate-500">Find open loads near a delivered truck’s last stop. Suggestions rank location similarity, pickup gap, capacity and historical lane times; review before dispatch.</UiText>
            </UiBox>
            <UiButton type="button" onClick={() => void load()} disabled={busy} className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">{busy ? "Refreshing…" : "Refresh"}</UiButton>
        </UiHeader>

        {message && <WorkflowFeedback message={message} onRefresh={() => void load()} />}
        <UiSection className="rounded-xl border border-line bg-white p-4">
            <UiText className="text-sm font-semibold">{rows.length} possible match{rows.length === 1 ? "" : "es"}</UiText>
            <UiText className="mt-1 text-xs text-slate-500">These are suggestions only. Check the load, route, driver hours, truck capacity, pickup time, and customer requirements before assigning a truck.</UiText>
        </UiSection>

        {rows.length === 0 ? <EmptyState title="No return load found" description="A suggestion appears when an open order begins near a truck’s last delivery stop. Add an open transport order or try again after a delivery." actionLabel="Open transport orders" onAction={() => window.location.assign("/fleet/orders")} /> : <UiBox className="grid gap-4">
            {rows.map(item => <UiSection key={item.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-0 shadow-sm">
                <UiBox className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5"><UiBox className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-lg bg-emerald-50 text-emerald-700"><Truck size={16}/></span><UiText className="text-sm font-semibold text-slate-900">Possible return load</UiText><UiText className="text-xs text-slate-500">Order {item.order.order_number}</UiText></UiBox><UiText className={`rounded-full px-3 py-1 text-xs font-semibold ${item.offer?.status === "BOOKED" ? "bg-emerald-100 text-emerald-800" : item.offer?.status === "OFFERED" ? "bg-amber-100 text-amber-900" : item.offer?.status === "DECLINED" ? "bg-slate-100 text-slate-700" : "bg-blue-50 text-blue-700"}`}>{item.offer?.status === "BOOKED" ? "Booked" : item.offer?.status === "OFFERED" ? "Waiting for customer" : item.offer?.status === "DECLINED" ? "Offer declined" : "Suggested"}</UiText></UiBox>
                <UiBox className="grid gap-4 p-4 sm:p-5 xl:grid-cols-[minmax(0,1fr)_300px]">
                    <UiBox className="min-w-0">
                        <UiBox className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.25fr)] md:items-stretch">
                            <UiBox className="rounded-xl border border-slate-200 p-4"><UiText className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Truck is here</UiText><UiText className="mt-2 text-base font-bold text-slate-900">{item.source_trip.destination}</UiText><UiText className="mt-1 text-xs text-slate-600">{item.source_trip.vehicle} · {item.source_trip.driver}</UiText><UiText className="mt-2 text-[11px] text-slate-500">After trip {item.source_trip.trip_number} · {new Date(item.source_trip.delivered_at).toLocaleString()}</UiText></UiBox>
                            <UiBox className="hidden items-center justify-center text-emerald-700 md:flex"><ArrowRight size={20}/></UiBox>
                            <UiBox className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-4"><UiText className="text-[10px] font-bold uppercase tracking-wide text-emerald-800">Open load</UiText><UiText className="mt-2 text-base font-bold text-slate-900">{item.order.customer}</UiText><UiText className="mt-1 text-sm font-medium text-slate-700">Pick up: {item.order.origin}</UiText><UiText className="mt-1 text-sm font-medium text-slate-700">Deliver to: {item.order.destination}</UiText><UiText className="mt-2 text-[11px] text-slate-500">{item.order.load_quantity ? `${item.order.load_quantity} ${item.order.load_unit}` : "Load size not provided"}{item.order.pickup_due_at ? ` · Pickup ${new Date(item.order.pickup_due_at).toLocaleString()}` : " · Pickup time not set"}</UiText></UiBox>
                        </UiBox>
                        <UiBox className="mt-3 flex flex-wrap gap-2"><UiText className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-800">{Math.round(item.location_match_score * 100)}% location match</UiText>{item.availability_gap_minutes !== null && <UiText className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700">Pickup in about {(item.availability_gap_minutes / 60).toFixed(1)} hours</UiText>}{item.historical_lane.median_travel_minutes !== null && <UiText className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700">Past travel time about {Math.round(item.historical_lane.median_travel_minutes / 60)} hours</UiText>}</UiBox>
                        {item.warnings.length > 0 && <UiBox className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3"><UiText className="mb-1 text-xs font-semibold text-amber-900">Check before assigning</UiText>{item.warnings.map(warning => <UiText key={warning} className="mt-1 text-xs leading-5 text-amber-900">{warning}</UiText>)}</UiBox>}
                    </UiBox>
                    <UiBox className="self-start rounded-xl border border-slate-200 bg-slate-50 p-4"><UiText className="text-xs font-semibold text-slate-700">Estimated money for this load</UiText>{item.profitability.status === "ESTIMATED" ? <><UiBox className="mt-3 grid grid-cols-2 gap-3"><UiBox><UiText className="text-[10px] text-slate-500">Estimated cost</UiText><UiText className="mt-1 text-sm font-semibold text-slate-900">₹{Number(item.profitability.estimated_cost).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</UiText></UiBox><UiBox><UiText className="text-[10px] text-slate-500">Estimated profit</UiText><UiText className={`mt-1 text-sm font-bold ${Number(item.profitability.estimated_profit) < 0 ? "text-rose-700" : "text-emerald-800"}`}>₹{Number(item.profitability.estimated_profit).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</UiText></UiBox></UiBox><UiText className="mt-3 border-t border-slate-200 pt-3 text-[11px] text-slate-600">About {item.profitability.estimated_margin_percent}% profit · Based on {item.profitability.sample_count} similar past trips.</UiText></> : <UiText className="mt-2 text-xs leading-5 text-slate-600">No estimate yet. There is not enough past trip information for this route.</UiText>}<UiText className="mt-2 text-[10px] leading-4 text-slate-500">Estimate only. {item.profitability.basis}.</UiText></UiBox>
                </UiBox>
                {item.offer?.status === "BOOKED" ? <UiBox className="flex flex-wrap items-center justify-between gap-3 border-t border-emerald-100 bg-emerald-50/50 px-4 py-3 sm:px-5"><UiText className="text-xs font-medium text-emerald-900">Customer accepted. The truck and driver are assigned to a new trip.</UiText><AppLink href="/fleet/dispatch" className="inline-flex items-center gap-2 rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white"><Truck size={14}/>Open dispatch</AppLink></UiBox> : <UiBox className="grid gap-3 border-t border-slate-100 bg-slate-50/50 p-4 sm:p-5 lg:grid-cols-2">
                    <details className="rounded-xl border border-slate-200 bg-white"><summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-800">{item.offer?.status === "OFFERED" ? "Change customer offer" : "Make an offer"}<UiText className="mt-1 text-xs font-normal text-slate-500">KriyoPay records this; it does not contact the customer.</UiText></summary><UiBox className="border-t border-slate-100 p-4"><form onSubmit={event => void recordOffer(event, item)} className="grid gap-2"><label className="text-xs font-medium text-slate-600">Offer amount<input name="amount" required type="number" min="0.01" step="0.01" defaultValue={item.offer?.proposed_amount || item.order.agreed_amount || ""} aria-label="Proposed freight amount" placeholder="Amount in rupees" className="mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"/></label><input name="notes" maxLength={500} defaultValue={item.offer?.notes || ""} aria-label="Offer notes" placeholder="Optional note" className="rounded-lg border border-line bg-white px-3 py-2 text-sm"/><button disabled={Boolean(actingOn)} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">{actingOn === `${item.id}:offer` ? "Saving…" : "Save offer"}</button></form></UiBox></details>
                    {item.offer?.status === "OFFERED" && <UiBox className="rounded-xl border border-emerald-200 bg-white p-4"><UiText className="text-sm font-semibold text-slate-900">Customer has replied?</UiText><UiText className="mt-1 text-xs text-slate-500">Confirm only after the customer agrees and you have checked the truck and driver.</UiText><form onSubmit={event => { event.preventDefault(); void offerAction(item, "confirm", event.currentTarget); }} className="mt-3 grid gap-2"><label className="text-xs font-medium text-slate-600">Accepted amount<input name="accepted_amount" required type="number" min="0.01" step="0.01" defaultValue={item.offer.proposed_amount} className="mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"/></label><input name="notes" maxLength={500} placeholder="Optional note" aria-label="Acceptance notes" className="rounded-lg border border-line bg-white px-3 py-2 text-sm"/><label className="flex items-start gap-2 text-xs leading-5 text-slate-600"><input name="customer_accepted" type="checkbox" required className="mt-0.5"/>Customer agreed to this amount.</label><label className="flex items-start gap-2 text-xs leading-5 text-slate-600"><input name="suitability_confirmed" type="checkbox" required className="mt-0.5"/>I checked the truck, load size, route rules, and driver hours.</label><UiBox className="flex flex-wrap gap-2"><button disabled={Boolean(actingOn)} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">{actingOn === `${item.id}:confirm` ? "Booking…" : "Confirm and assign"}</button><button type="button" disabled={Boolean(actingOn)} onClick={() => void offerAction(item, "decline")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">{actingOn === `${item.id}:decline` ? "Saving…" : "Mark declined"}</button></UiBox></form></UiBox>}
                </UiBox>}
            </UiSection>)}
        </UiBox>}
    </UiMain>;
}
