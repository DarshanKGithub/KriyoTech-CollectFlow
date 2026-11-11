"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { UiAlert, UiButton, UiH1, UiH2, UiMain, UiSection, UiText } from "@/components/product-ui";
import { ArrowRight, MapPin, Truck } from "lucide-react";

type Order = { id: string; order_number: string; customer: { name: string }; origin: string; destination: string; load_quantity: string | null; load_unit: string; status: string; pickup_due_at: string | null; delivery_due_at: string | null };
type RouteStop = { order_id: string; order_number: string; kind: string; address: string; planned_at: string | null };
type Route = { stops: RouteStop[]; distance_km: number | null; estimated_travel_minutes: number | null; provider_status?: string; method?: string; warnings?: string[] };
type Assignment = { vehicle_id: string; vehicle: string; driver_id: string; driver: string; order_ids: string[]; score: number; route: Route; warnings: string[] };
type Option = { option_id: string; vehicle_id: string; vehicle: string; driver_id: string; driver: string; score: number; score_components: Record<string, number>; optimization_status?: string; route: Route & { distance_kind: string; method: string; warnings: string[] }; assignments?: Assignment[]; unserved_orders?: { order_id: string; order_number: string; quantity: string; reasons: string[] }[]; warnings: string[] };
type Plan = { plan_id: string; fingerprint: string; expires_at: string; options: Option[]; limitations: string[]; status: string };
type Schedule = { id: string; driver_id: string; driver: string; kind: string; starts_at: string; ends_at: string; note: string };
type Driver = { id: string; name: string };
const field = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const isoLocal = (d: Date) => { const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000); return local.toISOString().slice(0, 16); };
const dateTime = (value: string) => new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

function RoutePreview({ route }: { route: Route }) {
  return <div className="mt-3">
    <p className="text-xs text-slate-600">
      {route.distance_km == null ? "Distance unavailable" : `${route.distance_km} km · ${route.provider_status === "UPDATED" ? "Road estimate" : "Straight-line estimate"}`}
      {route.estimated_travel_minutes != null && ` · ${route.estimated_travel_minutes} min estimated`}
    </p>
    <ol className="mt-3 space-y-3">
      {route.stops.map((stop, index) => <li key={`${stop.order_id}-${stop.kind}-${index}`} className="flex items-start gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-emerald-50 text-xs font-bold text-forest">{index + 1}</span>
        <div className="min-w-0 break-words">
          <p className="text-sm font-semibold">{stop.kind === "PICKUP" ? "Pickup" : stop.kind === "DELIVERY" ? "Delivery" : stop.kind} · {stop.address}</p>
          <p className="text-xs text-slate-600">{stop.order_number} · {stop.planned_at ? dateTime(stop.planned_at) : "Time not estimated"}</p>
        </div>
      </li>)}
    </ol>
    {!!route.warnings?.length && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-900">{route.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
  </div>;
}

export default function DispatchPlannerPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [start, setStart] = useState(isoLocal(new Date(Date.now() + 60 * 60 * 1000)));
  const [end, setEnd] = useState(isoLocal(new Date(Date.now() + 9 * 60 * 60 * 1000)));
  const [plan, setPlan] = useState<Plan | null>(null);
  const [selected, setSelected] = useState("");
  const [tripNumber, setTripNumber] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [scheduleDriver, setScheduleDriver] = useState("");
  const [scheduleKind, setScheduleKind] = useState("SHIFT");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [orderResponse, driverResponse, scheduleResponse] = await Promise.all([
      apiFetch("/fleet/orders"), apiFetch("/fleet/drivers"), apiFetch("/fleet/driver-schedules"),
    ]);
    if (![orderResponse, driverResponse, scheduleResponse].every(r => r.ok)) throw new Error("Could not load dispatch planning data for this workspace.");
    const orderData = await orderResponse.json();
    setOrders(orderData.filter((row: Order) => ["OPEN", "PARTIALLY_ASSIGNED"].includes(row.status)));
    const driverData = await driverResponse.json(); setDrivers(driverData);
    setSchedules(await scheduleResponse.json());
  }, []);
  useEffect(() => { void refresh().catch(e => setMessage(e.message)).finally(() => setLoading(false)); }, [refresh]);
  const selectedOrders = useMemo(() => orders.filter(o => quantities[o.id] && Number(quantities[o.id]) > 0), [orders, quantities]);
  const chosenOrders = orders.filter(order => quantities[order.id] !== undefined);
  const visibleOrders = orders.filter(order => quantities[order.id] !== undefined ||
    [order.order_number, order.customer.name, order.origin, order.destination].join(" ").toLowerCase().includes(search.trim().toLowerCase()));
  const selectedOption = plan?.options.find(option => option.option_id === selected);
  const validWindow = Boolean(start && end && new Date(end) > new Date(start));

  function changeInputs() {
    setPlan(null);
    setSelected("");
  }

  async function optimize(event: FormEvent) {
    event.preventDefault();
    if (busy || !validWindow || !selectedOrders.length || selectedOrders.length !== chosenOrders.length) return;
    setBusy(true); setMessage(""); changeInputs();
    try {
      const response = await apiFetch("/fleet/dispatch-plans/optimize", { method: "POST", body: JSON.stringify({
        allocations: selectedOrders.map(o => ({ order_id: o.id, quantity: quantities[o.id] })),
        starts_at: new Date(start).toISOString(), ends_at: new Date(end).toISOString(), request_key: crypto.randomUUID(),
      }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || "Could not create a dispatch plan.");
      setPlan(data); setSelected(data.options?.[0]?.option_id || "");
      if (!data.options?.length) setMessage("No feasible truck and driver option was found. Review the order details and fleet availability.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not create a dispatch plan."); }
    finally { setBusy(false); }
  }

  async function confirm() {
    if (busy || !plan || !selected || !tripNumber.trim()) return;
    if (Date.parse(plan.expires_at) <= Date.now()) {
      setMessage("This proposal expired. Generate new options before assigning a trip.");
      changeInputs();
      return;
    }
    setBusy(true); setMessage("");
    try {
      const response = await apiFetch(`/fleet/dispatch-plans/${plan.plan_id}/confirm`, { method: "POST", body: JSON.stringify({ option_id: selected, fingerprint: plan.fingerprint, trip_number: tripNumber.trim() }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || "Could not confirm this plan.");
      const trips = data.trips || [data.trip];
      const unserved = data.unserved_orders?.length ? ` ${data.unserved_orders.length} shipment(s) remain unassigned; review the open dispatch queue.` : "";
      setMessage(`${trips.length} trip(s) confirmed across ${trips.length} truck/driver pair(s).${unserved}`); setPlan(null); setQuantities({}); setTripNumber(""); await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not confirm this plan."); }
    finally { setBusy(false); }
  }

  async function addSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; setBusy(true); setMessage(""); const values = Object.fromEntries(new FormData(form).entries());
    try {
      const response = await apiFetch("/fleet/driver-schedules", { method: "POST", body: JSON.stringify({ ...values, driver_id: scheduleDriver, kind: scheduleKind, starts_at: new Date(String(values.starts_at)).toISOString(), ends_at: new Date(String(values.ends_at)).toISOString() }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || "Could not save driver availability.");
      setMessage("Driver availability saved."); form.reset(); changeInputs(); await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not save driver availability."); }
    finally { setBusy(false); }
  }

  async function removeSchedule(id: string) {
    setBusy(true); try { const response = await apiFetch(`/fleet/driver-schedules/${id}`, { method: "DELETE" }); if (!response.ok) { const data = await response.json(); throw new Error(data.error || "Could not remove schedule."); } changeInputs(); await refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not remove schedule."); } finally { setBusy(false); }
  }

  return <UiMain className="mx-auto w-full max-w-7xl space-y-5 px-4 py-7 sm:px-6">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-wider text-forest">Fleet · Dispatch</p>
        <UiH1 className="mt-1 text-2xl font-bold">Multi-stop trip planner</UiH1>
        <UiText className="mt-1 text-sm text-slate-600">Choose shipments, review the suggested stops, and assign a truck and driver.</UiText>
      </div>
      <a className="text-sm font-semibold text-forest underline" href="/fleet/dispatch">Back to dispatch</a>
    </header>
    {message && <UiAlert role="status">{message}</UiAlert>}

    <UiSection className="rounded-xl border border-line bg-white p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div><UiH2 className="text-lg font-bold">1. Choose shipments</UiH2><UiText className="mt-1 text-sm text-slate-600">Select the orders to include and enter how much to carry.</UiText></div>
        <span className="rounded-full bg-emerald-50 px-3 py-1 text-sm font-semibold text-forest">{chosenOrders.length} selected</span>
      </div>
      {loading ? <UiText>Loading shipments…</UiText> : !orders.length ? <UiText className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">No open or partly assigned shipments need planning.</UiText> :
        <form onSubmit={optimize}>
          <fieldset disabled={busy} className="min-w-0 space-y-4">
            <label className="block max-w-sm text-sm font-semibold">Find an order
              <input className={`${field} mt-1`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Order, customer, or location"/>
            </label>
            <div className="max-h-80 divide-y divide-line overflow-y-auto rounded-xl border border-line">
              {visibleOrders.map(order => {
                const checked = quantities[order.id] !== undefined;
                return <div key={order.id} className={`grid gap-2 p-3 sm:grid-cols-[minmax(0,1fr)_10rem] ${checked ? "bg-emerald-50/50" : ""}`}>
                  <label className="flex min-w-0 cursor-pointer items-start gap-3">
                    <input type="checkbox" className="mt-1 size-4 shrink-0 accent-emerald-700" checked={checked} onChange={event => {
                      const include = event.target.checked;
                      changeInputs();
                      setQuantities(current => {
                        const next = { ...current };
                        if (include) next[order.id] = order.status === "OPEN" ? order.load_quantity || "" : "";
                        else delete next[order.id];
                        return next;
                      });
                    }}/>
                    <span className="min-w-0 break-words">
                      <span className="block text-sm font-semibold">{order.order_number} · {order.customer.name}</span>
                      <span className="block text-sm text-slate-600">{order.origin} → {order.destination}</span>
                      <span className="text-xs text-slate-500">{order.status === "PARTIALLY_ASSIGNED" ? "Partly assigned · " : ""}{order.load_quantity ? `Order load ${order.load_quantity} ${order.load_unit}` : "Load size not recorded"}</span>
                    </span>
                  </label>
                  {checked && <label className="ml-7 text-xs font-medium sm:ml-0">Quantity to carry {order.load_unit && `(${order.load_unit})`}
                    <input className={`${field} mt-1`} aria-label={`Quantity for ${order.order_number}`} required type="number" min="0.001" step="0.001" value={quantities[order.id]}
                      onChange={event => { changeInputs(); setQuantities(current => ({ ...current, [order.id]: event.target.value })); }}/>
                  </label>}
                </div>;
              })}
              {!visibleOrders.length && <p className="p-4 text-sm text-slate-600">No orders match this search.</p>}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm font-semibold">Dispatch window starts<input required type="datetime-local" className={`${field} mt-1`} value={start} onChange={event => { changeInputs(); setStart(event.target.value); }}/></label>
              <label className="text-sm font-semibold">Dispatch window ends<input required type="datetime-local" className={`${field} mt-1`} value={end} onChange={event => { changeInputs(); setEnd(event.target.value); }}/></label>
            </div>
            {start && end && !validWindow && <p className="text-sm text-rose-700">The end time must be after the start time.</p>}
            <UiButton type="submit" disabled={busy || !validWindow || !selectedOrders.length || selectedOrders.length !== chosenOrders.length} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">
              {busy && !plan ? "Finding options…" : "Find routes and available trucks"} <ArrowRight size={16} className="ml-2"/>
            </UiButton>
          </fieldset>
        </form>}
    </UiSection>

    <UiSection className="rounded-xl border border-line bg-white p-4 sm:p-5">
      <UiH2 className="text-lg font-bold">2. Review the route</UiH2>
      {!plan?.options.length ? <UiText className="mt-2 text-sm text-slate-600">{plan ? "No routes are available for this selection. Adjust the shipments or dispatch window." : "Find options above to see the suggested pickup and delivery stops."}</UiText> : <>
        <div role="group" aria-label="Trip options" className="mt-4 grid gap-2 sm:grid-cols-2">
          {plan.options.map((option, index) => <label key={option.option_id} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${selected === option.option_id ? "border-forest bg-emerald-50" : "border-line"}`}>
            <input type="radio" name="option" checked={selected === option.option_id} disabled={busy} onChange={() => setSelected(option.option_id)} className="mt-1 accent-emerald-700"/>
            <span><span className="block text-sm font-semibold">Option {index + 1} · {option.assignments?.length ? `${option.assignments.length} ${option.assignments.length === 1 ? "trip" : "trips"}` : option.vehicle}</span>
              <span className="text-xs text-slate-600">{option.assignments?.length ? option.assignments.map(item => item.vehicle).join(", ") : option.driver} · Fit score {option.score}/100</span></span>
          </label>)}
        </div>
        {selectedOption && <div className="mt-4 rounded-xl border border-line p-4">
          <div className="flex items-center gap-2 text-sm font-semibold"><MapPin size={16} className="text-forest"/> Suggested stop order</div>
          {selectedOption.assignments?.length ? selectedOption.assignments.map((assignment, index) => <div key={assignment.vehicle_id} className="mt-3 border-t border-line pt-3">
            <p className="text-sm font-bold">Trip {index + 1} · {assignment.vehicle} · {assignment.driver}</p>
            <RoutePreview route={assignment.route}/>
            {!!assignment.warnings.length && <ul className="mt-3 list-disc pl-5 text-xs text-amber-900">{assignment.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
          </div>) : <RoutePreview route={selectedOption.route}/>}
          {!!selectedOption.unserved_orders?.length && <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            <strong>{selectedOption.unserved_orders.length} shipments would remain unassigned</strong>
            {selectedOption.unserved_orders.map(item => <p key={item.order_id} className="mt-1 text-xs">{item.order_number} · {item.reasons.join(" ")}</p>)}
          </div>}
          {!!selectedOption.warnings.length && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-900">{selectedOption.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
        </div>}
      </>}
      {!!plan?.limitations.length && <details className="mt-3 text-sm text-slate-600"><summary className="cursor-pointer font-semibold">Planning limits</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">{plan.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
      </details>}
    </UiSection>

    <UiSection className="rounded-xl border border-line bg-white p-4 sm:p-5">
      <UiH2 className="text-lg font-bold">3. Assign truck and driver</UiH2>
      {selectedOption && plan ? <>
        <div className="mt-3 space-y-2">
          {(selectedOption.assignments?.length ? selectedOption.assignments : [selectedOption]).map(item => <div key={item.vehicle_id} className="flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50 p-3 text-sm">
            <Truck size={17} className="text-forest"/><strong>Truck {item.vehicle}</strong><span>· Driver {item.driver}</span>
          </div>)}
        </div>
        <UiText className="mt-3 text-sm text-slate-600">Proposal expires {dateTime(plan.expires_at)}. Availability is checked again when you confirm.</UiText>
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void confirm(); }}>
          <label className="text-sm font-semibold">Trip number<input required className={`${field} mt-1`} value={tripNumber} onChange={event => setTripNumber(event.target.value)} placeholder="e.g. TRIP-204" maxLength={64}/></label>
          <UiButton type="submit" disabled={busy || !tripNumber.trim()} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">{busy ? "Confirming…" : "Confirm assignment"}</UiButton>
        </form>
      </> : <UiText className="mt-2 text-sm text-slate-600">Choose a route option to see its truck and driver.</UiText>}
    </UiSection>
    <details className="space-y-4 rounded-xl border border-line bg-white p-4 sm:p-5"><summary className="cursor-pointer text-sm font-semibold">Manage driver availability</summary><UiText className="text-sm text-slate-600">Record shifts, leave, or unavailable time.</UiText>
      <form onSubmit={addSchedule} className="grid gap-3 md:grid-cols-2 xl:grid-cols-5"><label className="text-sm">Driver<select required className={`${field} mt-1`} value={scheduleDriver} onChange={e => setScheduleDriver(e.target.value)}><option value="">Select driver</option>{drivers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label><label className="text-sm">Availability<select className={`${field} mt-1`} value={scheduleKind} onChange={e => setScheduleKind(e.target.value)}><option value="SHIFT">Available shift</option><option value="LEAVE">Leave</option><option value="UNAVAILABLE">Unavailable</option></select></label><label className="text-sm">Starts<input required name="starts_at" type="datetime-local" className={`${field} mt-1`} /></label><label className="text-sm">Ends<input required name="ends_at" type="datetime-local" className={`${field} mt-1`} /></label><label className="text-sm">Note<input name="note" maxLength={240} className={`${field} mt-1`} placeholder="Optional" /></label><div><UiButton type="submit" disabled={busy || !scheduleDriver}>Save availability</UiButton></div></form>
      <div className="divide-y divide-line">{schedules.length ? schedules.map(item => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><div><strong>{item.driver}</strong><span className="ml-2 rounded-full bg-canvas px-2 py-1 text-xs">{item.kind}</span><div className="mt-1 text-xs text-muted">{new Date(item.starts_at).toLocaleString()} – {new Date(item.ends_at).toLocaleString()} {item.note && `· ${item.note}`}</div></div><button className="text-sm font-semibold text-red-700" disabled={busy} onClick={() => void removeSchedule(item.id)}>Remove</button></div>) : <p className="py-3 text-sm text-muted">No driver schedules recorded yet.</p>}</div>
    </details>
  </UiMain>;
}
