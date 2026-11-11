"use client";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AppLink as Link } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
import { ArrowRight, ChevronDown, Search, Truck } from "lucide-react";
type Customer = {
    id: string;
    name: string;
};
type Order = {
    id: string;
    order_number: string;
    customer: Customer;
    origin: string;
    destination: string;
    pickup_due_at: string | null;
    delivery_due_at: string | null;
    cargo_description: string;
    load_quantity: string | null;
    load_unit: string;
    agreed_amount: string | null;
    status: string;
    trip_id: string | null;
};
type Vehicle = {
    id: string;
    registration_number: string;
    status: string;
};
type Driver = {
    id: string;
    name: string;
    status: string;
};
type Trip = {
    id: string;
    trip_number: string;
    transport_order: {
        id: string;
        order_number: string;
        customer_name: string;
    } | null;
    vehicle: {
        registration_number: string;
    };
    driver: {
        name: string;
    };
    status: string;
    pickup_at: string | null;
    loaded_at: string | null;
    delivery_at: string | null;
    delivery_proof_name: string | null;
    delivery_signature_name: string;
    created_at: string;
};
type FollowUp = {
    id: string;
    trip_id: string | null;
    category: string;
    description: string;
    due_at: string | null;
    status: string;
};
type DispatchVehicleSuggestion = {
    vehicle_id: string;
    registration_number: string;
    vehicle_type: string;
    capacity: string | null;
    capacity_unit: string;
    score: number;
    score_basis: string;
    reasons: string[];
    warnings: string[];
};
type DispatchSuggestions = {
    vehicles: DispatchVehicleSuggestion[];
    drivers: { id: string; name: string }[];
    excluded: Record<string, number>;
    limitations: string[];
};
const input = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const lanes = [
    { id: "OPEN", title: "Needs dispatch", hint: "Order has no truck or driver" },
    { id: "ASSIGNED", title: "Assigned", hint: "Trip created; awaiting pickup check-in" },
    { id: "PARTIALLY_ASSIGNED", title: "Partly assigned", hint: "Some cargo still needs a truck" },
    { id: "LOADING", title: "At pickup", hint: "Driver checked in; confirm the load" },
    { id: "IN_TRANSIT", title: "In transit", hint: "Load confirmed; delivery is pending" },
    { id: "PARTIALLY_DELIVERED", title: "Partly delivered", hint: "Some cargo is still due for delivery" },
    { id: "DELIVERED", title: "Delivered", hint: "Check proof of delivery" },
    { id: "CANCELLED", title: "Cancelled", hint: "Cancelled orders" },
];
const activeFollowUp = (item: FollowUp) => ["OPEN", "IN_PROGRESS"].includes(item.status);
const labelTime = (value: string | null) => value ? new Date(value).toLocaleString() : null;
export default function FleetDispatchPage() {
    const [statusFilter, setStatusFilter] = useState("");
    const [search, setSearch] = useState("");
    const [orders, setOrders] = useState<Order[]>([]);
    const [trips, setTrips] = useState<Trip[]>([]);
    const [vehicles, setVehicles] = useState<Vehicle[]>([]);
    const [drivers, setDrivers] = useState<Driver[]>([]);
    const [followUps, setFollowUps] = useState<FollowUp[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState("");
    const [exceptionTrip, setExceptionTrip] = useState("");
    const [dispatchSuggestions, setDispatchSuggestions] = useState<Record<string, DispatchSuggestions>>({});
    const [selectedResources, setSelectedResources] = useState<Record<string, { vehicleId: string; driverId: string }>>({});
    const tripsByOrder = useMemo(() => new Map(trips.filter(trip => trip.transport_order).map(trip => [trip.transport_order!.id, trip])), [trips]);
    const tripsById = useMemo(() => new Map(trips.map(trip => [trip.id, trip])), [trips]);
    const refresh = useCallback(async () => {
        const [ordersResponse, tripsResponse, vehiclesResponse, driversResponse, followUpsResponse] = await Promise.all([
            apiFetch("/fleet/orders"), apiFetch("/fleet/trips"), apiFetch("/fleet/vehicles"), apiFetch("/fleet/drivers"), apiFetch("/fleet/follow-ups"),
        ]);
        if (![ordersResponse, tripsResponse, vehiclesResponse, driversResponse, followUpsResponse].every(response => response.ok))
            throw new Error("Could not load dispatch data. Check your workspace access.");
        setOrders(await ordersResponse.json());
        setTrips(await tripsResponse.json());
        setVehicles(await vehiclesResponse.json());
        setDrivers(await driversResponse.json());
        setFollowUps(await followUpsResponse.json());
    }, []);
    useEffect(() => { void refresh().catch(error => setMessage(error.message)); }, [refresh]);
    async function suggestResources(order: Order) {
        setBusy(`suggest:${order.id}`);
        setMessage("");
        try {
            const response = await apiFetch(`/fleet/dispatch-recommendations?order_id=${encodeURIComponent(order.id)}`);
            const result = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(typeof result?.error === "string" ? result.error : "Could not create dispatch suggestions.");
            setDispatchSuggestions(previous => ({ ...previous, [order.id]: result as DispatchSuggestions }));
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not create dispatch suggestions.");
        }
        finally {
            setBusy("");
        }
    }
    async function assignOrder(event: FormEvent<HTMLFormElement>, order: Order) {
        event.preventDefault();
        setMessage("");
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form).entries());
        data.transport_order_id = order.id;
        setBusy(order.id);
        try {
            const response = await apiFetch("/fleet/trips", { method: "POST", body: JSON.stringify(data) });
            const result = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(typeof result?.error === "string" ? result.error : JSON.stringify(result) || "Could not assign this order.");
            setMessage(`${order.order_number} assigned to the selected truck and driver.`);
            await refresh();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not assign this order.");
        }
        finally {
            setBusy("");
        }
    }
    async function reportException(event: FormEvent<HTMLFormElement>, trip: Trip) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form).entries());
        data.trip_id = trip.id;
        data.category = `DISPATCH_${String(data.category)}`;
        setBusy(`exception:${trip.id}`);
        try {
            const response = await apiFetch("/fleet/follow-ups", { method: "POST", body: JSON.stringify(data) });
            const result = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(typeof result?.error === "string" ? result.error : "Could not record the trip issue.");
            setMessage("Trip issue added to follow-ups.");
            setExceptionTrip("");
            await refresh();
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not record the trip issue.");
        }
        finally {
            setBusy("");
        }
    }
    function milestone(order: Order, trip: Trip | undefined) {
        if (!trip)
            return order.status === "CANCELLED" ? "Order cancelled" : "Order received · awaiting dispatch";
        if (trip.delivery_at)
            return trip.delivery_proof_name || trip.delivery_signature_name ? `Delivered · POD received ${labelTime(trip.delivery_at)}` : `Delivered · POD needed ${labelTime(trip.delivery_at)}`;
        if (trip.loaded_at)
            return `Load confirmed ${labelTime(trip.loaded_at)} · in transit`;
        if (trip.pickup_at)
            return `Pickup check-in ${labelTime(trip.pickup_at)} · awaiting load confirmation`;
        return `Trip ${trip.trip_number} assigned · ${labelTime(trip.created_at)}`;
    }
    const needsProof = (order: Order) => {
        const trip = tripsByOrder.get(order.id);
        return order.status === "DELIVERED" && Boolean(trip?.delivery_at && !trip.delivery_proof_name && !trip.delivery_signature_name);
    };
    const moving = (order: Order) => ["ASSIGNED", "PARTIALLY_ASSIGNED", "LOADING", "IN_TRANSIT", "PARTIALLY_DELIVERED"].includes(order.status);
    const awaitingDispatch = (order: Order) => order.status === "OPEN" && !order.trip_id && !tripsByOrder.has(order.id);
    const queues = [
        { value: "", title: "All orders", count: orders.length },
        { value: "TO_ASSIGN", title: "Needs assignment", count: orders.filter(awaitingDispatch).length },
        { value: "MOVING", title: "In progress", count: orders.filter(moving).length },
        { value: "NEEDS_PROOF", title: "Missing delivery proof", count: orders.filter(needsProof).length },
        { value: "DELIVERED", title: "Delivered", count: orders.filter(order => order.status === "DELIVERED").length },
    ];
    const visibleOrders = orders.filter(order => {
        const matchesStatus = !statusFilter || (statusFilter === "TO_ASSIGN" ? awaitingDispatch(order) :
            statusFilter === "MOVING" ? moving(order) : statusFilter === "NEEDS_PROOF" ? needsProof(order) : order.status === statusFilter);
        const query = search.trim().toLowerCase();
        const trip = tripsByOrder.get(order.id) || tripsById.get(order.trip_id || "");
        const matchesSearch = !query || [order.order_number, order.customer.name, order.origin, order.destination, order.cargo_description,
            trip?.trip_number, trip?.vehicle.registration_number, trip?.driver.name].some(value => value?.toLowerCase().includes(query));
        return matchesStatus && matchesSearch;
    });
    const pagination = useListPagination(visibleOrders, `${statusFilter}:${search}`);
    return <UiMain className="w-full min-w-0 space-y-5 px-4 py-8 sm:px-6 lg:px-8">
    <UiHeader className="flex flex-wrap items-end justify-between gap-4"><UiBox><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet operations</UiText><UiH1 className="mt-1 text-2xl font-bold tracking-tight">Dispatch</UiH1><UiText className="mt-1 max-w-2xl text-sm text-slate-500">Move each order from assignment to delivery, with the next action easy to find.</UiText></UiBox><UiBox className="flex flex-wrap gap-2"><Link href="/fleet/dispatch-planner" className="inline-flex items-center gap-2 rounded-lg bg-forest px-3.5 py-2.5 text-sm font-semibold text-white"><Truck size={15}/>Plan multi-stop trip</Link><Link href="/fleet/orders" className="rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm font-semibold">Transport orders</Link></UiBox></UiHeader>
    <LiveData onRefresh={refresh} paused={Boolean(busy || exceptionTrip)} interval={20000}/>
    {message && <UiAlert role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{message}</UiAlert>}
    <UiSection aria-label="Dispatch queues" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {queues.map(queue => <button key={queue.value} type="button" aria-pressed={statusFilter === queue.value}
        onClick={() => setStatusFilter(queue.value)}
        className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-4 text-left text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest ${statusFilter === queue.value ? "border-forest bg-emerald-50 text-forest" : "border-line bg-white text-slate-700 hover:bg-slate-50"}`}>
        {queue.title}<span className="text-lg font-bold tabular-nums">{queue.count}</span>
      </button>)}
    </UiSection>
    <UiSection className="overflow-hidden rounded-xl border border-line bg-white">
      <UiHeader id="dispatch-orders" className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-white p-4 sm:p-5"><UiBox><UiH2 className="text-sm font-bold">Orders <UiSpan className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{visibleOrders.length}</UiSpan></UiH2><UiText className="mt-1 text-xs text-slate-500">Select an order to assign resources or review trip progress.</UiText></UiBox><UiBox className="flex w-full flex-wrap gap-2 sm:w-auto"><UiLabel className="relative min-w-48 flex-1 sm:flex-none"><span className="sr-only">Search orders</span><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><UiInput className={`${input} pl-9`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Order, customer, trip, or truck" aria-label="Search dispatch orders"/></UiLabel><UiLabel className="flex items-center gap-2 text-xs font-semibold">Status<UiSelect className={input} value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">All statuses</option><option value="TO_ASSIGN">Needs assignment</option><option value="MOVING">In progress</option><option value="NEEDS_PROOF">Missing delivery proof</option>{lanes.map(lane => <option key={lane.id} value={lane.id}>{lane.title}</option>)}</UiSelect></UiLabel></UiBox></UiHeader>
      <UiBox className="divide-y divide-line">{pagination.rows.map(order => {
            const trip = tripsByOrder.get(order.id);
            const assignedTrip = trip || tripsById.get(order.trip_id || "");
            const proofMissing = needsProof(order);
            const awaitingAssignment = awaitingDispatch(order);
            const lane = lanes.find(item => item.id === order.status);
            const exceptions = followUps.filter(item => item.trip_id === assignedTrip?.id && activeFollowUp(item));
            return <UiArticle key={order.id} className="bg-white"><details className="group"><summary className="grid cursor-pointer list-none items-center gap-3 px-4 py-4 transition hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-forest sm:px-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_auto] [&::-webkit-details-marker]:hidden">
              <div className="min-w-0 break-words">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <UiH3 className="text-sm font-bold">{order.order_number}</UiH3>
                  <UiSpan className="text-xs text-slate-600">{order.customer.name}</UiSpan>
                </div>
                <UiText className="mt-1 text-sm font-medium text-slate-800">{order.origin || "Pickup not set"} <span aria-hidden="true" className="px-1 text-slate-400">→</span><span className="sr-only"> to </span> {order.destination || "Delivery location not set"}</UiText>
              </div>
              <div className="min-w-0 break-words text-sm">
                <span className="font-semibold text-slate-800">{assignedTrip ? `Trip ${assignedTrip.trip_number}` : order.trip_id ? "Trip assigned" : "No trip assigned"}</span>
                {assignedTrip && <span className="mt-1 block text-xs text-slate-600">{assignedTrip.vehicle.registration_number} · {assignedTrip.driver.name}</span>}
              </div>
              <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                <UiSpan className={`rounded-full px-2.5 py-1 text-xs font-semibold ${proofMissing || awaitingAssignment ? "bg-amber-50 text-amber-900" : order.status === "DELIVERED" ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-700"}`}>{proofMissing ? "Delivery proof missing" : lane?.title || order.status.replaceAll("_", " ")}</UiSpan>
                {exceptions.length > 0 && <UiSpan className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900">{exceptions.length} {exceptions.length === 1 ? "follow-up" : "follow-ups"}</UiSpan>}
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-forest">{awaitingAssignment ? "Assign truck and driver" : "View details"}<ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden="true"/></span>
              </div>
            </summary><UiBox className="border-t border-line bg-slate-50/50 px-4 py-4 sm:px-5 sm:py-5"><UiText className="text-[11px] text-slate-500">{[order.cargo_description, order.load_quantity && `${order.load_quantity} ${order.load_unit}`.trim()].filter(Boolean).join(" · ") || "Cargo details not set"}</UiText>{(order.pickup_due_at || order.delivery_due_at) && <UiText className="mt-2 text-[11px] text-slate-500">{order.pickup_due_at && <>Pickup by {labelTime(order.pickup_due_at)}</>}{order.pickup_due_at && order.delivery_due_at && " · "}{order.delivery_due_at && <>Deliver by {labelTime(order.delivery_due_at)}</>}</UiText>}
            {!trip && assignedTrip && <Link href="/fleet/trips" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-forest">Open Trip Register <ArrowRight size={14}/></Link>}
            {trip && <><UiBox className="mt-3 rounded-md bg-slate-50 p-2 text-xs"><UiText className="font-semibold">{trip.vehicle.registration_number} · {trip.driver.name}</UiText><UiText className="mt-1 text-slate-600">{milestone(order, trip)}</UiText></UiBox>{exceptions.length > 0 && <UiBox className="mt-2 space-y-1 rounded-md bg-amber-50 p-2 text-[11px] text-amber-900">{exceptions.map(item => <UiText key={item.id}><UiStrong>Needs attention:</UiStrong> {item.description}</UiText>)}</UiBox>}{trip.delivery_at && !trip.delivery_proof_name && !trip.delivery_signature_name && <UiText className="mt-2 text-[11px] font-semibold text-rose-700">Proof of delivery is missing.</UiText>}{!trip.delivery_at && <UiButton type="button" onClick={() => setExceptionTrip(exceptionTrip === trip.id ? "" : trip.id)} className="mt-3 text-xs font-semibold text-forest">{exceptionTrip === trip.id ? "Close issue form" : "Report a trip issue"}</UiButton>}{exceptionTrip === trip.id && <UiForm onSubmit={event => void reportException(event, trip)} className="mt-2 space-y-2"><UiSelect className={input} name="category"><option value="DELAY">Delay</option><option value="CUSTOMER_UNAVAILABLE">Customer unavailable</option><option value="VEHICLE_ISSUE">Vehicle issue</option><option value="CARGO_ISSUE">Cargo issue</option><option value="ROUTE_ISSUE">Route issue</option><option value="OTHER">Other</option></UiSelect><UiInput className={input} name="description" required maxLength={240} placeholder="Briefly describe the issue"/><UiButton disabled={busy === `exception:${trip.id}`} className="rounded-md bg-forest px-3 py-2 text-xs font-semibold text-white">{busy === `exception:${trip.id}` ? "Saving…" : "Add to follow-ups"}</UiButton></UiForm>}</>}
            {awaitingAssignment && <UiBox className="mt-3 rounded-lg border border-line bg-slate-50 p-3">
              <UiBox className="flex flex-wrap items-center justify-between gap-2"><UiBox><UiText className="text-xs font-semibold">Resource suggestions</UiText><UiText className="text-[10px] text-slate-500">Rule-based shortlist. Review and confirm before dispatch.</UiText></UiBox><UiButton type="button" disabled={busy === `suggest:${order.id}`} onClick={() => void suggestResources(order)} className="rounded-md border border-line bg-white px-3 py-2 text-xs font-semibold text-forest">{busy === `suggest:${order.id}` ? "Checking availability…" : dispatchSuggestions[order.id] ? "Refresh suggestions" : "Suggest truck and driver"}</UiButton></UiBox>
              {dispatchSuggestions[order.id] && <><UiBox className="mt-3 space-y-2">{dispatchSuggestions[order.id].vehicles.slice(0, 5).map((candidate, index) => <UiBox key={candidate.vehicle_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-white p-2"><UiBox><UiText className="text-xs font-semibold">{index === 0 ? "Best fit · " : ""}{candidate.registration_number} <UiSpan className="ml-1 text-[10px] font-normal text-slate-500">{candidate.score}/100</UiSpan></UiText><UiText className="text-[10px] text-slate-600">{candidate.reasons.join(" ")}</UiText>{candidate.warnings.map(warning => <UiText key={warning} className="text-[10px] text-amber-800">{warning}</UiText>)}</UiBox><UiButton type="button" onClick={() => setSelectedResources(previous => ({ ...previous, [order.id]: { vehicleId: candidate.vehicle_id, driverId: previous[order.id]?.driverId || "" } }))} className="rounded border border-line px-2 py-1 text-[10px] font-semibold">{selectedResources[order.id]?.vehicleId === candidate.vehicle_id ? "Truck selected" : "Use truck"}</UiButton></UiBox>)}{dispatchSuggestions[order.id].vehicles.length === 0 && <UiText className="text-xs text-amber-800">No compatible available truck was found. Review vehicle status, active work, breakdowns, and capacity settings.</UiText>}</UiBox><UiText className="mt-2 text-[10px] text-slate-500">{dispatchSuggestions[order.id].drivers.length} driver(s) are free of recorded active trips. Shift, leave, and driver-hours checks are not available yet.</UiText><UiText className="mt-1 text-[10px] text-slate-400">{dispatchSuggestions[order.id].limitations[0]}</UiText></>}
            </UiBox>}
            {awaitingAssignment && <UiForm onSubmit={event => void assignOrder(event, order)} className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2 xl:grid-cols-4"><UiText className="text-xs font-semibold sm:col-span-2 xl:col-span-4">Confirm assignment</UiText><UiInput className={input} name="trip_number" required maxLength={64} placeholder="Trip number (e.g. TR-204)"/><UiSelect className={input} name="vehicle_id" required value={selectedResources[order.id]?.vehicleId || ""} onChange={event => setSelectedResources(previous => ({ ...previous, [order.id]: { vehicleId: event.target.value, driverId: previous[order.id]?.driverId || "" } }))}><option value="" disabled>Select truck</option>{(dispatchSuggestions[order.id] ? dispatchSuggestions[order.id].vehicles.map(candidate => ({ id: candidate.vehicle_id, registration_number: candidate.registration_number })) : vehicles.filter(vehicle => vehicle.status === "ACTIVE")).map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration_number}</option>)}</UiSelect><UiSelect className={input} name="driver_id" required value={selectedResources[order.id]?.driverId || ""} onChange={event => setSelectedResources(previous => ({ ...previous, [order.id]: { vehicleId: previous[order.id]?.vehicleId || "", driverId: event.target.value } }))}><option value="" disabled>Select driver</option>{(dispatchSuggestions[order.id] ? dispatchSuggestions[order.id].drivers : drivers.filter(driver => driver.status === "ACTIVE")).map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect><UiButton disabled={busy === order.id || !vehicles.some(vehicle => vehicle.status === "ACTIVE") || !drivers.some(driver => driver.status === "ACTIVE") || Boolean(dispatchSuggestions[order.id] && (!dispatchSuggestions[order.id].vehicles.length || !dispatchSuggestions[order.id].drivers.length))} className="rounded-md bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === order.id ? "Assigning…" : "Create trip and assign"}</UiButton></UiForm>}
          </UiBox></details></UiArticle>;
        })}{visibleOrders.length === 0 && <UiText className="p-8 text-center text-sm text-slate-500">{search || statusFilter ? "No orders match these filters. Try a different search or status." : "No dispatch orders yet. New transport orders will appear here."}</UiText>}</UiBox>
    {pagination.controls}
    </UiSection>
  </UiMain>;
}
