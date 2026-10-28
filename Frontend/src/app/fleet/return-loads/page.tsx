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
                <UiH1 className="mt-1 text-2xl font-bold">Return-load suggestions</UiH1>
                <UiText className="mt-1 max-w-3xl text-sm text-slate-500">Find open loads near a delivered truck’s last stop. Suggestions rank location similarity, pickup gap, capacity and historical lane times; review before dispatch.</UiText>
            </UiBox>
            <UiButton type="button" onClick={() => void load()} disabled={busy} className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">{busy ? "Refreshing…" : "Refresh"}</UiButton>
        </UiHeader>

        {message && <WorkflowFeedback message={message} onRefresh={() => void load()} />}
        <UiSection className="rounded-xl border border-line bg-white p-4">
            <UiText className="text-sm font-semibold">{rows.length} possible backhaul{rows.length === 1 ? "" : "s"}</UiText>
            <UiText className="mt-1 text-xs text-slate-500">No truck is assigned automatically. Check road distance, driver hours, load units, pickup time and customer requirements. Historical lane times are estimates, not live navigation ETAs.</UiText>
        </UiSection>

        {rows.length === 0 ? <EmptyState title="No return-load matches found" description="KriyoPay will show suggestions when a truck completes a trip and an open order starts at the delivery location. Add open transport orders or check the recorded location names." actionLabel="Open transport orders" onAction={() => window.location.assign("/fleet/orders")} /> : <UiBox className="grid gap-3">
            {rows.map((item) => <UiSection key={item.id} className="rounded-xl border border-line bg-white p-4">
                <UiBox className="grid gap-4 lg:grid-cols-[1fr_auto_1fr] lg:items-center">
                    <UiBox>
                        <UiText className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Truck delivered</UiText>
                        <UiText className="mt-1 font-semibold">{item.source_trip.trip_number} · {item.source_trip.vehicle}</UiText>
                        <UiText className="mt-1 text-sm text-slate-600">{item.source_trip.destination}</UiText>
                        <UiText className="mt-1 text-xs text-slate-500">Driver: {item.source_trip.driver} · Delivered {new Date(item.source_trip.delivered_at).toLocaleString()}</UiText>
                    </UiBox>
                    <UiBox className="hidden justify-center text-forest lg:flex"><ArrowRight size={20}/></UiBox>
                    <UiBox>
                        <UiText className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Open load · {item.order.order_number}</UiText>
                        <UiText className="mt-1 font-semibold">{item.order.customer}</UiText>
                        <UiText className="mt-1 text-sm text-slate-600">{item.order.origin} <span aria-hidden="true">→</span> {item.order.destination}</UiText>
                        <UiText className="mt-1 text-xs text-slate-500">{item.order.load_quantity ? `Load: ${item.order.load_quantity} ${item.order.load_unit}` : "Load quantity not specified"}{item.order.agreed_amount ? ` · Agreed ₹${item.order.agreed_amount}` : " · Rate not set"}{item.order.pickup_due_at ? ` · Pickup ${new Date(item.order.pickup_due_at).toLocaleString()}` : ""}</UiText>
                        <UiBox className="mt-2 rounded-lg bg-slate-50 p-3"><UiText className="text-xs font-semibold">Estimated trip profitability</UiText>{item.profitability.status === "ESTIMATED" ? <UiText className="mt-1 text-xs text-slate-600">Approx. cost ₹{Number(item.profitability.estimated_cost).toLocaleString("en-IN",{minimumFractionDigits:2})} · profit ₹{Number(item.profitability.estimated_profit).toLocaleString("en-IN",{minimumFractionDigits:2})} · margin {item.profitability.estimated_margin_percent}% · based on {item.profitability.sample_count} historical same-lane trips</UiText> : <UiText className="mt-1 text-xs text-slate-500">No estimate yet · {item.profitability.basis}</UiText>}<UiText className="mt-1 text-[11px] text-slate-500">{item.profitability.basis}</UiText></UiBox>
                    </UiBox>
                </UiBox>
                <UiBox className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
                    <UiBox className="flex items-start gap-2 text-xs text-slate-600"><MapPin size={15} className="mt-0.5 shrink-0 text-forest"/><UiText>{item.match_reason} Location match {Math.round(item.location_match_score*100)}%.{item.source_trip.capacity ? ` Truck capacity: ${item.source_trip.capacity}.` : ""}{item.availability_gap_minutes!==null?` Pickup gap: ${(item.availability_gap_minutes/60).toFixed(1)} hours.`:""}{item.historical_lane.median_travel_minutes!==null?` Historic lane median ${item.historical_lane.median_travel_minutes} min from ${item.historical_lane.sample_count} trips${item.historical_lane.estimated_arrival_at?`; estimated arrival ${new Date(item.historical_lane.estimated_arrival_at).toLocaleString()}`:""}.`:""}</UiText></UiBox>
                    <UiText className={`rounded-full px-3 py-1 text-xs font-semibold ${item.offer?.status === "BOOKED" ? "bg-emerald-100 text-emerald-800" : item.offer?.status === "OFFERED" ? "bg-amber-100 text-amber-900" : item.offer?.status === "DECLINED" ? "bg-slate-100 text-slate-700" : "bg-slate-100 text-slate-600"}`}>{item.offer?.status === "BOOKED" ? `Booked${item.offer.booked_trip_id ? " · trip assigned" : ""}` : item.offer?.status === "OFFERED" ? "Offer awaiting response" : item.offer?.status === "DECLINED" ? "Offer declined" : "Suggestion only"}</UiText>
                </UiBox>
                {item.warnings.length > 0 && <UiBox className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">{item.warnings.map((warning) => <UiText key={warning}>{warning}</UiText>)}</UiBox>}
                {item.offer?.status === "BOOKED" ? <UiBox className="mt-3"><AppLink href="/fleet/dispatch" className="inline-flex items-center gap-2 rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white"><Truck size={14}/>Open dispatch</AppLink></UiBox> : <UiBox className="mt-4 grid gap-3 border-t border-line pt-4 lg:grid-cols-2">
                    <UiBox><UiText className="text-sm font-semibold">{item.offer?.status === "OFFERED" ? "Update offer" : "Record customer offer"}</UiText><UiText className="mt-1 text-xs text-slate-500">This records an offer for tracking. It does not contact the customer.</UiText><form onSubmit={event => void recordOffer(event, item)} className="mt-3 grid gap-2 sm:grid-cols-[1fr_1.5fr_auto]"><input name="amount" required type="number" min="0.01" step="0.01" defaultValue={item.offer?.proposed_amount || item.order.agreed_amount || ""} aria-label="Proposed freight amount" placeholder="Proposed freight ₹" className="rounded-lg border border-line bg-white px-3 py-2 text-sm"/><input name="notes" maxLength={500} defaultValue={item.offer?.notes || ""} aria-label="Offer notes" placeholder="Offer details or negotiation notes" className="rounded-lg border border-line bg-white px-3 py-2 text-sm"/><button disabled={Boolean(actingOn)} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">{actingOn === `${item.id}:offer` ? "Saving…" : "Record offer"}</button></form></UiBox>
                    {item.offer?.status === "OFFERED" && <UiBox><UiText className="text-sm font-semibold">Customer response</UiText><form onSubmit={event => { event.preventDefault(); void offerAction(item, "confirm", event.currentTarget); }} className="mt-3 grid gap-2"><label className="text-xs font-medium">Accepted freight amount<input name="accepted_amount" required type="number" min="0.01" step="0.01" defaultValue={item.offer.proposed_amount} className="mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"/></label><input name="notes" maxLength={500} placeholder="Acceptance reference or notes" aria-label="Acceptance notes" className="rounded-lg border border-line bg-white px-3 py-2 text-sm"/><label className="flex items-start gap-2 text-xs text-slate-600"><input name="customer_accepted" type="checkbox" required className="mt-0.5"/>I confirm the customer accepted this freight amount and authorize assigning the shown truck and driver.</label><label className="flex items-start gap-2 text-xs text-slate-600"><input name="suitability_confirmed" type="checkbox" required className="mt-0.5"/>I verified vehicle type, capacity units, legal route restrictions and available driver working hours.</label><UiBox className="flex flex-wrap gap-2"><button disabled={Boolean(actingOn)} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">{actingOn === `${item.id}:confirm` ? "Booking…" : "Confirm acceptance & assign"}</button><button type="button" disabled={Boolean(actingOn)} onClick={() => void offerAction(item, "decline")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">{actingOn === `${item.id}:decline` ? "Saving…" : "Mark declined"}</button></UiBox></form></UiBox>}
                </UiBox>}
            </UiSection>)}
        </UiBox>}
    </UiMain>;
}
