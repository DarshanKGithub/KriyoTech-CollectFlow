"use client";
import { ProcessingStatus } from "@/components/processing-status";
import { DriverMobileNavigation, DriverProfile, type DriverTab } from "@/components/driver-mobile-navigation";
import { PageSkeleton } from "@/components/content-skeleton";
import { EmptyState } from "@/components/empty-state";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { TripProgress } from "@/components/workflow-progress";
import { UiArticle, UiBox, UiButton, UiDetails, UiForm, UiH1, UiH2, UiH3, UiHeader, UiInput, UiLabel, UiMain, UiSelect, UiSmall, UiSpan, UiStrong, UiSummary, UiText, UiTextarea } from "@/components/product-ui";
import { requestInput } from "@/components/product-dialogs";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Trip = {
    id: string;
    trip_number: string;
    vehicle: {
        registration_number: string;
    };
    driver: {
        name: string;
    };
    origin: string;
    destination: string;
    starts_at: string | null;
    odometer_start: string | null;
    odometer_end: string | null;
    pickup_at: string | null;
    loaded_at: string | null;
    delivery_at: string | null;
    delivery_proof_name: string | null;
    delivery_signature_name: string;
    status: string;
    review_note: string;
    stops: { id: string; sequence: number; order_number: string; kind: string; address: string; status: string; planned_at: string | null; actual_at?: string | null }[];
    expense_lines: {
        id: string;
        category: string;
        description: string;
        amount: string;
        receipt_name: string | null;
        status: string;
    }[];
};
type GpsStatus = { state: "REQUESTING" | "SHARING" | "ERROR" | "OFFLINE"; message: string; lastSentAt?: string; accuracy?: number };
const input = "w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-base outline-none focus:border-emerald-700";
export default function DriverPhonePage() {
    const [driverTab, setDriverTab] = useState<DriverTab>("trips");
    const [initialLoading, setInitialLoading] = useState(true);
    const [trips, setTrips] = useState<Trip[]>([]);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState("");
    const [pendingCount, setPendingCount] = useState(0);
    const [gpsStatus, setGpsStatus] = useState<Record<string, GpsStatus>>({});
    function getQueue(): {
        path: string;
        body: Record<string, unknown>;
        label: string;
    }[] {
        try {
            return JSON.parse(localStorage.getItem("kriyopay_driver_offline_queue") || "[]");
        }
        catch {
            return [];
        }
    }
    async function queueOffline(path: string, body: Record<string, unknown>, label: string, file?: File | null) {
        if (file?.size && file.size <= 1500000) {
            try {
                const dataUrl = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(reader.error); reader.readAsDataURL(file); });
                body = { ...body, _offline_file: dataUrl, _offline_filename: file.name };
            }
            catch {
                label += " (file could not be saved offline)";
            }
        }
        else if (file?.size)
            label += " (file is too large to save offline; attach it after sync)";
        const queue = getQueue();
        if (!queue.some(item => item.path === path && JSON.stringify(item.body) === JSON.stringify(body)))
            queue.push({ path, body, label });
        try {
            localStorage.setItem("kriyopay_driver_offline_queue", JSON.stringify(queue));
            setPendingCount(queue.length);
            const actionName = path.split("/").pop();
            setTrips(current => {
                const updated = current.map(trip => {
                    if (!path.includes(`/${trip.id}/`))
                        return trip;
                    if (actionName === "start")
                        return { ...trip, status: "IN_PROGRESS", pickup_at: new Date().toISOString(), odometer_start: String(body.odometer_start || trip.odometer_start || "") || null };
                    if (actionName === "load")
                        return { ...trip, loaded_at: new Date().toISOString() };
                    if (actionName === "complete")
                        return { ...trip, status: "COMPLETED", delivery_at: new Date().toISOString(), odometer_end: String(body.odometer_end || "") || null, delivery_signature_name: String(body.delivery_signature_name || trip.delivery_signature_name), delivery_proof_name: file?.name || trip.delivery_proof_name };
                    if (actionName === "submit")
                        return { ...trip, status: "SUBMITTED" };
                    if (actionName === "expenses")
                        return { ...trip, expense_lines: [...trip.expense_lines, { id: `offline:${crypto.randomUUID()}`, category: String(body.category || "Other"), description: String(body.description || "Pending offline expense"), amount: String(body.amount || "0"), receipt_name: file?.name || null, status: "PENDING" }] };
                    return trip;
                });
                localStorage.setItem("kriyopay_driver_trip_cache", JSON.stringify(updated));
                return updated;
            });
            setNotice(`${label} saved on this device. It will sync when you’re back online.`);
        }
        catch {
            setError("This update could not be saved offline because device storage is full.");
        }
    }
    const refresh = useCallback(async () => {
        try {
            const response = await apiFetch("/fleet/my-trips");
            const body = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(body?.error || body?.detail || "Could not load your trips.");
            setTrips(body);
            localStorage.setItem("kriyopay_driver_trip_cache", JSON.stringify(body));
        }
        catch (error) {
            const cached = localStorage.getItem("kriyopay_driver_trip_cache");
            if (!navigator.onLine && cached) {
                setTrips(JSON.parse(cached));
                return;
            }
            throw error;
        }
    }, []);
    const syncPending = useCallback(async () => {
        const queue = getQueue();
        if (!queue.length || !navigator.onLine)
            return;
        const remaining = [];
        for (const item of queue) {
            try {
                const body = { ...item.body };
                if (typeof body._offline_file === "string") {
                    const [header, encoded] = body._offline_file.split(",");
                    const mime = header.match(/data:(.*?);base64/)?.[1] || "application/octet-stream";
                    const binary = atob(encoded);
                    const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
                    const upload = new FormData();
                    upload.set("file", new File([new Blob([bytes], { type: mime })], String(body._offline_filename || "driver-upload"), { type: mime }));
                    const uploaded = await apiFetch("/fleet/documents", { method: "POST", body: upload });
                    const document = await uploaded.json().catch(() => null);
                    if (!uploaded.ok) {
                        remaining.push(item);
                        continue;
                    }
                    body[item.path.endsWith("/complete") ? "delivery_proof_id" : "receipt_id"] = document.id;
                    delete body._offline_file;
                    delete body._offline_filename;
                }
                const response = await apiFetch(item.path, { method: "POST", body: JSON.stringify(body) });
                if (!response.ok)
                    remaining.push(item);
            }
            catch {
                remaining.push(item);
            }
        }
        localStorage.setItem("kriyopay_driver_offline_queue", JSON.stringify(remaining));
        setPendingCount(remaining.length);
        if (queue.length > remaining.length) {
            setNotice(`${queue.length - remaining.length} offline update(s) synced.`);
            await refresh();
        }
    }, [refresh]);
    useEffect(() => { setPendingCount(getQueue().length); void refresh().catch(e => setError(e instanceof Error ? e.message : "Could not load trips.")).finally(()=>setInitialLoading(false)); const online = () => void syncPending(); window.addEventListener("online", online); return () => window.removeEventListener("online", online); }, [refresh, syncPending]);
    useEffect(() => {
        const timers: number[] = [];
        const stopTrackers: Array<() => void> = [];
        const activeTrips = trips.filter(trip => trip.status === "IN_PROGRESS");
        for (const trip of activeTrips) {
            if (!navigator.geolocation) {
                setGpsStatus(current => ({ ...current, [trip.id]: { state: "ERROR", message: "This browser does not support phone location." } }));
                continue;
            }
            let sending = false;
            let disposed = false;
            let stopped = false;
            const capture = () => {
                if (disposed || stopped || sending) return;
                if (!navigator.onLine) {
                    setGpsStatus(current => ({ ...current, [trip.id]: { state: "OFFLINE", message: "Waiting for internet; location is not being saved on this phone." } }));
                    return;
                }
                sending = true;
                setGpsStatus(current => current[trip.id]?.state === "SHARING" ? current : ({ ...current, [trip.id]: { state: "REQUESTING", message: "Getting phone location…" } }));
                navigator.geolocation.getCurrentPosition(async position => {
                    try {
                        const response = await apiFetch(`/fleet/trips/${trip.id}/location`, { method: "POST", body: JSON.stringify({
                            latitude: position.coords.latitude, longitude: position.coords.longitude,
                            accuracy_m: position.coords.accuracy, speed_mps: position.coords.speed,
                            heading_degrees: position.coords.heading, captured_at: new Date(position.timestamp).toISOString(),
                            client_event_id: crypto.randomUUID(),
                        }) });
                        const body = await response.json().catch(() => null);
                        if (!response.ok) {
                            const message = body?.error || body?.detail || "Could not send phone location.";
                            if (response.status === 409) {
                                stopped = true;
                                if (!disposed) setGpsStatus(current => ({ ...current, [trip.id]: { state: "ERROR", message: "This trip is no longer active. Phone GPS sharing has stopped." } }));
                                return;
                            }
                            throw new Error(message);
                        }
                        if (!disposed) setGpsStatus(current => ({ ...current, [trip.id]: { state: "SHARING", message: "Live location is being shared with dispatch.", lastSentAt: body?.captured_at || new Date(position.timestamp).toISOString(), accuracy: position.coords.accuracy } }));
                    } catch (e) {
                        if (!disposed) setGpsStatus(current => ({ ...current, [trip.id]: { state: "ERROR", message: e instanceof Error ? e.message : "Could not send phone location." } }));
                    } finally { sending = false; }
                }, error => {
                    if (!disposed) setGpsStatus(current => ({ ...current, [trip.id]: { state: "ERROR", message: error.code === error.PERMISSION_DENIED ? "Allow location access and open KriyoPay over HTTPS on your phone to share trip GPS." : error.code === error.TIMEOUT ? "Phone GPS timed out. KriyoPay will try again." : "Phone location is unavailable. Turn on Location Services and retry." } }));
                    sending = false;
                }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
            };
            setGpsStatus(current => ({ ...current, [trip.id]: { state: "REQUESTING", message: "Requesting phone location permission…" } }));
            capture();
            timers.push(window.setInterval(capture, 30000));
            stopTrackers.push(() => { disposed = true; });
        }
        return () => {
            timers.forEach(window.clearInterval);
            stopTrackers.forEach(stop => stop());
        };
    }, [trips]);
    async function action(trip: Trip, name: "start" | "load" | "complete" | "submit") {
        let odometer_end: string | undefined;
        let odometer_start: string | undefined;
        if (name === "start") {
            const value = (await requestInput("Enter the pickup odometer reading (optional):"));
            if (value === null)
                return;
            odometer_start = value.trim() || undefined;
            if (odometer_start && (!Number.isFinite(Number(odometer_start)) || Number(odometer_start) < 0)) {
                setError("Enter a valid starting odometer reading.");
                return;
            }
        }
        setBusy(`${trip.id}:${name}`);
        setError("");
        try {
            const requestPayload = { ...(odometer_end ? { odometer_end } : {}), ...(odometer_start ? { odometer_start } : {}) };
            const response = await apiFetch(`/fleet/trips/${trip.id}/${name}`, { method: "POST", body: JSON.stringify(requestPayload) });
            const body = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(body?.error?.message || body?.error || "Trip update failed.");
            await refresh();
            setNotice(name === "start" ? "Pickup check-in recorded." : name === "load" ? "Load confirmation recorded." : name === "complete" ? "Trip completed." : "Trip sent for review.");
        }
        catch (e) {
            if (!navigator.onLine)
                queueOffline(`/fleet/trips/${trip.id}/${name}`, { ...(odometer_start ? { odometer_start } : {}) }, name === "start" ? "Pickup check-in" : name === "load" ? "Load confirmation" : "Trip update");
            else
                setError(e instanceof Error ? e.message : "Trip update failed.");
        }
        finally {
            setBusy("");
        }
    }
    async function stopAction(trip: Trip, stop: Trip["stops"][number], name: "arrive" | "complete") {
        setBusy(`${trip.id}:stop:${stop.id}`); setError("");
        try {
            const response = await apiFetch(`/fleet/trips/${trip.id}/stops/${stop.id}/${name}`, { method: "POST", body: "{}" });
            const body = await response.json().catch(() => null);
            if (!response.ok) throw new Error(body?.error?.message || body?.error || "Could not update the route stop.");
            await refresh(); setNotice(name === "arrive" ? `Arrived at ${stop.kind.toLowerCase()} stop.` : `${stop.kind === "PICKUP" ? "Pickup" : "Delivery"} stop completed.`);
        } catch (e) { setError(e instanceof Error ? e.message : "Could not update the route stop."); }
        finally { setBusy(""); }
    }
    async function completeTrip(event: FormEvent<HTMLFormElement>, trip: Trip) {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        const odometer_end = String(values.get("odometer_end") || "").trim();
        const delivery_signature_name = String(values.get("signature") || "").trim();
        const file = values.get("proof");
        if (odometer_end && (!Number.isFinite(Number(odometer_end)) || Number(odometer_end) < 0)) {
            setError("Enter a valid ending odometer reading.");
            return;
        }
        setBusy(`${trip.id}:complete`);
        setError("");
        try {
            let delivery_proof_id: string | undefined;
            if (file instanceof File && file.size) {
                const upload = new FormData();
                upload.set("file", file);
                const uploaded = await apiFetch("/fleet/documents", { method: "POST", body: upload });
                const doc = await uploaded.json().catch(() => null);
                if (!uploaded.ok)
                    throw new Error(doc?.error || "Delivery proof upload failed.");
                delivery_proof_id = doc.id;
            }
            if (!delivery_signature_name && !delivery_proof_id) {
                setError("Add a recipient name or delivery photo/document as proof.");
                return;
            }
            const payload = { ...(odometer_end ? { odometer_end } : {}), ...(delivery_signature_name ? { delivery_signature_name } : {}), ...(delivery_proof_id ? { delivery_proof_id } : {}) };
            const response = await apiFetch(`/fleet/trips/${trip.id}/complete`, { method: "POST", body: JSON.stringify(payload) });
            const result = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(result?.error?.message || result?.error || "Could not complete trip.");
            await refresh();
            setNotice("Delivery time and proof recorded.");
        }
        catch (e) {
            if (!navigator.onLine)
                void queueOffline(`/fleet/trips/${trip.id}/complete`, { ...(odometer_end ? { odometer_end } : {}), ...(delivery_signature_name ? { delivery_signature_name } : {}) }, "Delivery check-out", file instanceof File ? file : null);
            else
                setError(e instanceof Error ? e.message : "Could not complete trip.");
        }
        finally {
            setBusy("");
        }
    }
    async function reportTripIssue(event: FormEvent<HTMLFormElement>, trip: Trip) {
        event.preventDefault();
        const form = event.currentTarget;
        const values = new FormData(form);
        setBusy(`${trip.id}:issue`);
        setError("");
        try {
            const response = await apiFetch("/fleet/follow-ups", { method: "POST", body: JSON.stringify({ trip_id: trip.id, category: `DRIVER_${values.get("category")}`, description: values.get("description") }) });
            const result = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(result?.error?.message || result?.error || "Could not report this issue.");
            form.reset();
            setNotice("Issue sent to the dispatch team.");
        }
        catch (e) {
            setError(e instanceof Error ? e.message : "Could not report this issue.");
        }
        finally {
            setBusy("");
        }
    }
    async function addExpense(event: FormEvent<HTMLFormElement>, trip: Trip) {
        event.preventDefault();
        const form = event.currentTarget;
        const values = new FormData(form);
        const file = values.get("receipt");
        setBusy(`${trip.id}:expense`);
        setError("");
        try {
            let receipt_id: string | undefined;
            if (file instanceof File && file.size) {
                const upload = new FormData();
                upload.set("file", file);
                const uploaded = await apiFetch("/fleet/documents", { method: "POST", body: upload });
                const doc = await uploaded.json().catch(() => null);
                if (!uploaded.ok)
                    throw new Error(doc?.error || "Receipt upload failed.");
                receipt_id = doc.id;
            }
            let key = sessionStorage.getItem(`fleet-expense:${trip.id}`);
            if (!key) {
                key = crypto.randomUUID();
                sessionStorage.setItem(`fleet-expense:${trip.id}`, key);
            }
            const payload = { category: values.get("category"), description: values.get("description"), amount: values.get("amount"), incurred_at: values.get("incurred_at"), paid_by_driver: true, ...(values.get("quantity_litres") ? { quantity_litres: values.get("quantity_litres") } : {}), idempotency_key: key, ...(receipt_id ? { receipt_id } : {}) };
            const response = await apiFetch(`/fleet/trips/${trip.id}/expenses`, { method: "POST", body: JSON.stringify(payload) });
            const body = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(body?.error?.message || body?.error || "Could not save expense.");
            sessionStorage.removeItem(`fleet-expense:${trip.id}`);
            form.reset();
            await refresh();
            setNotice("Expense and receipt submitted.");
        }
        catch (e) {
            if (!navigator.onLine) {
                let key = sessionStorage.getItem(`fleet-expense:${trip.id}`);
                if (!key) {
                    key = crypto.randomUUID();
                    sessionStorage.setItem(`fleet-expense:${trip.id}`, key);
                }
                void queueOffline(`/fleet/trips/${trip.id}/expenses`, { category: values.get("category"), description: values.get("description"), amount: values.get("amount"), incurred_at: values.get("incurred_at"), paid_by_driver: true, ...(values.get("quantity_litres") ? { quantity_litres: values.get("quantity_litres") } : {}), idempotency_key: key }, "Trip expense", file instanceof File ? file : null);
            }
            else
                setError(e instanceof Error ? e.message : "Could not save expense.");
        }
        finally {
            setBusy("");
        }
    }
    if(initialLoading)return <PageSkeleton variant="cards" label="Loading your trips"/>;
    return <UiBox sx={{"& [data-driver-tab=checkin] [data-driver-section=receipts]":{display:"none"},"& [data-driver-tab=receipts] [data-driver-section=checkin]":{display:"none"}}}><UiMain data-driver-tab={driverTab} style={{paddingBottom:100}} className="w-full min-w-0 min-h-screen bg-slate-50 px-4 py-6 sm:px-6">
    <UiHeader className="mb-5"><UiText className="text-xs font-bold uppercase tracking-widest text-emerald-800">KriyoPay · Driver</UiText><UiH1 className="mt-1 text-2xl font-bold text-slate-950">{driverTab === "profile" ? "My profile" : driverTab === "checkin" ? "Trip check-in" : driverTab === "receipts" ? "Expenses & receipts" : "My trips"}</UiH1><UiText className="mt-1 text-sm text-slate-600">Update trip progress and send expenses with receipt photos.</UiText></UiHeader>
    {busy && <ProcessingStatus status="PROCESSING" label="Saving driver update"/>}
    {pendingCount > 0 && <UiButton onClick={() => void syncPending()} className="mb-4 w-full rounded-xl border border-amber-300 bg-amber-50 p-3 text-left text-sm font-semibold text-amber-900">{pendingCount} update(s) waiting to sync · Sync now</UiButton>}{error && <WorkflowFeedback message={error} onRefresh={()=>refresh()} />}{notice && <WorkflowFeedback message={notice}/>}
    {driverTab === "profile" && <DriverProfile/>}<UiBox style={{display:driverTab === "profile" ? "none" : undefined}} className="space-y-4">{trips.map(trip => <UiArticle key={trip.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><TripProgress pickup={Boolean(trip.pickup_at)} loaded={Boolean(trip.loaded_at)} delivered={Boolean(trip.delivery_at)}/>
      <UiBox className="flex items-start justify-between gap-3"><UiBox><UiH2 className="text-lg font-bold">{trip.trip_number}</UiH2><UiText className="text-sm text-slate-500">{trip.vehicle.registration_number}</UiText></UiBox><UiSpan className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold">{trip.status.replaceAll("_", " ")}</UiSpan></UiBox>
      <UiText className="mt-3 text-sm font-medium">{trip.origin || "Origin"} <UiSpan className="text-slate-400">→</UiSpan> {trip.destination || "Destination"}</UiText>
      {!!trip.stops?.length && <UiBox className="mt-4 space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3"><UiH3 className="text-sm font-semibold">Planned route stops</UiH3>{trip.stops.map(stop => <UiBox key={stop.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white p-3"><UiText className="min-w-0 text-sm"><UiStrong>{String(stop.sequence).padStart(2, "0")} · {stop.kind}</UiStrong><UiSmall className="block text-slate-600">{stop.order_number} · {stop.address}</UiSmall><UiSmall className="block text-slate-500">{stop.status.replaceAll("_", " ")}{stop.planned_at ? ` · planned ${new Date(stop.planned_at).toLocaleTimeString()}` : ""}</UiSmall></UiText>{trip.status === "IN_PROGRESS" && stop.status !== "COMPLETED" && stop.status !== "SKIPPED" && <UiButton disabled={!!busy} onClick={() => void stopAction(trip, stop, stop.status === "PLANNED" ? "arrive" : "complete")} className="min-h-10 rounded-lg border border-emerald-800 px-3 text-sm font-semibold text-emerald-900">{busy === `${trip.id}:stop:${stop.id}` ? "Saving…" : stop.status === "PLANNED" ? "Mark arrived" : `Complete ${stop.kind.toLowerCase()}`}</UiButton>}</UiBox>)}</UiBox>}
      {trip.pickup_at && <UiText className="mt-2 text-xs text-slate-500">Pickup check-in · {new Date(trip.pickup_at).toLocaleString()}</UiText>}{trip.loaded_at && <UiText className="mt-1 text-xs font-medium text-emerald-800">Load confirmed · {new Date(trip.loaded_at).toLocaleString()}</UiText>}{trip.status === "IN_PROGRESS" && <UiBox role="status" className="mt-3 rounded-xl border border-sky-200 bg-sky-50 p-3"><UiText className="text-xs font-semibold text-sky-950">Phone GPS · {gpsStatus[trip.id]?.state === "SHARING" ? "Sharing live location" : gpsStatus[trip.id]?.state === "ERROR" ? "Needs attention" : gpsStatus[trip.id]?.state === "OFFLINE" ? "Offline" : "Starting"}</UiText><UiText className="mt-1 text-xs text-sky-900">{gpsStatus[trip.id]?.message || "KriyoPay will request phone location and send an update every 30 seconds while this trip is active."}</UiText>{gpsStatus[trip.id]?.lastSentAt && <UiText className="mt-1 text-[11px] text-sky-800">Last sent {new Date(gpsStatus[trip.id].lastSentAt!).toLocaleTimeString()}{gpsStatus[trip.id]?.accuracy ? ` · Accuracy ±${Math.round(gpsStatus[trip.id].accuracy!)} m` : ""}</UiText>}<UiText className="mt-1 text-[10px] text-sky-700">Sharing stops when you complete the trip or close this driver page. On a phone, open KriyoPay over HTTPS and allow location access.</UiText></UiBox>}
      {trip.review_note && <UiText className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{trip.review_note}</UiText>}
      <UiDetails data-driver-section="checkin" className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3"><UiSummary className="cursor-pointer text-sm font-semibold text-amber-950">Report a trip issue</UiSummary><UiForm onSubmit={event => void reportTripIssue(event, trip)} className="mt-3 space-y-2"><UiSelect name="category" className={input}><option value="DELAY">Delay</option><option value="CUSTOMER_UNAVAILABLE">Customer unavailable</option><option value="VEHICLE_ISSUE">Vehicle problem</option><option value="CARGO_ISSUE">Cargo problem</option><option value="ROUTE_ISSUE">Route problem</option><option value="OTHER">Other</option></UiSelect><UiTextarea name="description" required maxLength={240} placeholder="Describe what happened and what help you need" className={input}/><UiButton disabled={!!busy} className="min-h-11 rounded-lg bg-amber-900 px-4 text-sm font-semibold text-white disabled:opacity-60">{busy === `${trip.id}:issue` ? "Sending…" : "Send issue to dispatch"}</UiButton></UiForm></UiDetails>
      {trip.expense_lines.length > 0 && <UiBox data-driver-section="receipts" className="mt-3 space-y-2 border-t pt-3">{trip.expense_lines.map(line => <UiText key={line.id} className="flex justify-between gap-2 text-sm"><UiSpan>{line.category}: {line.description}<UiSmall className="block text-slate-500">{line.receipt_name || "Receipt not attached"} · {line.status.toLowerCase()}</UiSmall></UiSpan><UiStrong>₹{line.amount}</UiStrong></UiText>)}</UiBox>}
      <UiBox data-driver-section="checkin" className="mt-4 grid grid-cols-1 gap-2">{trip.status === "DRAFT" && <UiButton disabled={!!busy} onClick={() => void action(trip, "start")} className="min-h-12 rounded-xl bg-emerald-800 px-4 font-semibold text-white disabled:opacity-60">{busy === `${trip.id}:start` ? "Saving…" : "Start trip"}</UiButton>}{trip.status === "IN_PROGRESS" && <>{!trip.stops?.length && !trip.loaded_at && <UiButton disabled={!!busy} onClick={() => void action(trip, "load")} className="min-h-12 rounded-xl border border-emerald-800 px-4 font-semibold text-emerald-900 disabled:opacity-60">{busy === `${trip.id}:load` ? "Saving…" : "Confirm load is on the truck"}</UiButton>}<UiForm data-driver-section="checkin" onSubmit={event => void completeTrip(event, trip)} className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3"><UiH3 className="font-semibold">Delivery check-out</UiH3><UiInput name="odometer_end" type="number" min="0" step="0.1" placeholder="Ending odometer (optional)" className={input}/><UiInput name="signature" maxLength={160} placeholder="Recipient name / signature" className={input}/><UiLabel className="block text-sm">Delivery photo, signed document, or POD<UiInput name="proof" type="file" accept="application/pdf,image/jpeg,image/png,image/heic" className="mt-2 block w-full text-sm"/></UiLabel><UiButton disabled={!!busy} className="min-h-12 w-full rounded-xl bg-emerald-800 px-4 font-semibold text-white disabled:opacity-60">{busy === `${trip.id}:complete` ? "Saving delivery…" : "Record trip delivery"}</UiButton></UiForm></>}{["COMPLETED", "REJECTED"].includes(trip.status) && <UiButton disabled={!!busy} onClick={() => void action(trip, "submit")} className="min-h-12 rounded-xl bg-emerald-800 px-4 font-semibold text-white disabled:opacity-60">Send for review</UiButton>}</UiBox>
      {["DRAFT", "IN_PROGRESS", "COMPLETED", "REJECTED"].includes(trip.status) && <UiForm data-driver-section="receipts" onSubmit={event => void addExpense(event, trip)} className="mt-4 space-y-3 border-t pt-4"><UiH3 className="font-semibold">Add a trip expense</UiH3><UiSelect name="category" required className={input}><option value="FUEL">Fuel</option><option value="TOLL">Toll / FASTag</option><option value="LOADING">Loading / unloading</option><option value="ALLOWANCE">Food / allowance</option><option value="PERMIT">Permit</option><option value="REPAIR">Repair / maintenance</option><option value="PARKING">Parking</option><option value="OTHER">Other</option></UiSelect><UiInput name="description" required maxLength={200} placeholder="What was this expense for?" className={input}/><UiInput name="amount" required type="number" min="0.01" step="0.01" placeholder="Amount (₹)" className={input}/><UiInput name="quantity_litres" type="number" min="0.01" step="0.01" placeholder="Fuel quantity (litres, optional)" className={input}/><UiInput name="incurred_at" type="date" className={input}/><UiLabel className="block text-sm font-medium">Receipt photo or file<UiInput name="receipt" type="file" accept="application/pdf,image/jpeg,image/png,image/heic" className="mt-2 block w-full text-sm"/></UiLabel><UiButton disabled={!!busy} className="min-h-12 w-full rounded-xl border border-emerald-800 font-semibold text-emerald-900 disabled:opacity-60">{busy === `${trip.id}:expense` ? "Saving…" : "Add expense"}</UiButton></UiForm>}
    </UiArticle>)}{trips.length === 0 && !error && <EmptyState description="No trips are assigned to your account yet." onAction={()=>void refresh()} actionLabel="Refresh data" />}</UiBox>
  <DriverMobileNavigation value={driverTab} onChange={setDriverTab}/></UiMain></UiBox>;
}
