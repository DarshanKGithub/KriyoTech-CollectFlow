"use client";

import { PageSkeleton } from "@/components/content-skeleton";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiText, UiTextarea } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { apiFetch } from "@/lib/api";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import { ArrowRight, CalendarClock, CircleAlert, Clock3, Plus, RefreshCw, Search, Warehouse, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

type Dock = { id: string; site_name: string; code: string; name: string; parallel_capacity: number };
type Order = { id: string; order_number: string; customer: { name: string }; origin: string; destination: string; status: string };
type Appointment = {
    id: string; dock_id: string; dock_name: string; site_name: string; order_id: string; order_number: string; customer: string;
    origin: string; destination: string; appointment_type: "PICKUP" | "DELIVERY"; starts_at: string; ends_at: string; status: string;
    checked_in_at: string | null; checked_out_at: string | null; loading_started_at: string | null; loading_finished_at: string | null;
    delay_reason: string; wait_minutes: number | null; free_minutes: number; chargeable_minutes: number; detention_estimate: string;
    detention_status: "OVER_FREE_TIME" | "WITHIN_FREE_TIME" | "NOT_CHECKED_IN"; notes: string;
};
type AppointmentType = "PICKUP" | "DELIVERY";
type DialogMode = "booking" | "dock" | null;

const input = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const localInput = (date: Date) => { const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60000); return adjusted.toISOString().slice(0, 16); };
const initialStart = () => { const date = new Date(); date.setHours(date.getHours() + 1, 0, 0, 0); return localInput(date); };
const initialEnd = () => { const date = new Date(); date.setHours(date.getHours() + 2, 0, 0, 0); return localInput(date); };
const appointmentStatus = (value: string) => value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const dateTime = (value: string) => new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
const statusClass = (status: string) => status === "BOOKED" ? "bg-blue-50 text-blue-700" : status === "ARRIVED" ? "bg-amber-50 text-amber-800" : status === "LOADING" ? "bg-violet-50 text-violet-700" : status === "COMPLETED" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600";

export default function DockSchedulePage() {
    const [docks, setDocks] = useState<Dock[]>([]);
    const [orders, setOrders] = useState<Order[]>([]);
    const [appointments, setAppointments] = useState<Appointment[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState("");
    const [message, setMessage] = useState("");
    const [dialog, setDialog] = useState<DialogMode>(null);
    const [startsAt, setStartsAt] = useState(initialStart);
    const [endsAt, setEndsAt] = useState(initialEnd);
    const [appointmentType, setAppointmentType] = useState<AppointmentType>("PICKUP");
    const [detentionAppointment, setDetentionAppointment] = useState("");
    const [delayReason, setDelayReason] = useState("");
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [dockResponse, orderResponse, appointmentResponse] = await Promise.all([apiFetch("/fleet/docks"), apiFetch("/fleet/orders"), apiFetch("/fleet/dock-appointments")]);
            const [dockData, orderData, appointmentData] = await Promise.all([dockResponse.json(), orderResponse.json(), appointmentResponse.json()]);
            if (!dockResponse.ok || !orderResponse.ok || !appointmentResponse.ok)
                throw new Error(dockData.error || orderData.error || appointmentData.error || "Could not load the dock schedule. Check workspace access and try again.");
            setDocks(dockData);
            setOrders(orderData);
            setAppointments(appointmentData);
            setMessage("");
            return true;
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not load the dock schedule.");
            return false;
        }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { void load(); }, [load]);

    async function createDock(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (saving) return;
        setSaving("dock");
        setMessage("");
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        try {
            const response = await apiFetch("/fleet/docks", { method: "POST", body: JSON.stringify({ site_name: form.get("site_name"), code: form.get("code"), name: form.get("name"), parallel_capacity: Number(form.get("parallel_capacity")) }) });
            const data = await response.json().catch(() => null);
            if (!response.ok) throw new Error(data?.error || "Could not add the dock. Check the details and try again.");
            formElement.reset();
            setDialog(null);
            const refreshed = await load();
            setMessage(refreshed ? "Dock added to this workspace." : "Dock added, but the list did not refresh. Use Refresh to reload it.");
        }
        catch (error) { setMessage(error instanceof Error ? error.message : "Could not add the dock."); }
        finally { setSaving(""); }
    }

    async function bookAppointment(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (saving) return;
        const start = new Date(startsAt);
        const end = new Date(endsAt);
        if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
            setMessage("Choose a valid end time after the start time.");
            return;
        }
        if (end.getTime() - start.getTime() > 12 * 60 * 60 * 1000) {
            setMessage("A dock slot can be no longer than 12 hours.");
            return;
        }
        setSaving("booking");
        setMessage("");
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        try {
            const response = await apiFetch("/fleet/dock-appointments", { method: "POST", body: JSON.stringify({ dock_id: form.get("dock_id"), order_id: form.get("order_id"), appointment_type: form.get("appointment_type"), starts_at: start.toISOString(), ends_at: end.toISOString(), idempotency_key: crypto.randomUUID(), notes: form.get("notes") }) });
            const data = await response.json().catch(() => null);
            if (!response.ok) throw new Error(data?.error || "Could not book this dock time. Check capacity and order status.");
            formElement.reset();
            setStartsAt(initialStart());
            setEndsAt(initialEnd());
            setAppointmentType("PICKUP");
            setDialog(null);
            const refreshed = await load();
            setMessage(refreshed ? "Dock time booked." : "Dock time booked, but the schedule did not refresh. Use Refresh to reload it.");
        }
        catch (error) { setMessage(error instanceof Error ? error.message : "Could not book this dock time."); }
        finally { setSaving(""); }
    }

    async function updateAppointment(row: Appointment, action: "arrive" | "start" | "complete" | "cancel") {
        if (saving) return;
        setSaving(row.id);
        setMessage("");
        try {
            const response = await apiFetch(`/fleet/dock-appointments/${row.id}/${action}`, { method: "POST", body: JSON.stringify({}) });
            const data = await response.json().catch(() => null);
            if (!response.ok) throw new Error(data?.error || "Could not update this appointment.");
            const refreshed = await load();
            const pastTense = action === "arrive" ? "checked in" : action === "start" ? "marked as loading" : action === "complete" ? "completed" : "cancelled";
            setMessage(refreshed ? `Appointment ${pastTense}.` : `Appointment ${pastTense}, but the schedule did not refresh. Use Refresh to reload it.`);
        }
        catch (error) { setMessage(error instanceof Error ? error.message : "Could not update the appointment."); }
        finally { setSaving(""); }
    }

    async function detentionAction(action: "reason" | "finish-loading" | "prepare-billing") {
        if (!detentionAppointment || saving) return;
        setSaving(`detention:${action}`);
        setMessage("");
        try {
            const response = await apiFetch(`/fleet/detention/${detentionAppointment}/${action}`, { method: "POST", body: JSON.stringify({ reason: delayReason }) });
            const data = await response.json().catch(() => null);
            if (!response.ok) throw new Error(data?.error || "Could not update detention evidence.");
            const refreshed = await load();
            setMessage(refreshed ? action === "prepare-billing" ? "Detention draft prepared. Submit the trip for independent approval before customer billing." : "Detention record updated." : "Detention record updated, but the schedule did not refresh.");
        }
        catch (error) { setMessage(error instanceof Error ? error.message : "Could not update detention evidence."); }
        finally { setSaving(""); }
    }

    const schedulableOrders = orders.filter(order => appointmentType === "PICKUP" ? ["OPEN", "ASSIGNED"].includes(order.status) : order.status === "IN_TRANSIT");
    const detentionRows = appointments.filter(row => row.detention_status === "OVER_FREE_TIME");
    const estimatedDetention = detentionRows.reduce((total, row) => total + Number(row.detention_estimate || 0), 0);
    const selectedDetention = appointments.find(row => row.id === detentionAppointment);
    const checkedInCount = appointments.filter(row => row.checked_in_at && !row.checked_out_at).length;
    const activeAppointmentsCount = appointments.filter(row => ["BOOKED", "ARRIVED", "LOADING"].includes(row.status)).length;
    const visibleAppointments = useMemo(() => {
        const query = search.trim().toLowerCase();
        return appointments.filter(row => {
            const matchesStatus = !statusFilter || row.status === statusFilter;
            const matchesSearch = !query || [row.order_number, row.customer, row.site_name, row.dock_name, row.origin, row.destination].some(value => value?.toLowerCase().includes(query));
            return matchesStatus && matchesSearch;
        });
    }, [appointments, search, statusFilter]);
    const page = useListPagination(visibleAppointments, `${search}:${statusFilter}`);

    if (loading && appointments.length === 0 && docks.length === 0) return <PageSkeleton variant="table" label="Loading dock schedule"/>;

    return <UiMain className="w-full min-w-0 space-y-5 px-4 py-8 sm:px-6 lg:px-8">
        <UiHeader className="flex flex-wrap items-end justify-between gap-4">
            <UiBox><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet operations</UiText><UiH1 className="mt-1 text-2xl font-bold tracking-tight">Dock schedule</UiH1><UiText className="mt-1 max-w-2xl text-sm text-slate-500">Plan dock time, check trucks in, and keep loading progress in one clear view.</UiText></UiBox>
            <UiBox className="flex flex-wrap gap-2"><UiButton type="button" disabled={loading || Boolean(saving)} onClick={() => void load()} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm font-semibold"><RefreshCw size={15} className={loading ? "animate-spin" : ""}/>Refresh</UiButton><UiButton type="button" onClick={() => { setMessage(""); setDialog("dock"); }} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm font-semibold"><Warehouse size={15}/>Add dock</UiButton><UiButton type="button" onClick={() => { setMessage(""); setDialog("booking"); }} className="inline-flex items-center gap-2 rounded-lg bg-forest px-3.5 py-2.5 text-sm font-semibold text-white"><Plus size={16}/>Book dock time</UiButton></UiBox>
        </UiHeader>

        {message && <WorkflowFeedback message={message} onRefresh={() => void load()}/>}

        <UiSection aria-label="Dock schedule summary" className="grid gap-3 sm:grid-cols-3">
            {[
                { label: "Active appointments", value: activeAppointmentsCount, note: "Booked, arrived, or loading", icon: CalendarClock, tint: "bg-blue-50 text-blue-700" },
                { label: "Trucks on site", value: checkedInCount, note: "Checked in and not checked out", icon: Warehouse, tint: "bg-amber-50 text-amber-800" },
                { label: "Detention alerts", value: detentionRows.length, note: `Estimated exposure ₹${estimatedDetention.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, icon: CircleAlert, tint: detentionRows.length ? "bg-rose-50 text-rose-700" : "bg-slate-100 text-slate-500" },
            ].map(item => <UiArticle key={item.label} className="rounded-xl border border-line bg-white p-4"><UiBox className="flex items-center justify-between"><UiText className="text-xs font-medium text-slate-500">{item.label}</UiText><UiSpan className={`grid h-8 w-8 place-items-center rounded-lg ${item.tint}`}><item.icon size={16}/></UiSpan></UiBox><UiH2 className="mt-2 text-2xl font-bold tabular-nums">{loading ? "—" : item.value}</UiH2><UiText className="mt-1 text-xs text-slate-500">{item.note}</UiText></UiArticle>)}
        </UiSection>

        <UiSection className="overflow-hidden rounded-xl border border-line bg-white">
            <UiHeader className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4 sm:p-5"><UiBox><UiH2 className="text-sm font-bold">Appointments</UiH2><UiText className="mt-1 text-xs text-slate-500">{visibleAppointments.length} {visibleAppointments.length === 1 ? "appointment" : "appointments"}{search || statusFilter ? " match your filters" : " on the schedule"}</UiText></UiBox><UiBox className="flex w-full flex-wrap gap-2 sm:w-auto"><UiLabel className="relative min-w-52 flex-1 sm:flex-none"><span className="sr-only">Search appointments</span><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><UiInput className={`${input} pl-9`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search order, dock, customer" aria-label="Search appointments" maxLength={150}/></UiLabel><UiLabel className="flex items-center gap-2 text-xs font-semibold">Status<UiSelect className={input} value={statusFilter} onChange={event => setStatusFilter(event.target.value)} aria-label="Filter appointment status"><option value="">All</option>{["BOOKED", "ARRIVED", "LOADING", "COMPLETED", "CANCELLED"].map(status => <option key={status} value={status}>{appointmentStatus(status)}</option>)}</UiSelect></UiLabel></UiBox></UiHeader>
            {page.rows.length === 0 ? <UiBox className="p-10 text-center"><UiSpan className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-slate-100 text-slate-500"><CalendarClock size={19}/></UiSpan><UiH3 className="mt-3 text-sm font-semibold">{search || statusFilter ? "No matching appointments" : "No dock appointments yet"}</UiH3><UiText className="mx-auto mt-1 max-w-md text-sm text-slate-500">{search || statusFilter ? "Try a different search or clear the status filter." : docks.length ? "Book a time slot for an eligible transport order." : "Add a dock first, then book a time slot for a transport order."}</UiText>{search || statusFilter ? <UiButton type="button" onClick={() => { setSearch(""); setStatusFilter(""); }} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">Clear filters</UiButton> : <UiButton type="button" onClick={() => setDialog(docks.length ? "booking" : "dock")} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-forest px-3.5 py-2.5 text-sm font-semibold text-white"><Plus size={15}/>{docks.length ? "Book dock time" : "Add dock"}</UiButton>}</UiBox> : <>
                <UiBox className="divide-y divide-line">
                    {page.rows.map(row => <UiBox component="article" key={row.id} className="px-4 py-4 sm:px-5">
                        <UiBox className="grid gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(170px,.8fr)_minmax(190px,.8fr)_auto] lg:items-center">
                            <UiBox className="min-w-0"><UiBox className="flex flex-wrap items-center gap-2"><UiH3 className="text-sm font-bold">{row.order_number}</UiH3><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusClass(row.status)}`}>{appointmentStatus(row.status)}</UiSpan><UiSpan className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-600">{row.appointment_type === "PICKUP" ? "Pickup" : "Delivery"}</UiSpan></UiBox><UiText className="mt-1 text-sm font-medium text-slate-700">{row.origin} <span className="px-1 text-slate-300">→</span> {row.destination}</UiText><UiText className="mt-1 truncate text-xs text-slate-500">{row.customer} · {row.site_name} · {row.dock_name}</UiText></UiBox>
                            <UiBox><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Scheduled window</UiText><UiText className="mt-1 inline-flex items-center gap-1.5 text-xs text-slate-700"><Clock3 size={13} className="text-slate-400"/>{dateTime(row.starts_at)}</UiText><UiText className="mt-1 text-xs text-slate-500">Until {new Date(row.ends_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}</UiText></UiBox>
                            <UiBox><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Time on site</UiText>{row.wait_minutes === null ? <UiText className="mt-1 text-xs text-slate-500">Not checked in</UiText> : <><UiText className="mt-1 text-sm font-semibold text-slate-800">{row.wait_minutes} min</UiText><UiText className={`mt-1 text-[10px] ${row.chargeable_minutes > 0 ? "font-semibold text-amber-700" : "text-slate-500"}`}>{row.chargeable_minutes > 0 ? `${row.chargeable_minutes} min beyond free time · ₹${Number(row.detention_estimate).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} estimate` : `Within ${row.free_minutes} min free time`}</UiText></>}</UiBox>
                            <UiBox className="flex flex-wrap gap-2 lg:justify-end">{row.status === "BOOKED" && <><UiButton type="button" disabled={Boolean(saving)} onClick={() => void updateAppointment(row, "arrive")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">{saving === row.id ? "Updating…" : "Check in"}</UiButton><UiButton type="button" disabled={Boolean(saving)} onClick={() => void updateAppointment(row, "cancel")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold text-slate-600">Cancel</UiButton></>}{row.status === "ARRIVED" && <UiButton type="button" disabled={Boolean(saving)} onClick={() => void updateAppointment(row, "start")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">{saving === row.id ? "Updating…" : "Start loading"}</UiButton>}{row.status === "LOADING" && <UiButton type="button" disabled={Boolean(saving)} onClick={() => void updateAppointment(row, "complete")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">{saving === row.id ? "Updating…" : "Complete"}</UiButton>}{!["BOOKED", "ARRIVED", "LOADING"].includes(row.status) && <UiText className="text-xs text-slate-400">No action needed</UiText>}</UiBox>
                        </UiBox>
                        {(row.notes || row.delay_reason) && <UiBox className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-line pt-2 text-xs text-slate-500">{row.notes && <UiText>Note: {row.notes}</UiText>}{row.delay_reason && <UiText>Delay: {row.delay_reason}</UiText>}</UiBox>}
                    </UiBox>)}
                </UiBox>
                {page.controls}
            </>}
        </UiSection>

        <details className="overflow-hidden rounded-xl border border-line bg-white">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-4 sm:px-5"><UiBox><UiH2 className="text-sm font-bold">Detention evidence & billing</UiH2><UiText className="mt-1 text-xs text-slate-500">Record delay reasons, finish loading, and prepare a draft for trip approval.</UiText></UiBox><ArrowRight size={16} className="text-slate-400 transition open:rotate-90"/></summary>
            <UiBox className="border-t border-line bg-slate-50/50 p-4 sm:p-5">
                <UiText className="max-w-4xl text-xs leading-5 text-slate-600">Detention uses the free-time and rate terms captured at check-in. Draft charges need independent trip approval before customer billing; the estimate is operational evidence, not a confirmed receivable.</UiText>
                <UiBox className="mt-4 grid gap-3 md:grid-cols-[minmax(220px,.8fr)_minmax(220px,1.2fr)]"><UiLabel className="text-xs font-semibold">Appointment<UiSelect value={detentionAppointment} onChange={event => setDetentionAppointment(event.target.value)} className={`${input} mt-1`} aria-label="Select appointment for detention review"><option value="">Select appointment</option>{appointments.filter(row => ["ARRIVED", "LOADING", "COMPLETED"].includes(row.status)).map(row => <option key={row.id} value={row.id}>{row.order_number} · {row.dock_name} · {appointmentStatus(row.status)}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold">Delay reason / billing evidence<UiInput value={delayReason} onChange={event => setDelayReason(event.target.value)} placeholder="Describe the delay and evidence" maxLength={500} className={`${input} mt-1`}/></UiLabel></UiBox>
                {selectedDetention && <UiBox className="mt-3 rounded-lg border border-line bg-white p-3 text-xs text-slate-600"><UiText><UiStrong>Loading:</UiStrong> {selectedDetention.loading_started_at ? dateTime(selectedDetention.loading_started_at) : "Not started"} → {selectedDetention.loading_finished_at ? dateTime(selectedDetention.loading_finished_at) : "Not finished"}</UiText><UiText className="mt-1"><UiStrong>Waiting:</UiStrong> {selectedDetention.wait_minutes === null ? "Not checked in" : `${selectedDetention.wait_minutes} minutes · ${selectedDetention.chargeable_minutes} chargeable minutes`}</UiText>{selectedDetention.delay_reason && <UiText className="mt-1"><UiStrong>Saved reason:</UiStrong> {selectedDetention.delay_reason}</UiText>}</UiBox>}
                <UiBox className="mt-3 flex flex-wrap gap-2"><UiButton type="button" disabled={Boolean(saving) || !detentionAppointment || !delayReason.trim()} onClick={() => void detentionAction("reason")} className="rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold">{saving === "detention:reason" ? "Saving…" : "Save reason"}</UiButton><UiButton type="button" disabled={Boolean(saving) || selectedDetention?.status !== "LOADING" || Boolean(selectedDetention?.loading_finished_at)} onClick={() => void detentionAction("finish-loading")} className="rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold">{saving === "detention:finish-loading" ? "Saving…" : "Mark loading finished"}</UiButton><UiButton type="button" disabled={Boolean(saving) || selectedDetention?.status !== "COMPLETED" || !delayReason.trim() || Number(selectedDetention?.detention_estimate || 0) <= 0} onClick={() => void detentionAction("prepare-billing")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">{saving === "detention:prepare-billing" ? "Preparing…" : "Prepare draft for approval"}</UiButton></UiBox>
                {detentionRows.length > 0 && <UiText className="mt-3 text-xs text-amber-800">{detentionRows.length} appointment(s) are beyond recorded free time. Review the contract and evidence before preparing a draft.</UiText>}
            </UiBox>
        </details>

        <Dialog open={dialog === "dock"} onClose={() => !saving && setDialog(null)} fullWidth maxWidth="sm" aria-labelledby="add-dock-title"><UiForm onSubmit={createDock}>
            <DialogTitle id="add-dock-title" sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}><UiBox><UiH2 className="text-lg font-bold">Add dock</UiH2><UiText className="mt-1 text-xs font-normal text-slate-500">Create a bookable bay at a warehouse or site.</UiText></UiBox><UiButton type="button" aria-label="Close add dock" onClick={() => !saving && setDialog(null)} disabled={Boolean(saving)} className="min-w-0 p-2 text-slate-500"><X size={17}/></UiButton></DialogTitle>
            <DialogContent dividers><UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="text-xs font-semibold sm:col-span-2">Warehouse / site<UiInput name="site_name" required maxLength={160} className={`${input} mt-1`} placeholder="e.g. Mumbai North Hub"/></UiLabel><UiLabel className="text-xs font-semibold">Dock code<UiInput name="code" required maxLength={40} className={`${input} mt-1`} placeholder="D-01"/></UiLabel><UiLabel className="text-xs font-semibold">Dock name<UiInput name="name" required maxLength={120} className={`${input} mt-1`} placeholder="Main loading bay"/></UiLabel><UiLabel className="text-xs font-semibold">Parallel truck capacity<UiInput name="parallel_capacity" required type="number" min="1" max="100" defaultValue="1" className={`${input} mt-1`}/></UiLabel></UiBox></DialogContent>
            <DialogActions sx={{ p: 2, gap: 1 }}><UiButton type="button" onClick={() => setDialog(null)} disabled={Boolean(saving)} className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">Cancel</UiButton><UiButton type="submit" disabled={Boolean(saving)} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">{saving === "dock" ? "Adding…" : "Add dock"}</UiButton></DialogActions>
        </UiForm></Dialog>

        <Dialog open={dialog === "booking"} onClose={() => !saving && setDialog(null)} fullWidth maxWidth="md" aria-labelledby="book-dock-title"><UiForm onSubmit={bookAppointment}>
            <DialogTitle id="book-dock-title" sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}><UiBox><UiH2 className="text-lg font-bold">Book dock time</UiH2><UiText className="mt-1 text-xs font-normal text-slate-500">The system checks order eligibility and dock capacity before confirming the slot.</UiText></UiBox><UiButton type="button" aria-label="Close booking" onClick={() => !saving && setDialog(null)} disabled={Boolean(saving)} className="min-w-0 p-2 text-slate-500"><X size={17}/></UiButton></DialogTitle>
            <DialogContent dividers>{docks.length === 0 ? <UiBox className="rounded-lg border border-amber-200 bg-amber-50 p-4"><UiText className="text-sm font-semibold text-amber-900">There are no active docks yet.</UiText><UiText className="mt-1 text-xs text-amber-800">Add a dock first, then return here to book a time slot.</UiText><UiButton type="button" onClick={() => setDialog("dock")} className="mt-3 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-semibold">Add dock</UiButton></UiBox> : <UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="text-xs font-semibold">Dock<UiSelect name="dock_id" required defaultValue="" className={`${input} mt-1`}><option value="" disabled>Select dock</option>{docks.map(dock => <option key={dock.id} value={dock.id}>{dock.site_name} · {dock.code} · {dock.name} · capacity {dock.parallel_capacity}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs font-semibold">Appointment type<UiSelect name="appointment_type" value={appointmentType} onChange={event => setAppointmentType(event.target.value as AppointmentType)} className={`${input} mt-1`}><option value="PICKUP">Pickup</option><option value="DELIVERY">Delivery</option></UiSelect></UiLabel><UiLabel className="text-xs font-semibold sm:col-span-2">Eligible order<UiSelect name="order_id" required defaultValue="" className={`${input} mt-1`}><option value="" disabled>Select order</option>{schedulableOrders.map(order => <option key={order.id} value={order.id}>{order.order_number} · {order.customer.name} · {order.status}</option>)}</UiSelect><UiText className="mt-1 block text-[10px] font-normal text-slate-500">{appointmentType === "PICKUP" ? "Pickups can be booked for open or assigned orders." : "Deliveries can be booked for in-transit orders."}</UiText></UiLabel><UiLabel className="text-xs font-semibold">Start time<DateTimeInput value={startsAt} onChange={setStartsAt}/></UiLabel><UiLabel className="text-xs font-semibold">End time<DateTimeInput value={endsAt} onChange={setEndsAt}/></UiLabel><UiLabel className="text-xs font-semibold sm:col-span-2">Handling notes<UiTextarea name="notes" maxLength={500} rows={2} className={`${input} mt-1`} placeholder="Optional instructions for the dock team"/></UiLabel></UiBox>}</DialogContent>
            <DialogActions sx={{ p: 2, gap: 1 }}><UiButton type="button" onClick={() => setDialog(null)} disabled={Boolean(saving)} className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">Cancel</UiButton>{docks.length > 0 && <UiButton type="submit" disabled={Boolean(saving) || !schedulableOrders.length} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">{saving === "booking" ? "Booking…" : "Confirm booking"}</UiButton>}</DialogActions>
        </UiForm></Dialog>
    </UiMain>;
}

function DateTimeInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
    return <UiInput type="datetime-local" required value={value} onChange={event => onChange(event.target.value)} className={`${input} mt-1`}/>;
}
