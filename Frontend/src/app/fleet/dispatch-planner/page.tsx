"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { UiAlert, UiButton, UiH1, UiH2, UiMain, UiSection, UiText } from "@/components/product-ui";

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
  useEffect(() => { void refresh().catch(e => setMessage(e.message)); }, [refresh]);
  const selectedOrders = useMemo(() => orders.filter(o => quantities[o.id] && Number(quantities[o.id]) > 0), [orders, quantities]);

  async function optimize(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage(""); setPlan(null); setSelected("");
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
    if (!plan || !selected) return;
    setBusy(true); setMessage("");
    try {
      const response = await apiFetch(`/fleet/dispatch-plans/${plan.plan_id}/confirm`, { method: "POST", body: JSON.stringify({ option_id: selected, fingerprint: plan.fingerprint, trip_number: tripNumber }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || "Could not confirm this plan.");
      const trips = data.trips || [data.trip];
      const unserved = data.unserved_orders?.length ? ` ${data.unserved_orders.length} shipment(s) remain unassigned; review the open dispatch queue.` : "";
      setMessage(`${trips.length} trip(s) confirmed across ${trips.length} truck/driver pair(s).${unserved}`); setPlan(null); setQuantities({}); setTripNumber(""); await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not confirm this plan."); }
    finally { setBusy(false); }
  }

  async function addSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      const response = await apiFetch("/fleet/driver-schedules", { method: "POST", body: JSON.stringify({ ...values, driver_id: scheduleDriver, kind: scheduleKind, starts_at: new Date(String(values.starts_at)).toISOString(), ends_at: new Date(String(values.ends_at)).toISOString() }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.error || "Could not save driver availability.");
      setMessage("Driver availability saved."); event.currentTarget.reset(); await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not save driver availability."); }
    finally { setBusy(false); }
  }

  async function removeSchedule(id: string) {
    setBusy(true); try { const response = await apiFetch(`/fleet/driver-schedules/${id}`, { method: "DELETE" }); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Could not remove schedule."); await refresh(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not remove schedule."); } finally { setBusy(false); }
  }

  return <UiMain className="mx-auto max-w-7xl space-y-7 px-5 py-8">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[.16em] text-forest">Transport operations · Dispatch</p><UiH1 className="mt-2">Dispatch planner</UiH1><UiText className="mt-2 max-w-3xl">Build multi-stop manifests, compare single-truck and fleet-level options, then confirm proposed trips after reviewing routes and constraints.</UiText></div><a className="text-sm font-semibold text-forest underline" href="/fleet/dispatch">Back to dispatch board</a></header>
    {message && <UiAlert>{message}</UiAlert>}
    <UiSection className="space-y-5 rounded-2xl border border-line bg-white p-5 shadow-sm"><div><UiH2>1. Choose shipments and dispatch window</UiH2><UiText className="mt-1">Partially assigned orders show their remaining eligible quantity when recalculated by the server.</UiText></div>
      {!orders.length ? <p className="rounded-xl bg-canvas p-5 text-sm text-muted">No open or partially assigned shipments need planning.</p> : <form onSubmit={optimize} className="space-y-5">
        <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="border-b border-line text-xs uppercase text-muted"><th className="py-3">Shipment</th><th>Customer and lane</th><th>Remaining load</th><th>Plan quantity</th></tr></thead><tbody>{orders.map(order => <tr key={order.id} className="border-b border-line/70"><td className="py-3 font-semibold">{order.order_number}<div className="text-xs font-normal text-muted">{order.status.replaceAll("_", " ")}</div></td><td>{order.customer.name}<div className="text-xs text-muted">{order.origin} → {order.destination}</div></td><td>{order.load_quantity || "—"} {order.load_unit}</td><td><input aria-label={`Quantity for ${order.order_number}`} className={`${field} max-w-36`} type="number" min="0" step="0.001" value={quantities[order.id] || ""} placeholder="Skip" onChange={e => setQuantities(v => ({ ...v, [order.id]: e.target.value }))} /></td></tr>)}</tbody></table></div>
        <div className="grid gap-4 md:grid-cols-2"><label className="text-sm font-medium">Window starts<input required type="datetime-local" className={`${field} mt-1`} value={start} onChange={e => setStart(e.target.value)} /></label><label className="text-sm font-medium">Window ends<input required type="datetime-local" className={`${field} mt-1`} value={end} onChange={e => setEnd(e.target.value)} /></label></div>
        <UiButton type="submit" disabled={busy || !selectedOrders.length}>{busy ? "Planning…" : `Generate options for ${selectedOrders.length} shipment(s)`}</UiButton>
      </form>}
    </UiSection>
    {plan && <UiSection className="space-y-5 rounded-2xl border border-line bg-white p-5 shadow-sm"><div><UiH2>2. Review and confirm</UiH2><UiText className="mt-1">Proposal expires {new Date(plan.expires_at).toLocaleString()}. Selecting an option does not dispatch it; confirmation checks availability and capacity again.</UiText></div>
      <div className="grid gap-3 lg:grid-cols-2">{plan.options.map(option => <label key={option.option_id} className={`cursor-pointer rounded-xl border p-4 ${selected === option.option_id ? "border-forest bg-forest/5 ring-1 ring-forest" : "border-line"}`}><div className="flex items-start gap-3"><input type="radio" name="option" checked={selected === option.option_id} onChange={() => setSelected(option.option_id)} /><div className="min-w-0 flex-1"><div className="flex flex-wrap justify-between gap-2"><strong>{option.assignments?.length ? `${option.assignments.length} vehicle/driver assignments` : option.vehicle}</strong><div className="flex flex-wrap gap-2">{option.optimization_status && <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-800">{option.optimization_status === "OPTIMAL_WITHIN_MODEL" ? "Best fleet fit" : "Best found · bounded search"}</span>}<span className="rounded-full bg-canvas px-2 py-1 text-xs">Score {option.score}/100</span></div></div>{option.assignments?.length ? option.assignments.map((assignment, assignmentIndex) => <div key={assignment.vehicle_id} className="mt-3 rounded-lg border border-line bg-white p-3"><p className="text-sm font-semibold">Trip {assignmentIndex + 1} · {assignment.vehicle}</p><p className="text-sm">{assignment.driver}</p><p className="mt-1 text-xs text-muted">{assignment.order_ids.length} shipment(s) · {assignment.route.provider_status === "UPDATED" ? `${assignment.route.distance_km} km Google road estimate` : assignment.route.distance_km == null ? "Distance unavailable" : `${assignment.route.distance_km} km straight-line estimate`}{assignment.route.estimated_travel_minutes != null ? ` · ${assignment.route.estimated_travel_minutes} min` : ""}</p><ol className="mt-2 space-y-1 border-l border-line pl-3">{assignment.route.stops.map((stop, i) => <li key={`${stop.order_id}-${stop.kind}`} className="text-xs"><span className="text-muted">{String(i + 1).padStart(2, "0")} · {stop.kind}</span> · {stop.order_number} · {stop.address}{stop.planned_at && <div className="text-muted">{new Date(stop.planned_at).toLocaleString()}</div>}</li>)}</ol></div>) : <><p className="mt-1 text-sm">{option.driver}</p><p className="mt-2 text-xs text-muted">{option.route.provider_status === "UPDATED" ? `${option.route.distance_km} km Google road estimate` : `${option.route.distance_km ?? "—"} km straight-line estimate`}{option.route.estimated_travel_minutes != null ? ` · ${option.route.estimated_travel_minutes} min` : ""}</p><ol className="mt-3 space-y-2 border-l border-line pl-4">{option.route.stops.map((stop, i) => <li key={`${stop.order_id}-${stop.kind}`} className="text-sm"><span className="text-xs text-muted">{String(i + 1).padStart(2, "0")} · {stop.kind}</span><div>{stop.order_number} · {stop.address}</div><div className="text-xs text-muted">{stop.planned_at ? new Date(stop.planned_at).toLocaleString() : "Time not estimated"}</div></li>)}</ol></>}{!!option.unserved_orders?.length && <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900"><strong>{option.unserved_orders.length} shipment(s) remain unassigned</strong>{option.unserved_orders.map(item => <p key={item.order_id} className="mt-1">{item.order_number}: {item.reasons.join(" ")}</p>)}</div>}<ul className="mt-3 space-y-1 text-xs text-amber-800">{option.warnings.map((warning, i) => <li key={i}>• {warning}</li>)}</ul></div></div></label>)}</div>
      {!!plan.limitations.length && <div className="rounded-xl bg-canvas p-4 text-xs text-muted"><strong className="text-ink">Estimate limits</strong><ul className="mt-2 list-disc space-y-1 pl-5">{plan.limitations.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
      {!!plan.options.length && <div className="flex flex-wrap items-end gap-3"><label className="text-sm font-medium">Trip number<input className={`${field} mt-1`} value={tripNumber} onChange={e => setTripNumber(e.target.value)} placeholder="TRIP-2026-001" maxLength={64} /></label><UiButton disabled={busy || !selected || !tripNumber.trim()} onClick={() => void confirm()}>{busy ? "Confirming…" : "Confirm dispatch"}</UiButton></div>}
    </UiSection>}
    <UiSection className="space-y-5 rounded-2xl border border-line bg-white p-5 shadow-sm"><div><UiH2>Driver availability</UiH2><UiText className="mt-1">Add shifts so the planner can distinguish confirmed working windows from unrecorded availability.</UiText></div>
      <form onSubmit={addSchedule} className="grid gap-3 md:grid-cols-2 xl:grid-cols-5"><label className="text-sm">Driver<select required className={`${field} mt-1`} value={scheduleDriver} onChange={e => setScheduleDriver(e.target.value)}><option value="">Select driver</option>{drivers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label><label className="text-sm">Availability<select className={`${field} mt-1`} value={scheduleKind} onChange={e => setScheduleKind(e.target.value)}><option value="SHIFT">Available shift</option><option value="LEAVE">Leave</option><option value="UNAVAILABLE">Unavailable</option></select></label><label className="text-sm">Starts<input required name="starts_at" type="datetime-local" className={`${field} mt-1`} /></label><label className="text-sm">Ends<input required name="ends_at" type="datetime-local" className={`${field} mt-1`} /></label><label className="text-sm">Note<input name="note" maxLength={240} className={`${field} mt-1`} placeholder="Optional" /></label><div><UiButton type="submit" disabled={busy || !scheduleDriver}>Save availability</UiButton></div></form>
      <div className="divide-y divide-line">{schedules.length ? schedules.map(item => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><div><strong>{item.driver}</strong><span className="ml-2 rounded-full bg-canvas px-2 py-1 text-xs">{item.kind}</span><div className="mt-1 text-xs text-muted">{new Date(item.starts_at).toLocaleString()} – {new Date(item.ends_at).toLocaleString()} {item.note && `· ${item.note}`}</div></div><button className="text-sm font-semibold text-red-700" disabled={busy} onClick={() => void removeSchedule(item.id)}>Remove</button></div>) : <p className="py-3 text-sm text-muted">No driver schedules recorded yet.</p>}</div>
    </UiSection>
  </UiMain>;
}
