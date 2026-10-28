"use client";
import { QuickDetails } from "@/components/quick-details";
import { CollectionExplorer } from "@/components/collection-explorer";
import { applyFieldErrors } from "@/components/form-validation";
import { EmptyState } from "@/components/empty-state";
import { PageSkeleton } from "@/components/content-skeleton";
import { TripProgress } from "@/components/workflow-progress";
import { UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { requestInput } from "@/components/product-dialogs";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { apiFetch } from "@/lib/api";
type Vehicle = {
    id: string;
    registration_number: string;
    status: string;
};
type Driver = {
    id: string;
    name: string;
    status: string;
    account_email?: string | null;
};
type TransportOrder = {
    id: string;
    order_number: string;
    customer: {
        id: string;
        name: string;
    };
    origin: string;
    destination: string;
    agreed_amount: string | null;
    status: string;
};
type Member = {
    id: string;
    email: string;
    name: string;
    role: string;
    is_active: boolean;
};
type Line = {
    id: string;
    description: string;
    amount: string;
    budgeted_amount?: string | null;
    category?: string;
    status: string;
    receipt_name?: string | null;
};
type Trip = {
    id: string;
    trip_number: string;
    vehicle: {
        id: string;
        registration_number: string;
    };
    driver: {
        id: string;
        name: string;
    };
    transport_order: {
        id: string;
        order_number: string;
        customer_name: string;
    } | null;
    origin: string;
    destination: string;
    starts_at: string | null;
    ends_at: string | null;
    pickup_at: string | null;
    loaded_at: string | null;
    delivery_at: string | null;
    predicted_arrival_at: string | null;
    eta_error_minutes: number | null;
    odometer_start: string | null;
    odometer_end: string | null;
    status: string;
    revenue_total: string;
    expense_total: string;
    margin: string | null;
    revenue_lines: Line[];
    expense_lines: Line[];
    review_note: string;
};
type Dashboard = {
    active_vehicles: number;
    active_drivers: number;
    trips_in_progress: number;
    trips_awaiting_review: number;
    open_follow_ups: number;
    approved_trip_margin: string;
    driver_salary_remaining: string;
};
type FollowUp = {
    id: string;
    category: string;
    description: string;
    due_at: string | null;
    status: string;
    resolution_note: string;
};
type SalaryRecord = {
    id: string;
    driver: {
        id: string;
        name: string;
    };
    period_start: string;
    salary_amount: string;
    paid_amount: string;
    remaining_amount: string;
    notes: string;
    payments: {
        id: string;
        amount: string;
        payment_date: string;
        payment_reference: string;
        notes: string;
    }[];
};
type TripFilters = {
    search: string;
    status: string;
    vehicle_id: string;
    driver_id: string;
    date_from: string;
    date_to: string;
};
type ReportGroup = {
    id: string;
    name: string;
    trips: number;
    income: string;
    costs: string;
    margin: string;
};
type CostCategoryReport = {
    id: string;
    name: string;
    trips: number;
    actual: string;
    budgeted: string;
    over_budget: string;
};
type TripReport = {
    trip_count: number;
    income: string;
    costs: string;
    margin: string;
    budget_overrun_total: string;
    by_driver: ReportGroup[];
    by_truck: ReportGroup[];
    by_month: ReportGroup[];
    by_cost_category: CostCategoryReport[];
};
type FleetAlert = {
    id: string;
    kind: string;
    trip_id: string;
    trip_number: string;
    message: string;
    amount: string;
};
const inputClass = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const cardClass = "rounded-xl border border-line bg-white p-5 shadow-sm";
const openStatuses = ["OPEN", "IN_PROGRESS"];
const tripStatusLabel: Record<string, string> = { DRAFT: "Draft", IN_PROGRESS: "In progress", COMPLETED: "Completed · ready to review", SUBMITTED: "Waiting for review", APPROVED: "Approved", REJECTED: "Changes requested" };
const lineStatusLabel: Record<string, string> = { DRAFT: "Not reviewed", SUBMITTED: "Waiting for review", APPROVED: "Approved", REJECTED: "Needs changes" };
const localToday = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; };
const emptyTripFilters: TripFilters = { search: "", status: "", vehicle_id: "", driver_id: "", date_from: "", date_to: "" };
export default function FleetPage() {
    const [initialLoading, setInitialLoading] = useState(true);
    const pathname = usePathname();
    const featureSections: Record<string, string> = { trucks: "fleet-setup", "create-trip": "trip-create", "trip-reports": "trip-reports", "driver-salaries": "driver-salaries", "follow-ups": "follow-ups", trips: "trips", alerts: "alerts" };
    // Fleet subpages should fetch only the data shown on that page. The root is a compact overview.
    const focusSection = featureSections[pathname.split("/")[2]] || "overview";
    const [vehicles, setVehicles] = useState<Vehicle[]>([]);
    const [drivers, setDrivers] = useState<Driver[]>([]);
    const [orders, setOrders] = useState<TransportOrder[]>([]);
    const [members, setMembers] = useState<Member[]>([]);
    const [alerts, setAlerts] = useState<FleetAlert[]>([]);
    const [trips, setTrips] = useState<Trip[]>([]);
    const [dashboard, setDashboard] = useState<Dashboard | null>(null);
    const [followUps, setFollowUps] = useState<FollowUp[]>([]);
    const [salaryRecords, setSalaryRecords] = useState<SalaryRecord[]>([]);
    const [filterInputs, setFilterInputs] = useState<TripFilters>(emptyTripFilters);
    const [filters, setFilters] = useState<TripFilters>(emptyTripFilters);
    const [tripReport, setTripReport] = useState<TripReport | null>(null);
    const [reportError, setReportError] = useState("");
    const [message, setMessage] = useState("");
    const [alertsError, setAlertsError] = useState("");
    const [busy, setBusy] = useState(false);
    const idempotencyKeys = useRef(new WeakMap<HTMLFormElement, string>());
    const refresh = useCallback(async () => {
        const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
        const overview = focusSection === "overview" || focusSection === "alerts";
        const needVehicles = ["fleet-setup", "trip-create", "trip-reports", "trips"].includes(focusSection);
        const needDrivers = needVehicles;
        const needTrips = focusSection === "trips";
        const needMembers = focusSection === "fleet-setup";
        const needDashboard = overview;
        const needFollowUps = focusSection === "follow-ups";
        const needSalaries = focusSection === "driver-salaries";
        const needAlerts = overview;
        const needOrders = focusSection === "trip-create";
        const [v, d, t, membersResponse, summary, followUpsResponse, salariesResponse, alertsResponse, ordersResponse] = await Promise.all([
            needVehicles ? apiFetch("/fleet/vehicles") : Promise.resolve(null),
            needDrivers ? apiFetch("/fleet/drivers") : Promise.resolve(null),
            needTrips ? apiFetch(`/fleet/trips${params.size ? `?${params}` : ""}`) : Promise.resolve(null),
            needMembers ? apiFetch("/users") : Promise.resolve(null),
            needDashboard ? apiFetch("/fleet/dashboard") : Promise.resolve(null),
            needFollowUps ? apiFetch("/fleet/follow-ups") : Promise.resolve(null),
            needSalaries ? apiFetch("/fleet/driver-salaries") : Promise.resolve(null),
            needAlerts ? apiFetch("/fleet/alerts") : Promise.resolve(null),
            needOrders ? apiFetch("/fleet/orders?status=OPEN") : Promise.resolve(null),
        ]);
        if (v?.ok)
            setVehicles(await v.json());
        if (d?.ok)
            setDrivers(await d.json());
        if (t?.ok)
            setTrips(await t.json());
        if (membersResponse?.ok)
            setMembers(await membersResponse.json());
        if (summary?.ok)
            setDashboard(await summary.json());
        if (followUpsResponse?.ok)
            setFollowUps(await followUpsResponse.json());
        if (salariesResponse?.ok)
            setSalaryRecords(await salariesResponse.json());
        if (alertsResponse?.ok) {
            setAlerts((await alertsResponse.json()).alerts || []);
            setAlertsError("");
        }
        else if (needAlerts) {
            setAlerts([]);
            setAlertsError("Fleet alerts could not be loaded. Retry before relying on the alert count.");
        }
        if (ordersResponse?.ok)
            setOrders(await ordersResponse.json());
        if ([v, d, t, summary, followUpsResponse, salariesResponse, alertsResponse, ordersResponse].some(response => response !== null && !response.ok))
            throw new Error("Some fleet data could not refresh.");
    }, [filters, focusSection]);
    useEffect(() => { void refresh().catch(() => setMessage("Could not load fleet data. Check the API connection and workspace.")).finally(() => setInitialLoading(false)); }, [refresh]);
    async function send(path: string, method: string, data: unknown) {
        const response = await apiFetch(path, { method, body: JSON.stringify(data) });
        const payload = response.status === 204 ? null : await response.json().catch(() => null);
        if (!response.ok)
            throw Object.assign(new Error(payload?.error?.message || (typeof payload?.error === "string" ? payload.error : "Request failed")), { payload });
        return payload;
    }
    async function submitForm(event: FormEvent<HTMLFormElement>, path: string) {
        event.preventDefault();
        setMessage("");
        setBusy(true);
        const formElement = event.currentTarget;
        const data = Object.fromEntries(new FormData(formElement).entries());
        if (data.user_id === "")
            delete data.user_id;
        if (data.transport_order_id === "")
            delete data.transport_order_id;
        try {
            await send(path, "POST", data);
            formElement.reset();
            await refresh();
            setMessage("Saved successfully.");
        }
        catch (error) {
            if (error && typeof error === "object" && "payload" in error) applyFieldErrors(formElement, error.payload);
            setMessage(error instanceof Error ? error.message : "Could not save this record.");
        }
        finally {
            setBusy(false);
        }
    }
    async function tripAction(trip: Trip, action: "start" | "load" | "complete" | "submit" | "approve" | "reject") {
        const note = action === "reject" ? (await requestInput("What changes are needed for this trip?")) : "";
        if (action === "reject" && !note?.trim())
            return;
        const odometerEnd = action === "complete" ? (await requestInput("Ending odometer reading (optional):")) : null;
        if (action === "complete" && odometerEnd === null)
            return;
        const labels = { start: "Pickup check-in recorded.", load: "Load confirmation recorded.", complete: "Trip marked complete.", submit: "Trip sent for review.", approve: "Trip approved.", reject: "Changes requested." };
        try {
            const result = await send(`/fleet/trips/${trip.id}/${action}`, "POST", { note, ...(action === "complete" && odometerEnd?.trim() ? { odometer_end: odometerEnd.trim() } : {}) });
            await refresh();
            setMessage(result?.driver_earning_warning ? `${labels[action]} ${result.driver_earning_warning}` : labels[action]);
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not update this trip.");
        }
    }
    async function followUpAction(item: FollowUp, action: "start" | "resolve" | "waive") {
        const note = action === "resolve" || action === "waive" ? (await requestInput(action === "waive" ? "Reason for waiving this follow-up?" : "What was done to resolve it? (optional)")) || "" : "";
        if (action === "waive" && !note.trim())
            return;
        try {
            await send(`/fleet/follow-ups/${item.id}`, "PATCH", { action, note });
            await refresh();
            setMessage("Follow-up updated.");
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not update this follow-up.");
        }
    }
    async function addLine(event: FormEvent<HTMLFormElement>, trip: Trip, kind: "revenue" | "expenses") {
        event.preventDefault();
        setMessage("");
        setBusy(true);
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        const data: Record<string, FormDataEntryValue> = Object.fromEntries(form.entries());
        if (data.quantity_litres === "")
            delete data.quantity_litres;
        if (kind === "expenses") {
            const key = idempotencyKeys.current.get(formElement) || crypto.randomUUID();
            idempotencyKeys.current.set(formElement, key);
            data.idempotency_key = key;
            data.paid_by_driver = form.get("paid_by_driver") === "on" ? "true" : "false";
        }
        try {
            const receipt = form.get("receipt_file");
            delete data.receipt_file;
            if (kind === "expenses" && receipt instanceof File && receipt.size > 0) {
                const upload = new FormData();
                upload.set("file", receipt);
                const uploaded = await apiFetch("/fleet/documents", { method: "POST", body: upload });
                const uploadedData = await uploaded.json().catch(() => null);
                if (!uploaded.ok)
                    throw new Error(uploadedData?.error || "Receipt upload failed.");
                data.receipt_id = uploadedData.id;
            }
            await send(`/fleet/trips/${trip.id}/${kind}`, "POST", data);
            idempotencyKeys.current.delete(formElement);
            formElement.reset();
            await refresh();
            setMessage("Trip amount saved. It will count in the approved totals after review.");
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not save this trip amount.");
        }
        finally {
            setBusy(false);
        }
    }
    async function createSalaryRecord(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setMessage("");
        setBusy(true);
        const formElement = event.currentTarget;
        const data = Object.fromEntries(new FormData(formElement).entries());
        data.period_start = `${data.period_start}-01`;
        try {
            await send("/fleet/driver-salaries", "POST", data);
            formElement.reset();
            await refresh();
            setMessage("Monthly salary recorded.");
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not record this salary.");
        }
        finally {
            setBusy(false);
        }
    }
    async function paySalary(event: FormEvent<HTMLFormElement>, record: SalaryRecord) {
        event.preventDefault();
        setMessage("");
        setBusy(true);
        const formElement = event.currentTarget;
        const data = Object.fromEntries(new FormData(formElement).entries());
        const key = idempotencyKeys.current.get(formElement) || crypto.randomUUID();
        idempotencyKeys.current.set(formElement, key);
        data.idempotency_key = key;
        try {
            await send(`/fleet/driver-salaries/${record.id}/payments`, "POST", data);
            idempotencyKeys.current.delete(formElement);
            formElement.reset();
            await refresh();
            setMessage("Salary payment recorded.");
        }
        catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not record this payment.");
        }
        finally {
            setBusy(false);
        }
    }
    async function loadTripReport(activeFilters: TripFilters) {
        setReportError("");
        const params = new URLSearchParams(Object.entries(activeFilters).filter(([, value]) => value));
        try {
            const response = await apiFetch(`/fleet/trips/report${params.size ? `?${params}` : ""}`);
            const payload = await response.json().catch(() => null);
            if (!response.ok)
                throw new Error(payload?.detail || payload?.error || "Could not load the trip report.");
            setTripReport(payload);
        }
        catch (error) {
            setReportError(error instanceof Error ? error.message : "Could not load the trip report.");
        }
    }
    function updateTripFilter(field: keyof TripFilters, value: string) {
        setFilterInputs(current => ({ ...current, [field]: value }));
    }
    function applyTripFilters(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setFilters(filterInputs);
        void loadTripReport(filterInputs);
    }
    function clearTripFilters() {
        setFilterInputs(emptyTripFilters);
        setFilters(emptyTripFilters);
        void loadTripReport(emptyTripFilters);
    }
    function reportTable(title: string, groups: ReportGroup[]) {
        return <UiBox className="overflow-hidden rounded-lg border border-line"><UiH3 className="border-b border-line bg-slate-50 px-3 py-2 text-sm font-semibold">{title}</UiH3>{groups.length === 0 ? <EmptyState description="No approved trip data for this selection." onAction={()=>void refresh()} actionLabel="Refresh data" /> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[520px] text-left text-xs"><UiTableHead className="text-slate-500"><UiTableRow><UiTh className="px-3 py-2">{title === "By month" ? "Month" : "Name"}</UiTh><UiTh className="px-3 py-2">Trips</UiTh><UiTh className="px-3 py-2">Income</UiTh><UiTh className="px-3 py-2">Costs</UiTh><UiTh className="px-3 py-2">Margin</UiTh></UiTableRow></UiTableHead><UiTableBody>{groups.map(group => <UiTableRow className="border-t border-line" key={group.id}><UiTd className="px-3 py-2 font-medium">{group.name}</UiTd><UiTd className="px-3 py-2">{group.trips}</UiTd><UiTd className="px-3 py-2">₹{group.income}</UiTd><UiTd className="px-3 py-2">₹{group.costs}</UiTd><UiTd className="px-3 py-2">₹{group.margin}</UiTd></UiTableRow>)}</UiTableBody></UiTable></UiBox>}</UiBox>;
    }
    const activeFollowUps = followUps.filter(item => openStatuses.includes(item.status));
    const metricCards: [
        string,
        string | number
    ][] = [
        ["Active trucks", dashboard?.active_vehicles ?? 0], ["Active drivers", dashboard?.active_drivers ?? 0],
        ["Trips underway", dashboard?.trips_in_progress ?? 0], ["Waiting for review", dashboard?.trips_awaiting_review ?? 0],
        ["Open follow-ups", dashboard?.open_follow_ups ?? 0], ["Salary still to pay", `₹${dashboard?.driver_salary_remaining ?? "0.00"}`], ["Approved trip margin", `₹${dashboard?.approved_trip_margin ?? "0.00"}`],
    ];
    const tripPage = useListPagination(trips, JSON.stringify(filters) + String(focusSection));
    const etaEvaluations = trips.filter(trip => trip.eta_error_minutes !== null && trip.eta_error_minutes !== undefined);
    const averageEtaError = etaEvaluations.length ? etaEvaluations.reduce((total, trip) => total + Math.abs(trip.eta_error_minutes || 0), 0) / etaEvaluations.length : null;
    const followUpPage = useListPagination(activeFollowUps);
    const salaryPage = useListPagination(salaryRecords);
    if (initialLoading) return <PageSkeleton variant="cards" label="Loading fleet operations" />;
    return <UiMain className="w-full min-w-0 px-4 py-8 sm:px-6 lg:px-8">
    <UiBox className="mb-7 flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-xs font-semibold uppercase tracking-widest text-forest">Transport operations</UiText><UiH1 className="mt-1 text-3xl font-bold tracking-tight text-ink">Fleet & trips</UiH1><UiText className="mt-2 max-w-2xl text-sm text-slate-500">Set up trucks and drivers, record each trip’s income and costs, then review the approved trip margin.</UiText></UiBox><UiButton className="rounded-lg border border-line px-3 py-2 text-sm font-medium hover:bg-slate-50" onClick={() => void refresh()}>Refresh</UiButton></UiBox>
    <LiveData onRefresh={refresh} paused={busy} interval={focusSection === "overview" || focusSection === "alerts" ? 60000 : 30000}/>
    {alertsError && <UiBox role="alert" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{alertsError}<UiButton type="button" onClick={() => void refresh().catch(() => setAlertsError("Fleet alerts could not be loaded. Check the connection and retry."))} className="ml-3 font-semibold underline">Retry alerts</UiButton></UiBox>}
    {message && <UiBox role="status" className="mb-5 rounded-lg border border-line bg-white px-4 py-3 text-sm text-slate-700">{message}</UiBox>}

    {(!focusSection || focusSection === 'overview' || focusSection === 'alerts') && <>
    <UiSection className="mb-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metricCards.map(([label, value]) => <UiBox className={cardClass} key={label}><UiText className="text-xs text-slate-500">{label}</UiText><UiText className="mt-2 text-xl font-bold text-ink">{value}</UiText>{label === "Approved trip margin" && <UiText className="mt-1 text-[11px] text-slate-500">Approved amounts only</UiText>}</UiBox>)}
    </UiSection>
    <UiSection className={`${cardClass} mb-7`}><UiBox className="flex items-start justify-between gap-3"><UiBox><UiH2 className="font-semibold">Trip profitability & fuel alerts</UiH2><UiText className="mt-1 text-xs text-slate-500">Budget overruns, low margins, and fuel efficiency below a truck’s benchmark.</UiText></UiBox><UiSpan className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">{alerts.length} alerts</UiSpan></UiBox>{alerts.length ? <UiBox className="mt-3 divide-y divide-line">{alerts.map(alert => <UiBox key={alert.id} className="flex flex-wrap justify-between gap-2 py-3 text-sm"><UiSpan><UiStrong>{alert.trip_number}</UiStrong> · {alert.message}</UiSpan><UiSpan className="text-xs text-slate-500">{alert.kind.replaceAll("_", " ")}</UiSpan></UiBox>)}</UiBox> : <EmptyState description="No trip alerts. Add budgets, fuel litres, and truck efficiency benchmarks for more checks." onAction={()=>void refresh()} actionLabel="Refresh data" />}</UiSection>
    </>}

    {(!focusSection || focusSection === 'fleet-setup') && <>
    <UiBox className="mb-3"><UiH2 className="text-lg font-semibold">1. Set up your fleet</UiH2><UiText className="mt-1 text-sm text-slate-500">Add each truck and driver once. You can select them when creating trips.</UiText></UiBox>
    <UiSection id="fleet-setup" className="mb-7 grid gap-5 lg:grid-cols-2">
      <UiForm className={cardClass} onSubmit={e => void submitForm(e, "/fleet/vehicles")}><UiH3 className="mb-4 font-semibold">Add a truck</UiH3><UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="text-xs text-slate-500">Truck registration number<UiInput className={inputClass} name="registration_number" required placeholder="KA 01 AB 1234"/></UiLabel><UiLabel className="text-xs text-slate-500">Make and model <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="make_model" placeholder="e.g. Tata 407"/></UiLabel><UiLabel className="text-xs text-slate-500">Ownership <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="ownership_type" placeholder="Owned or leased"/></UiLabel><UiLabel className="text-xs text-slate-500">Vehicle type<UiSelect name="vehicle_type" className={inputClass} defaultValue=""><option value="">Not configured</option>{["LCV","RIGID","TRAILER","TANKER","REFRIGERATED"].map(t=><option key={t} value={t}>{t}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Capacity unit<UiSelect name="capacity_unit" className={inputClass} defaultValue=""><option value="">Not configured</option>{["TONNE","KG","CBM","PALLET"].map(t=><option key={t} value={t}>{t}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Load capacity <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="capacity" type="number" step="0.001" min="0" placeholder="Use your usual unit"/></UiLabel><UiLabel className="text-xs text-slate-500">Expected fuel efficiency (km/L)<UiInput className={inputClass} name="expected_km_per_litre" type="number" step="0.1" min="0.1" placeholder="Optional truck benchmark"/></UiLabel></UiBox><UiButton disabled={busy} className="mt-4 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save truck</UiButton></UiForm>
      <UiForm className={cardClass} onSubmit={e => void submitForm(e, "/fleet/drivers")}><UiH3 className="mb-4 font-semibold">Add a driver</UiH3><UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="text-xs text-slate-500">Driver’s full name<UiInput className={inputClass} name="name" required placeholder="Name"/></UiLabel><UiLabel className="text-xs text-slate-500">Phone number <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="contact_phone" type="tel" placeholder="Contact number"/></UiLabel><UiLabel className="text-xs text-slate-500">Staff ID or reference <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="reference_code" placeholder="Employee ID"/></UiLabel><UiLabel className="text-xs text-slate-500">Driver sign-in account <UiSpan className="text-slate-400">(create/invite a DRIVER user first)</UiSpan><UiSelect className={inputClass} name="user_id" defaultValue=""><option value="">No account linked</option>{members.filter(member => member.role === "DRIVER" && member.is_active && !drivers.some(driver => driver.account_email === member.email)).map(member => <option key={member.id} value={member.id}>{member.name || member.email} · {member.email}</option>)}</UiSelect></UiLabel></UiBox><UiButton disabled={busy} className="mt-4 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save driver</UiButton></UiForm>
    </UiSection>
    </>}

    {(!focusSection || focusSection === 'trip-create') && <>
    <UiBox className="mb-3"><UiH2 className="text-lg font-semibold">2. Create a trip</UiH2><UiText className="mt-1 text-sm text-slate-500">Choose an active truck and driver, then add the route and trip reference.</UiText></UiBox>
    <UiSection id="trip-create" className="mb-7 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,.8fr)]">
      <UiForm className={cardClass} onSubmit={e => void submitForm(e, "/fleet/trips")}><UiH3 className="mb-4 font-semibold">New trip</UiH3><UiBox className="grid gap-3 sm:grid-cols-2"><UiLabel className="text-xs text-slate-500">Trip number or reference<UiInput className={inputClass} name="trip_number" required placeholder="e.g. TRIP-1042"/></UiLabel><UiLabel className="text-xs text-slate-500">Truck<UiSelect className={inputClass} name="vehicle_id" required defaultValue=""><option value="" disabled>Select a truck</option>{vehicles.filter(v => v.status === "ACTIVE").map(v => <option key={v.id} value={v.id}>{v.registration_number}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Driver<UiSelect className={inputClass} name="driver_id" required defaultValue=""><option value="" disabled>Select a driver</option>{drivers.filter(d => d.status === "ACTIVE").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Transport order <UiSpan className="text-slate-400">(optional)</UiSpan><UiSelect className={inputClass} name="transport_order_id" defaultValue=""><option value="">No order linked</option>{orders.map(order => <option key={order.id} value={order.id}>{order.order_number} · {order.customer.name} · {order.origin} → {order.destination}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Customer or booking reference <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="customer_reference" placeholder="Customer / booking"/></UiLabel><UiLabel className="text-xs text-slate-500">Pickup location<UiInput className={inputClass} name="origin" placeholder="From"/></UiLabel><UiLabel className="text-xs text-slate-500">Delivery location<UiInput className={inputClass} name="destination" placeholder="To"/></UiLabel><UiLabel className="text-xs text-slate-500">Planned start time <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} type="datetime-local" name="starts_at"/></UiLabel><UiLabel className="text-xs text-slate-500">Starting odometer <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="odometer_start" type="number" min="0" step="0.1" placeholder="Truck reading at departure"/></UiLabel></UiBox><UiButton disabled={busy || !vehicles.some(v => v.status === "ACTIVE") || !drivers.some(d => d.status === "ACTIVE")} className="mt-4 rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Create trip</UiButton>{(!vehicles.some(v => v.status === "ACTIVE") || !drivers.some(d => d.status === "ACTIVE")) && <UiText className="mt-2 text-xs text-amber-700">Add an active truck and driver before creating a trip.</UiText>}</UiForm>
      <UiBox className={cardClass}><UiH3 className="font-semibold">How a trip moves through review</UiH3><ol className="mt-3 list-inside list-decimal space-y-2 text-sm leading-6 text-slate-600"><li>Start the trip when the truck leaves.</li><li>Mark it complete at delivery and enter the ending odometer if available.</li><li>Add the final income and costs, then send the trip for review.</li><li>Only approved actual amounts count toward the approved margin.</li></ol><UiText className="mt-3 text-xs text-slate-500">Pending amounts are shown on the trip but excluded from approved totals.</UiText></UiBox>
    </UiSection>
    </>}

    {(!focusSection || focusSection === 'follow-ups') && <>
    <UiSection id="follow-ups" className="mb-7"><UiBox className="mb-3 flex items-center justify-between"><UiBox><UiH2 className="text-lg font-semibold">Follow-ups to handle</UiH2><UiText className="mt-1 text-sm text-slate-500">For example, a missing receipt or a cost above its planned budget.</UiText></UiBox><UiSpan className="text-xs text-slate-500">{activeFollowUps.length} open</UiSpan></UiBox><UiBox className="grid gap-3 md:grid-cols-2">{followUpPage.rows.map(item => <UiArticle key={item.id} className={cardClass}><UiText className="text-[10px] font-semibold uppercase tracking-wider text-amber-700">{item.category.replaceAll("_", " ")}</UiText><UiText className="mt-1 text-sm font-medium">{item.description}</UiText><UiBox className="mt-3 flex gap-2">{item.status === "OPEN" && <UiButton onClick={() => void followUpAction(item, "start")} className="rounded-lg border border-line px-3 py-1.5 text-xs">Mark in progress</UiButton>}<UiButton onClick={() => void followUpAction(item, "resolve")} className="rounded-lg bg-forest px-3 py-1.5 text-xs font-semibold text-white">Mark resolved</UiButton><UiButton onClick={() => void followUpAction(item, "waive")} className="rounded-lg border border-line px-3 py-1.5 text-xs">Waive</UiButton></UiBox></UiArticle>)}{activeFollowUps.length === 0 && <UiText className="text-sm text-slate-500">You’re all caught up. No open follow-ups.</UiText>}</UiBox>{followUpPage.controls}</UiSection>
    </>}

    {false && <>
    <UiSection id="driver-salaries" className="mb-7"><UiBox className="mb-3"><UiH2 className="text-lg font-semibold">Driver salary and payments</UiH2><UiText className="mt-1 text-sm text-slate-500">Record the salary owed for a month, then add one or more payments. The remaining balance updates automatically.</UiText></UiBox>
      <UiForm className={`${cardClass} mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_2fr_auto] lg:items-end`} onSubmit={createSalaryRecord}><UiLabel className="text-xs text-slate-500">Driver<UiSelect className={inputClass} name="driver_id" required defaultValue=""><option value="" disabled>Select driver</option>{drivers.filter(d => d.status === "ACTIVE").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Salary month<UiInput className={inputClass} name="period_start" type="month" required/></UiLabel><UiLabel className="text-xs text-slate-500">Salary owed<UiInput className={inputClass} name="salary_amount" type="number" min="0.01" step="0.01" placeholder="₹ amount" required/></UiLabel><UiLabel className="text-xs text-slate-500">Note <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="notes" placeholder="Monthly salary, trip allowance, etc."/></UiLabel><UiButton disabled={busy || !drivers.some(d => d.status === "ACTIVE")} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Record salary</UiButton></UiForm>
      <UiBox className="space-y-3">{salaryPage.rows.map(record => <UiArticle key={record.id} className={cardClass}><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiH3 className="font-semibold">{record.driver.name} · {new Date(`${record.period_start}T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" })}</UiH3><UiText className="mt-1 text-sm text-slate-500">Salary ₹{record.salary_amount} · Paid ₹{record.paid_amount} · <UiSpan className="font-semibold text-ink">Remaining ₹{record.remaining_amount}</UiSpan></UiText>{record.notes && <UiText className="mt-1 text-xs text-slate-500">{record.notes}</UiText>}</UiBox>{Number(record.remaining_amount) > 0 && <UiForm className="flex flex-wrap gap-2" onSubmit={e => void paySalary(e, record)}><UiInput className="w-28 rounded-lg border border-line px-3 py-2 text-sm" name="amount" type="number" min="0.01" max={record.remaining_amount} step="0.01" placeholder="₹ payment" required/><UiInput className="w-36 rounded-lg border border-line px-3 py-2 text-sm" name="payment_date" type="date" required defaultValue={localToday()} aria-label="Payment date"/><UiInput className="w-40 rounded-lg border border-line px-3 py-2 text-sm" name="payment_reference" placeholder="Reference (optional)"/><UiButton disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Record payment</UiButton></UiForm>}</UiBox>{record.payments.length > 0 && <UiBox className="mt-3 border-t border-line pt-3 text-xs text-slate-500">{record.payments.map(payment => <UiText key={payment.id} className="mt-1 flex justify-between gap-3"><UiSpan>Payment · {payment.payment_date}{payment.payment_reference ? ` · ${payment.payment_reference}` : ""}</UiSpan><UiSpan>₹{payment.amount}</UiSpan></UiText>)}</UiBox>}</UiArticle>)}{salaryRecords.length === 0 && <EmptyState description="No salary records yet. Add a driver’s monthly salary above to start tracking payments." onAction={()=>void refresh()} actionLabel="Refresh data" />}</UiBox>
    {salaryPage.controls}</UiSection>
    </>}

    {(!focusSection || focusSection === 'trip-reports') && <>
    <UiSection id="trip-reports" className="mb-7"><UiBox className="mb-3"><UiH2 className="text-lg font-semibold">Trip reports</UiH2><UiText className="mt-1 text-sm text-slate-500">Income, costs, and margin from approved actual amounts only.</UiText></UiBox><UiForm className={`${cardClass} mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4`} onSubmit={applyTripFilters}><UiLabel className="text-xs text-slate-500">From date<UiInput className={inputClass} type="date" value={filterInputs.date_from} onChange={e => updateTripFilter("date_from", e.target.value)}/></UiLabel><UiLabel className="text-xs text-slate-500">To date<UiInput className={inputClass} type="date" value={filterInputs.date_to} onChange={e => updateTripFilter("date_to", e.target.value)}/></UiLabel><UiLabel className="text-xs text-slate-500">Truck<UiSelect aria-label="Filter truck" className={inputClass} value={filterInputs.vehicle_id} onChange={e => updateTripFilter("vehicle_id", e.target.value)}><option value="">All trucks</option>{vehicles.map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration_number}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Driver<UiSelect aria-label="Filter driver" className={inputClass} value={filterInputs.driver_id} onChange={e => updateTripFilter("driver_id", e.target.value)}><option value="">All drivers</option>{drivers.map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Search trip, route, or customer<UiInput className={inputClass} value={filterInputs.search} onChange={e => updateTripFilter("search", e.target.value)} placeholder="Trip no., route, customer"/></UiLabel><UiLabel className="text-xs text-slate-500">Trip status<UiSelect className={inputClass} value={filterInputs.status} onChange={e => updateTripFilter("status", e.target.value)}><option value="">All statuses</option><option value="DRAFT">Draft</option><option value="IN_PROGRESS">In progress</option><option value="COMPLETED">Completed</option><option value="SUBMITTED">Waiting for review</option><option value="APPROVED">Approved</option><option value="REJECTED">Changes requested</option></UiSelect></UiLabel><UiBox className="flex items-end gap-2"><UiButton className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">Apply filters</UiButton><UiButton className="rounded-lg border border-line px-4 py-2 text-sm" type="button" onClick={clearTripFilters}>Clear</UiButton></UiBox></UiForm>
      {reportError && <UiAlert role="alert" className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{reportError}</UiAlert>}{tripReport && <><UiBox className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[["Approved trips", tripReport.trip_count], ["Approved income", `₹${tripReport.income}`], ["Approved costs", `₹${tripReport.costs}`], ["Approved margin", `₹${tripReport.margin}`], ["Budget overruns", `₹${tripReport.budget_overrun_total}`]].map(([label, value]) => <UiBox className={cardClass} key={label}><UiText className="text-xs text-slate-500">{label}</UiText><UiText className="mt-2 text-xl font-bold text-ink">{value}</UiText>{label === "Budget overruns" && <UiText className="mt-1 text-[11px] text-slate-500">Budgeted lines only</UiText>}</UiBox>)}</UiBox><UiBox className="grid gap-4 lg:grid-cols-3">{reportTable("By driver", tripReport.by_driver)}{reportTable("By truck", tripReport.by_truck)}{reportTable("By month", tripReport.by_month)}</UiBox><UiBox className="mt-4 overflow-hidden rounded-lg border border-line"><UiBox className="border-b border-line bg-slate-50 px-3 py-2"><UiH3 className="text-sm font-semibold">Approved costs by category</UiH3><UiText className="mt-1 text-xs text-slate-500">Budgeted totals include only costs with a budget. Overrun is the positive difference on each budgeted cost line.</UiText></UiBox>{tripReport.by_cost_category.length === 0 ? <EmptyState description="No approved cost lines for this selection." onAction={()=>void refresh()} actionLabel="Refresh data" /> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[650px] text-left text-xs"><UiTableHead className="text-slate-500"><UiTableRow><UiTh className="px-3 py-2">Category</UiTh><UiTh className="px-3 py-2">Trips</UiTh><UiTh className="px-3 py-2">Actual costs</UiTh><UiTh className="px-3 py-2">Budgeted costs</UiTh><UiTh className="px-3 py-2">Over budget</UiTh></UiTableRow></UiTableHead><UiTableBody>{tripReport.by_cost_category.map(row => <UiTableRow key={row.id} className="border-t border-line"><UiTd className="px-3 py-2 font-medium">{row.name}</UiTd><UiTd className="px-3 py-2">{row.trips}</UiTd><UiTd className="px-3 py-2">₹{row.actual}</UiTd><UiTd className="px-3 py-2">₹{row.budgeted}</UiTd><UiTd className="px-3 py-2">₹{row.over_budget}</UiTd></UiTableRow>)}</UiTableBody></UiTable></UiBox>}</UiBox></>}</UiSection>
    </>}

    {(!focusSection || focusSection === 'trips') && <>
    {averageEtaError !== null && <UiArticle className={`${cardClass} mb-4`}><UiText className="text-xs font-semibold text-slate-500">Historical ETA accuracy</UiText><UiText className="mt-1 text-xl font-bold">±{averageEtaError.toFixed(0)} min</UiText><UiText className="mt-1 text-xs text-slate-500">Average absolute difference between predicted and actual delivery across {etaEvaluations.length} completed trip(s) with a saved route estimate.</UiText></UiArticle>}
    <UiSection id="trips"><UiBox className="mb-3 flex items-center justify-between"><UiBox><UiH2 className="text-lg font-semibold">Trips</UiH2><UiText className="mt-1 text-sm text-slate-500">Showing trips that match the filters above.</UiText></UiBox><UiSpan className="text-xs text-slate-500">{trips.length} trips</UiSpan></UiBox><UiBox className="space-y-4"><CollectionExplorer rows={trips.map(trip=>({id:trip.id,trip:trip.trip_number,truck:trip.vehicle.registration_number,driver:trip.driver.name,origin:trip.origin,destination:trip.destination,status:trip.status,income_INR:Number(trip.revenue_total),cost_INR:Number(trip.expense_total),margin_INR:trip.margin===null?null:Number(trip.margin)}))} recordPrefix="trip-record-" onOpen={id=>tripPage.reveal(trips.findIndex(item=>item.id===id))}>{tripPage.rows.map(trip => <UiArticle id={`trip-record-${trip.id}`} tabIndex={-1} key={trip.id} className={cardClass}><TripProgress pickup={Boolean(trip.pickup_at)} loaded={Boolean(trip.loaded_at)} delivered={Boolean(trip.delivery_at)}/>
      <UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiBox className="flex flex-wrap items-center gap-2"><UiH3 className="font-semibold"><QuickDetails title={trip.trip_number} label={trip.trip_number} fields={{Truck:trip.vehicle.registration_number,Driver:trip.driver.name,Origin:trip.origin,Destination:trip.destination,Status:tripStatusLabel[trip.status] || trip.status,Income:`INR ${trip.revenue_total}`,Expenses:`INR ${trip.expense_total}`,Margin:trip.margin ? `INR ${trip.margin}` : "Pending",Pickup:trip.pickup_at,Delivery:trip.delivery_at}}/></UiH3><QuickDetails title={`Driver ${trip.driver.name}`} label="Driver details" fields={{Name:trip.driver.name,Status:drivers.find(driver=>driver.id===trip.driver.id)?.status || "—",Truck:trip.vehicle.registration_number,"Assigned trip":trip.trip_number}}/><UiSpan className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600">{tripStatusLabel[trip.status] || trip.status.replaceAll("_", " ")}</UiSpan></UiBox><UiText className="mt-1 text-sm text-slate-500">Truck {trip.vehicle.registration_number} · Driver {trip.driver.name} · {[trip.origin, trip.destination].filter(Boolean).join(" → ") || "Route not set"}</UiText>{trip.transport_order && <UiText className="mt-1 text-xs font-medium text-forest">Order {trip.transport_order.order_number} · {trip.transport_order.customer_name}</UiText>}{trip.ends_at && <UiText className="mt-1 text-xs text-slate-500">Completed {new Date(trip.ends_at).toLocaleString()}{trip.odometer_end ? ` · Ending odometer ${trip.odometer_end}` : ""}</UiText>}{trip.review_note && <UiText className="mt-2 text-sm text-rose-700">Reviewer’s note: {trip.review_note}</UiText>}</UiBox><UiBox className="text-sm sm:text-right"><UiText>Approved income <UiStrong>₹{trip.revenue_total}</UiStrong></UiText><UiText className="mt-1">Approved costs <UiStrong>₹{trip.expense_total}</UiStrong></UiText><UiText className="mt-1 text-xs text-slate-500">{trip.margin === null ? "Margin is available after trip approval" : `Approved trip margin ₹${trip.margin}`}</UiText></UiBox></UiBox>
      <UiText className="mt-3 text-xs text-slate-500">Totals above include approved actual amounts only. Pending items are listed below.</UiText>
      {(trip.status === "DRAFT" || trip.status === "IN_PROGRESS" || trip.status === "COMPLETED" || trip.status === "REJECTED") && <UiBox className="mt-4 grid gap-3 border-t border-line pt-4 lg:grid-cols-2">
        <UiForm className="flex flex-wrap gap-2" onSubmit={e => void addLine(e, trip, "revenue")}><UiInput className={`${inputClass} min-w-24 flex-1`} name="description" placeholder="Income description (e.g. freight charge)" required/><UiInput className="w-28 rounded-lg border border-line px-3 py-2 text-sm" name="amount" type="number" min="0.01" step="0.01" placeholder="₹ amount" required/><UiButton disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Add income</UiButton></UiForm>
        <UiForm className="grid gap-2 sm:grid-cols-[1fr_110px_115px_1fr_110px_1fr_auto]" onSubmit={e => void addLine(e, trip, "expenses")}><UiInput className={inputClass} name="description" placeholder="Cost description (e.g. diesel)" required/><UiInput className={inputClass} name="amount" type="number" min="0.01" step="0.01" placeholder="₹ actual" required/><UiSelect className={inputClass} name="category" aria-label="Cost category"><option value="FUEL">Fuel</option><option value="TOLL">Toll</option><option value="LOADING">Loading</option><option value="REPAIR">Repair</option><option value="OTHER">Other</option></UiSelect><UiInput className={inputClass} name="budgeted_amount" type="number" min="0" step="0.01" placeholder="₹ budget (optional)" aria-label="Planned cost budget"/><UiInput className={inputClass} name="quantity_litres" type="number" min="0.01" step="0.01" placeholder="Fuel litres" aria-label="Fuel litres for efficiency monitoring"/><UiLabel className="flex items-center text-xs text-slate-500">Receipt<UiInput className="ml-2 w-32 text-xs" name="receipt_file" type="file" accept="application/pdf,image/jpeg,image/png,image/heic" aria-label="Attach cost receipt"/></UiLabel><UiButton disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Add cost</UiButton></UiForm>
      </UiBox>}
      {(trip.revenue_lines.length > 0 || trip.expense_lines.length > 0) && <UiBox className="mt-4 grid gap-4 border-t border-line pt-3 text-xs sm:grid-cols-2"><UiBox><UiStrong className="text-slate-500">Income</UiStrong>{trip.revenue_lines.map(line => <UiText key={line.id} className="mt-1 flex justify-between gap-2"><UiSpan>{line.description} · {lineStatusLabel[line.status] || line.status.toLowerCase()}</UiSpan><UiSpan>₹{line.amount}</UiSpan></UiText>)}</UiBox><UiBox><UiStrong className="text-slate-500">Costs</UiStrong>{trip.expense_lines.map(line => <UiText key={line.id} className="mt-1 flex justify-between gap-2"><UiSpan>{line.category} · {line.description} · {line.receipt_name || "Receipt missing"} · {lineStatusLabel[line.status] || line.status.toLowerCase()}{line.budgeted_amount !== null && line.budgeted_amount !== undefined && <> · Budget ₹{line.budgeted_amount}{Number(line.amount) > Number(line.budgeted_amount) && <UiStrong className="text-rose-700"> · Over budget ₹{(Number(line.amount) - Number(line.budgeted_amount)).toFixed(2)}</UiStrong>}</>}</UiSpan><UiSpan>₹{line.amount}</UiSpan></UiText>)}</UiBox></UiBox>}
      <UiBox className="mt-4 flex flex-wrap gap-2">{trip.status === "DRAFT" && <UiButton onClick={() => void tripAction(trip, "start")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Check in at pickup</UiButton>}{trip.status === "IN_PROGRESS" && <>{!trip.loaded_at && <UiButton onClick={() => void tripAction(trip, "load")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Confirm load</UiButton>}<UiButton onClick={() => void tripAction(trip, "complete")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Complete trip</UiButton></>}{["DRAFT", "IN_PROGRESS", "COMPLETED", "REJECTED"].includes(trip.status) && <UiButton onClick={() => void tripAction(trip, "submit")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Send trip for review</UiButton>}{trip.status === "SUBMITTED" && <><UiButton onClick={() => void tripAction(trip, "approve")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Approve trip</UiButton><UiButton onClick={() => void tripAction(trip, "reject")} className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700">Request changes</UiButton></>}</UiBox>
    </UiArticle>)}{tripPage.controls}</CollectionExplorer>{trips.length === 0 && <UiBox className={`${cardClass} text-sm text-slate-500`}>{Object.values(filters).some(Boolean) ? "No trips match these filters. Clear filters or try a different search." : "No trips yet. Add a truck and driver above, then create your first trip."}</UiBox>}</UiBox></UiSection>
    </>}
  </UiMain>;
}
