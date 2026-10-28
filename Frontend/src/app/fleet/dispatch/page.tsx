"use client";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiText } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AppLink as Link } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
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
const input = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const lanes = [
    { id: "OPEN", title: "Needs dispatch", hint: "Order has no truck or driver" },
    { id: "ASSIGNED", title: "Assigned", hint: "Trip created; awaiting pickup check-in" },
    { id: "LOADING", title: "At pickup", hint: "Driver checked in; confirm the load" },
    { id: "IN_TRANSIT", title: "In transit", hint: "Load confirmed; delivery is pending" },
    { id: "DELIVERED", title: "Delivered", hint: "Check proof of delivery" },
    { id: "CANCELLED", title: "Cancelled", hint: "Cancelled orders" },
];
const activeFollowUp = (item: FollowUp) => ["OPEN", "IN_PROGRESS"].includes(item.status);
const labelTime = (value: string | null) => value ? new Date(value).toLocaleString() : null;
export default function FleetDispatchPage() {
    const [statusFilter, setStatusFilter] = useState("");
    const [orders, setOrders] = useState<Order[]>([]);
    const [trips, setTrips] = useState<Trip[]>([]);
    const [vehicles, setVehicles] = useState<Vehicle[]>([]);
    const [drivers, setDrivers] = useState<Driver[]>([]);
    const [followUps, setFollowUps] = useState<FollowUp[]>([]);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState("");
    const [exceptionTrip, setExceptionTrip] = useState("");
    const tripsByOrder = useMemo(() => new Map(trips.filter(trip => trip.transport_order).map(trip => [trip.transport_order!.id, trip])), [trips]);
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
    const visibleOrders = orders.filter(order => !statusFilter || order.status === statusFilter);
    const pagination = useListPagination(visibleOrders, statusFilter);
    return <UiMain className="w-full min-w-0 space-y-5 px-4 py-8 sm:px-6 lg:px-8">
    <UiHeader className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet & trips</UiText><UiH1 className="mt-1 text-2xl font-bold">Dispatch</UiH1><UiText className="mt-1 text-sm text-slate-500">Assign orders, follow pickup and delivery milestones, and capture issues as they happen.</UiText></UiBox><UiBox className="flex gap-2"><Link href="/fleet/orders" className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">Transport orders</Link><Link href="/fleet/trips" className="rounded-lg bg-forest px-3 py-2 text-sm font-semibold text-white">All trips</Link></UiBox></UiHeader>
    <LiveData onRefresh={refresh} paused={Boolean(busy || exceptionTrip)} interval={20000}/>
    {message && <UiAlert role="status" className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{message}</UiAlert>}
    <UiSection className="overflow-hidden rounded-xl border border-line bg-white">
      <UiHeader className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4"><UiH2 className="text-sm font-bold">Dispatch orders <UiSpan className="ml-2 text-slate-400">{orders.filter(order => !statusFilter || order.status === statusFilter).length}</UiSpan></UiH2><UiLabel className="flex items-center gap-2 text-xs font-semibold">Status<UiSelect className={input} value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">All statuses</option>{lanes.map(lane => <option key={lane.id} value={lane.id}>{lane.title}</option>)}</UiSelect></UiLabel></UiHeader>
      <UiBox className="divide-y divide-line">{pagination.rows.map(order => {
            const trip = tripsByOrder.get(order.id);
            const exceptions = followUps.filter(item => item.trip_id === trip?.id && activeFollowUp(item));
            return <UiArticle key={order.id} className="bg-white p-4 sm:p-5"><UiBox className="flex items-start justify-between gap-2"><UiBox><UiH3 className="text-sm font-bold">{order.order_number}</UiH3><UiText className="text-xs text-slate-500">{order.customer.name}</UiText></UiBox><UiSpan className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold">{order.status.replaceAll("_", " ")}</UiSpan></UiBox><UiText className="mt-3 text-xs font-medium text-slate-700">{order.origin} → {order.destination}</UiText><UiText className="mt-1 text-[11px] text-slate-500">{[order.cargo_description, order.load_quantity && `${order.load_quantity} ${order.load_unit}`.trim()].filter(Boolean).join(" · ") || "Cargo details not set"}</UiText>{(order.pickup_due_at || order.delivery_due_at) && <UiText className="mt-2 text-[10px] text-slate-500">{order.pickup_due_at && <>Pickup by {labelTime(order.pickup_due_at)}</>}{order.pickup_due_at && order.delivery_due_at && " · "}{order.delivery_due_at && <>Deliver by {labelTime(order.delivery_due_at)}</>}</UiText>}
            {trip && <><UiBox className="mt-3 rounded-md bg-slate-50 p-2 text-xs"><UiText className="font-semibold">{trip.vehicle.registration_number} · {trip.driver.name}</UiText><UiText className="mt-1 text-slate-600">{milestone(order, trip)}</UiText></UiBox>{exceptions.length > 0 && <UiBox className="mt-2 space-y-1 rounded-md bg-amber-50 p-2 text-[11px] text-amber-900">{exceptions.map(item => <UiText key={item.id}><UiStrong>Needs attention:</UiStrong> {item.description}</UiText>)}</UiBox>}{trip.delivery_at && !trip.delivery_proof_name && !trip.delivery_signature_name && <UiText className="mt-2 text-[11px] font-semibold text-rose-700">Proof of delivery is missing.</UiText>}{!trip.delivery_at && <UiButton type="button" onClick={() => setExceptionTrip(exceptionTrip === trip.id ? "" : trip.id)} className="mt-3 text-xs font-semibold text-forest">{exceptionTrip === trip.id ? "Close issue form" : "Report a trip issue"}</UiButton>}{exceptionTrip === trip.id && <UiForm onSubmit={event => void reportException(event, trip)} className="mt-2 space-y-2"><UiSelect className={input} name="category"><option value="DELAY">Delay</option><option value="CUSTOMER_UNAVAILABLE">Customer unavailable</option><option value="VEHICLE_ISSUE">Vehicle issue</option><option value="CARGO_ISSUE">Cargo issue</option><option value="ROUTE_ISSUE">Route issue</option><option value="OTHER">Other</option></UiSelect><UiInput className={input} name="description" required maxLength={240} placeholder="Briefly describe the issue"/><UiButton disabled={busy === `exception:${trip.id}`} className="rounded-md bg-forest px-3 py-2 text-xs font-semibold text-white">{busy === `exception:${trip.id}` ? "Saving…" : "Add to follow-ups"}</UiButton></UiForm>}</>}
            {!trip && order.status !== "CANCELLED" && <UiForm onSubmit={event => void assignOrder(event, order)} className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2 xl:grid-cols-4"><UiText className="text-xs font-semibold sm:col-span-2 xl:col-span-4">Assign truck and driver</UiText><UiInput className={input} name="trip_number" required maxLength={64} placeholder="Trip number (e.g. TR-204)"/><UiSelect className={input} name="vehicle_id" required defaultValue=""><option value="" disabled>Select truck</option>{vehicles.filter(vehicle => vehicle.status === "ACTIVE").map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration_number}</option>)}</UiSelect><UiSelect className={input} name="driver_id" required defaultValue=""><option value="" disabled>Select driver</option>{drivers.filter(driver => driver.status === "ACTIVE").map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect><UiButton disabled={busy === order.id || !vehicles.some(vehicle => vehicle.status === "ACTIVE") || !drivers.some(driver => driver.status === "ACTIVE")} className="rounded-md bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === order.id ? "Assigning…" : "Create trip and assign"}</UiButton></UiForm>}
          </UiArticle>;
        })}{orders.filter(order => !statusFilter || order.status === statusFilter).length === 0 && <UiText className="p-8 text-center text-sm text-slate-500">No orders match this status.</UiText>}</UiBox>
    {pagination.controls}
    </UiSection>
  </UiMain>;
}
