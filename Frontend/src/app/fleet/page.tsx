"use client";
import { QuickDetails } from "@/components/quick-details";
import { CollectionExplorer } from "@/components/collection-explorer";
import { applyFieldErrors } from "@/components/form-validation";
import { EmptyState } from "@/components/empty-state";
import { PageSkeleton } from "@/components/content-skeleton";
import { TripProgress } from "@/components/workflow-progress";
import { AppLink as Link, UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { requestInput } from "@/components/product-dialogs";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { FleetLiveMap, type FleetMapVehicle } from "./live-tracking/fleet-live-map";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { canShowNavigation, type NavigationAccess } from "@/lib/navigation-access";
import { ArrowUpRight, CircleAlert, ClipboardList, Fuel, MapPin, Plus, RefreshCw, Route, Search, Truck, UsersRound, Wrench } from "lucide-react";
type Vehicle = {
    id: string;
    registration_number: string;
    status: string;
    make_model?: string;
    vehicle_type?: string;
    capacity?: string | null;
    capacity_unit?: string;
    expected_km_per_litre?: string | null;
    ownership_type?: string;
};
type Driver = {
    id: string;
    name: string;
    status: string;
    account_email?: string | null;
    contact_phone?: string;
    reference_code?: string;
};
type TrackingTrip = FleetMapVehicle & { trip_number: string; driver: string; origin: string; destination: string; age_seconds: number | null };
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
    quantity_litres?: string | null;
    fuel_fill_type?: "UNKNOWN" | "FULL" | "PARTIAL";
    odometer_km?: string | null;
    incurred_at?: string | null;
    payment_reference?: string;
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
    const [assetView, setAssetView] = useState<"vehicles" | "drivers">("vehicles");
    const [assetSearch, setAssetSearch] = useState("");
    const [vehicleFormOpen, setVehicleFormOpen] = useState(false);
    const [driverFormOpen, setDriverFormOpen] = useState(false);
    const [trackingTrips, setTrackingTrips] = useState<TrackingTrip[]>([]);
    const [trackingMessage, setTrackingMessage] = useState("");
    const [selectedTrackingTrip, setSelectedTrackingTrip] = useState<string | null>(null);
    const [trackingAccess, setTrackingAccess] = useState(false);
    const [navigationAccess, setNavigationAccess] = useState<NavigationAccess | null>(null);
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
    const [correctingFuel, setCorrectingFuel] = useState<string | null>(null);
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
        const needAccess = overview;
        const [v, d, t, membersResponse, summary, followUpsResponse, salariesResponse, alertsResponse, ordersResponse, accessResponse] = await Promise.all([
            needVehicles ? apiFetch("/fleet/vehicles") : Promise.resolve(null),
            needDrivers ? apiFetch("/fleet/drivers") : Promise.resolve(null),
            needTrips ? apiFetch(`/fleet/trips${params.size ? `?${params}` : ""}`) : Promise.resolve(null),
            needMembers ? apiFetch("/users") : Promise.resolve(null),
            needDashboard ? apiFetch("/fleet/dashboard") : Promise.resolve(null),
            needFollowUps ? apiFetch("/fleet/follow-ups") : Promise.resolve(null),
            needSalaries ? apiFetch("/fleet/driver-salaries") : Promise.resolve(null),
            needAlerts ? apiFetch("/fleet/alerts") : Promise.resolve(null),
            needOrders ? apiFetch("/fleet/orders?status=OPEN") : Promise.resolve(null),
            needAccess ? apiFetch("/auth/me") : Promise.resolve(null),
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
        if (accessResponse?.ok) {
            const access = await accessResponse.json() as NavigationAccess;
            setNavigationAccess(access);
            if (canShowNavigation("/fleet/live-tracking", access)) {
                setTrackingAccess(true);
                const trackingResponse = await apiFetch("/fleet/live-locations");
                if (trackingResponse.ok) {
                    const tracking = await trackingResponse.json();
                    const liveTrips: TrackingTrip[] = tracking.trips || [];
                    setTrackingTrips(liveTrips);
                    setSelectedTrackingTrip(current => liveTrips.some(trip => trip.trip_id === current) ? current : liveTrips[0]?.trip_id || null);
                    setTrackingMessage("");
                } else {
                    setTrackingTrips([]);
                    setTrackingMessage("Live location data is temporarily unavailable.");
                }
            } else {
                setTrackingAccess(false);
                setTrackingTrips([]);
                setTrackingMessage("Live tracking access is restricted for your role.");
            }
        } else if (needAccess) {
            setNavigationAccess(null);
            setTrackingAccess(false);
            setTrackingTrips([]);
            setTrackingMessage("Could not verify live tracking access.");
        }
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
            if (path === "/fleet/vehicles") setVehicleFormOpen(false);
            if (path === "/fleet/drivers") setDriverFormOpen(false);
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
        if (data.odometer_km === "")
            delete data.odometer_km;
        if (data.incurred_at === "")
            delete data.incurred_at;
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
    async function correctFuelLine(event: FormEvent<HTMLFormElement>, trip: Trip, line: Line) {
        event.preventDefault();
        setBusy(true);
        const formElement = event.currentTarget;
        const data: Record<string, FormDataEntryValue> = Object.fromEntries(new FormData(formElement).entries());
        for (const field of ["quantity_litres", "odometer_km", "incurred_at", "budgeted_amount"])
            if (data[field] === "") delete data[field];
        try {
            await send(`/fleet/trips/${trip.id}/expenses/${line.id}`, "PATCH", data);
            setCorrectingFuel(null);
            await refresh();
            setMessage("Fuel entry corrected and returned to draft review. Its correction is recorded in the audit history.");
        } catch (error) {
            setMessage(error instanceof Error ? error.message : "Could not correct this fuel entry.");
        } finally { setBusy(false); }
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
    const pageMeta: Record<string, { eyebrow: string; title: string; description: string }> = {
        overview: { eyebrow: "Operations", title: "Fleet control center", description: "A live view of vehicles, trips, and the work that needs attention." },
        "fleet-setup": { eyebrow: "Fleet directory", title: "Trucks & drivers", description: "Manage the vehicles and people available to your operation." },
        "trip-create": { eyebrow: "Dispatch", title: "Plan a trip", description: "Assign an available truck and driver to a customer movement." },
        trips: { eyebrow: "Operations", title: "Trip register", description: "Review trip progress, submitted amounts, and approved margins." },
        alerts: { eyebrow: "Operations", title: "Trip alerts", description: "Review budget overruns, low margins, and fuel efficiency exceptions." },
        "follow-ups": { eyebrow: "Operations", title: "Open follow-ups", description: "Resolve missing evidence and costs that need an operator decision." },
        "trip-reports": { eyebrow: "Insights", title: "Trip profitability", description: "Compare approved trip revenue, costs, and margin over time." },
        "driver-salaries": { eyebrow: "Finance", title: "Driver settlements", description: "Review driver earnings, approved payments, and outstanding balances." },
    };
    const currentPage = pageMeta[focusSection] || pageMeta.overview;
    const overviewCards = [
        { label: "Active trucks", value: dashboard ? dashboard.active_vehicles : "—", detail: "Fleet available for assignment", icon: Truck, tone: "text-slate-900", accent: "bg-slate-100 text-slate-700" },
        { label: "Active drivers", value: dashboard ? dashboard.active_drivers : "—", detail: "Drivers in the directory", icon: UsersRound, tone: "text-slate-900", accent: "bg-slate-100 text-slate-700" },
        { label: "Trips underway", value: dashboard ? dashboard.trips_in_progress : "—", detail: "Currently in progress", icon: Route, tone: "text-slate-900", accent: "bg-emerald-50 text-emerald-700" },
        { label: "Awaiting review", value: dashboard ? dashboard.trips_awaiting_review : "—", detail: "Completed trips to review", icon: ClipboardList, tone: dashboard?.trips_awaiting_review ? "text-amber-700" : "text-slate-900", accent: "bg-amber-50 text-amber-700" },
        { label: "Approved trip margin", value: dashboard ? `₹${dashboard.approved_trip_margin}` : "—", detail: "Approved actual amounts only", icon: ArrowUpRight, tone: "text-emerald-700", accent: "bg-emerald-50 text-emerald-700" },
    ];
    const tripPage = useListPagination(trips, JSON.stringify(filters) + String(focusSection));
    const etaEvaluations = trips.filter(trip => trip.eta_error_minutes !== null && trip.eta_error_minutes !== undefined);
    const averageEtaError = etaEvaluations.length ? etaEvaluations.reduce((total, trip) => total + Math.abs(trip.eta_error_minutes || 0), 0) / etaEvaluations.length : null;
    const followUpPage = useListPagination(activeFollowUps);
    const salaryPage = useListPagination(salaryRecords);
    if (initialLoading) return <PageSkeleton variant="cards" label="Loading fleet operations" />;
    return <UiMain className="w-full min-w-0 px-4 py-7 sm:px-6 lg:px-8">
      <UiBox className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <UiBox>
          <UiText className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-500">{currentPage.eyebrow}</UiText>
          <UiH1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">{currentPage.title}</UiH1>
          <UiText className="mt-1 max-w-2xl text-sm text-slate-500">{currentPage.description}</UiText>
        </UiBox>
        <UiBox className="flex items-center gap-2">
          {focusSection === "overview" && canShowNavigation("/fleet/dispatch", navigationAccess) && <Link href="/fleet/dispatch" className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-3.5 py-2.5 text-xs font-semibold text-white hover:bg-slate-800"><Route size={15}/>Open dispatch</Link>}
          <UiButton type="button" onClick={() => void refresh()} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"><RefreshCw size={14}/>{busy ? "Refreshing" : "Refresh data"}</UiButton>
        </UiBox>
      </UiBox>
      {(focusSection === "overview" || focusSection === "alerts") && <LiveData onRefresh={refresh} paused={busy} interval={60000} compact/>}
      {alertsError && (focusSection === "overview" || focusSection === "alerts") && <UiBox role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><span>{alertsError}</span><UiButton type="button" onClick={() => void refresh().catch(() => setAlertsError("Fleet alerts could not be loaded. Check the connection and retry."))} className="font-semibold underline">Retry</UiButton></UiBox>}
      {message && <UiBox role="status" className="mb-5 rounded-lg border border-line bg-white px-4 py-3 text-sm text-slate-700">{message}</UiBox>}

      {(focusSection === "overview" || focusSection === "alerts") && <>
        <UiSection aria-label="Fleet performance snapshot" className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {overviewCards.map(metric => { const Icon = metric.icon; return <UiArticle key={metric.label} className="rounded-xl border border-slate-200 bg-white p-4">
            <UiBox className="flex items-start justify-between gap-2"><UiText className="text-xs font-medium text-slate-500">{metric.label}</UiText><span className={`grid size-8 shrink-0 place-items-center rounded-lg ${metric.accent}`}><Icon size={16}/></span></UiBox>
            <UiText className={`mt-2 text-2xl font-semibold tracking-tight tabular-nums ${metric.tone}`}>{metric.value}</UiText>
            <UiText className="mt-1 text-[11px] text-slate-500">{metric.detail}</UiText>
          </UiArticle>; })}
        </UiSection>

        <div className="mb-5 grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,.85fr)]">
          <UiSection className="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white">
            <UiBox className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><UiBox><UiH2 className="text-sm font-semibold text-slate-900">Live operations</UiH2><UiText className="mt-0.5 text-[11px] text-slate-500">Latest vehicle positions reported by active trips</UiText></UiBox>{trackingAccess && <Link href="/fleet/live-tracking" className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700 hover:text-slate-950">Open tracking <ArrowUpRight size={14}/></Link>}</UiBox>
            {trackingAccess ? <FleetLiveMap compact vehicles={trackingTrips} selectedTripId={selectedTrackingTrip} onSelect={setSelectedTrackingTrip}/> : <UiBox className="grid min-h-64 place-items-center bg-slate-50 px-6 py-10 text-center"><UiBox className="max-w-sm"><MapPin className="mx-auto text-slate-400" size={22}/><UiText className="mt-3 text-sm font-semibold text-slate-800">Live map access is unavailable</UiText><UiText className="mt-1 text-xs leading-5 text-slate-500">{trackingMessage || "This workspace role does not have permission to view live vehicle locations."}</UiText></UiBox></UiBox>}
            {trackingAccess && trackingTrips.length > 0 && <UiBox className="grid gap-0 border-t border-slate-200 sm:grid-cols-2">
              {trackingTrips.slice(0, 4).map((trip, index) => <button key={trip.trip_id} type="button" onClick={() => setSelectedTrackingTrip(trip.trip_id)} aria-pressed={trip.trip_id === selectedTrackingTrip} className={`flex min-w-0 items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50 ${index % 2 === 0 ? "sm:border-r sm:border-slate-200" : ""} ${index > 1 ? "border-t border-slate-200" : ""}`}>
                <span className="min-w-0"><span className="block truncate text-xs font-semibold text-slate-900">{trip.vehicle}<span className="ml-2 font-normal text-slate-500">{trip.trip_number}</span></span><span className="mt-0.5 block truncate text-[10px] text-slate-500">{trip.origin || "Origin"} → {trip.destination || "Destination"} · {trip.driver}</span></span>
                <span className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-semibold ${trip.status === "LIVE" ? "bg-emerald-50 text-emerald-700" : trip.status === "STALE" ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-600"}`}>{trip.status === "LIVE" ? "Live" : trip.status === "STALE" ? "Stale" : "Waiting"}</span>
              </button>)}
            </UiBox>}
          </UiSection>

          <div className="grid content-start gap-4">
            <UiSection className="rounded-xl border border-slate-200 bg-white p-4">
              <UiBox className="flex items-start justify-between gap-3"><UiBox><UiH2 className="text-sm font-semibold text-slate-900">Work queue</UiH2><UiText className="mt-0.5 text-[11px] text-slate-500">Items waiting for an operator</UiText></UiBox><ClipboardList size={17} className="text-slate-400"/></UiBox>
              <UiBox className="mt-3 divide-y divide-slate-100">
                {canShowNavigation("/fleet/trips", navigationAccess) && <Link href="/fleet/trips" className="flex items-center justify-between gap-3 py-3 text-xs hover:text-slate-950"><span><span className="block font-medium text-slate-800">Trips awaiting review</span><span className="mt-0.5 block text-[10px] text-slate-500">Review actual income and cost lines</span></span><UiSpan className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-800">{dashboard ? dashboard.trips_awaiting_review : "—"}</UiSpan></Link>}
                {canShowNavigation("/fleet/follow-ups", navigationAccess) && <Link href="/fleet/follow-ups" className="flex items-center justify-between gap-3 py-3 text-xs hover:text-slate-950"><span><span className="block font-medium text-slate-800">Open follow-ups</span><span className="mt-0.5 block text-[10px] text-slate-500">Missing evidence and cost exceptions</span></span><UiSpan className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-700">{dashboard ? dashboard.open_follow_ups : "—"}</UiSpan></Link>}
                {canShowNavigation("/fleet/driver-salaries", navigationAccess) && <Link href="/fleet/driver-salaries" className="flex items-center justify-between gap-3 py-3 text-xs hover:text-slate-950"><span><span className="block font-medium text-slate-800">Driver settlements remaining</span><span className="mt-0.5 block text-[10px] text-slate-500">Approved balance not yet settled</span></span><UiStrong className="shrink-0 text-xs tabular-nums">{dashboard ? `₹${dashboard.driver_salary_remaining}` : "—"}</UiStrong></Link>}
              </UiBox>
            </UiSection>
            <UiSection className="rounded-xl border border-slate-200 bg-white p-4">
              <UiBox className="flex items-center justify-between gap-3"><UiBox><UiH2 className="text-sm font-semibold text-slate-900">Trip and fuel alerts</UiH2><UiText className="mt-0.5 text-[11px] text-slate-500">Based on recorded budgets and vehicle benchmarks</UiText></UiBox><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${alerts.length ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-700"}`}>{alerts.length} open</span></UiBox>
              {alerts.length ? <UiBox className="mt-2 divide-y divide-slate-100">{alerts.slice(0, 3).map(alert => <UiBox key={alert.id} className="flex items-start gap-2 py-2.5"><CircleAlert size={14} className="mt-0.5 shrink-0 text-amber-600"/><UiBox className="min-w-0"><UiText className="text-xs font-medium text-slate-800">{alert.trip_number} · {alert.message}</UiText><UiText className="mt-0.5 text-[10px] text-slate-500">{alert.kind.replaceAll("_", " ")}</UiText></UiBox></UiBox>)}</UiBox> : <UiText className="mt-3 text-xs text-slate-500">No recorded exceptions need attention.</UiText>}
              <Link href="/fleet/alerts" className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-slate-700">Review alerts <ArrowUpRight size={13}/></Link>
            </UiSection>
          </div>
        </div>

        <UiSection aria-label="Fleet quick actions" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Plan and dispatch", detail: "Assign an open order", href: "/fleet/dispatch", icon: Route },
            { label: "Manage trucks & drivers", detail: "Update fleet availability", href: "/fleet/trucks", icon: Truck },
            { label: "Maintenance", detail: "Review service and breakdowns", href: "/fleet/maintenance", icon: Wrench },
            { label: "Fuel and trip costs", detail: "Review recorded spend", href: "/fleet/operational-reports", icon: Fuel },
          ].filter(action => canShowNavigation(action.href, navigationAccess)).map(action => { const Icon = action.icon; return <Link key={action.label} href={action.href} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3.5 py-3 transition-colors hover:border-slate-300 hover:bg-slate-50"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-700"><Icon size={16}/></span><span className="min-w-0"><span className="block text-xs font-semibold text-slate-900">{action.label}</span><span className="mt-0.5 block truncate text-[10px] text-slate-500">{action.detail}</span></span><ArrowUpRight size={14} className="ml-auto shrink-0 text-slate-400"/></Link>; })}
        </UiSection>
      </>}

      {focusSection === "fleet-setup" && <>
        <UiSection className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[{ label: "Vehicles", value: vehicles.length }, { label: "Active vehicles", value: vehicles.filter(vehicle => vehicle.status === "ACTIVE").length }, { label: "Drivers", value: drivers.length }, { label: "Active drivers", value: drivers.filter(driver => driver.status === "ACTIVE").length }].map(item => <UiBox key={item.label} className="rounded-lg border border-slate-200 bg-white px-4 py-3"><UiText className="text-[11px] font-medium text-slate-500">{item.label}</UiText><UiText className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{item.value}</UiText></UiBox>)}
        </UiSection>
        <UiSection className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1" role="group" aria-label="Fleet directory type">
            <button type="button" aria-pressed={assetView === "vehicles"} onClick={() => { setAssetView("vehicles"); setAssetSearch(""); }} className={`rounded-md px-3 py-2 text-xs font-semibold ${assetView === "vehicles" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>Vehicles <span className="ml-1 tabular-nums text-slate-400">{vehicles.length}</span></button>
            <button type="button" aria-pressed={assetView === "drivers"} onClick={() => { setAssetView("drivers"); setAssetSearch(""); }} className={`rounded-md px-3 py-2 text-xs font-semibold ${assetView === "drivers" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>Drivers <span className="ml-1 tabular-nums text-slate-400">{drivers.length}</span></button>
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
            <label className="relative min-w-0 flex-1 sm:w-64 sm:flex-none"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><input aria-label={`Search ${assetView}`} value={assetSearch} onChange={event => setAssetSearch(event.target.value)} placeholder={assetView === "vehicles" ? "Search registration or model" : "Search driver or phone"} className="h-9 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-xs outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"/></label>
            {assetView === "vehicles" ? <UiButton type="button" onClick={() => { setVehicleFormOpen(value => !value); setDriverFormOpen(false); }} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-950 px-3 text-xs font-semibold text-white hover:bg-slate-800"><Plus size={14}/>{vehicleFormOpen ? "Close" : "Add vehicle"}</UiButton> : <UiButton type="button" onClick={() => { setDriverFormOpen(value => !value); setVehicleFormOpen(false); }} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-950 px-3 text-xs font-semibold text-white hover:bg-slate-800"><Plus size={14}/>{driverFormOpen ? "Close" : "Add driver"}</UiButton>}
          </div>
        </UiSection>

        {vehicleFormOpen && <UiSection className="mb-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-5"><UiBox className="mb-4 flex items-start justify-between gap-3"><UiBox><UiH2 className="text-sm font-semibold">Register a vehicle</UiH2><UiText className="mt-1 text-xs text-slate-500">Required fields are marked by the browser. Add technical details when they are known.</UiText></UiBox><button type="button" aria-label="Close vehicle form" onClick={() => setVehicleFormOpen(false)} className="rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">Close</button></UiBox>
          <UiForm className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" onSubmit={event => void submitForm(event, "/fleet/vehicles")}><UiLabel className="text-xs text-slate-600">Registration number<UiInput className={inputClass} name="registration_number" required placeholder="KA 01 AB 1234"/></UiLabel><UiLabel className="text-xs text-slate-600">Make and model<UiInput className={inputClass} name="make_model" placeholder="e.g. Tata 407"/></UiLabel><UiLabel className="text-xs text-slate-600">Vehicle type<UiSelect name="vehicle_type" className={inputClass} defaultValue=""><option value="">Not configured</option>{["LCV","RIGID","TRAILER","TANKER","REFRIGERATED"].map(type => <option key={type} value={type}>{type}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-600">Ownership<UiInput className={inputClass} name="ownership_type" placeholder="Owned or leased"/></UiLabel><UiLabel className="text-xs text-slate-600">Capacity<UiInput className={inputClass} name="capacity" type="number" step="0.001" min="0" placeholder="Optional"/></UiLabel><UiLabel className="text-xs text-slate-600">Capacity unit<UiSelect name="capacity_unit" className={inputClass} defaultValue=""><option value="">Not configured</option>{["TONNE","KG","CBM","PALLET"].map(unit => <option key={unit} value={unit}>{unit}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-600">Expected fuel efficiency (km/L)<UiInput className={inputClass} name="expected_km_per_litre" type="number" step="0.1" min="0.1" placeholder="Optional benchmark"/></UiLabel><UiBox className="flex items-end"><UiButton disabled={busy} className="h-10 rounded-lg bg-slate-950 px-4 text-xs font-semibold text-white">{busy ? "Saving…" : "Save vehicle"}</UiButton></UiBox></UiForm>
        </UiSection>}

        {driverFormOpen && <UiSection className="mb-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-5"><UiBox className="mb-4 flex items-start justify-between gap-3"><UiBox><UiH2 className="text-sm font-semibold">Add a driver</UiH2><UiText className="mt-1 text-xs text-slate-500">Link an existing driver account if this person needs the phone trip view.</UiText></UiBox><button type="button" aria-label="Close driver form" onClick={() => setDriverFormOpen(false)} className="rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">Close</button></UiBox>
          <UiForm className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" onSubmit={event => void submitForm(event, "/fleet/drivers")}><UiLabel className="text-xs text-slate-600">Full name<UiInput className={inputClass} name="name" required placeholder="Driver name"/></UiLabel><UiLabel className="text-xs text-slate-600">Phone number<UiInput className={inputClass} name="contact_phone" type="tel" placeholder="Contact number"/></UiLabel><UiLabel className="text-xs text-slate-600">Staff ID or reference<UiInput className={inputClass} name="reference_code" placeholder="Employee ID"/></UiLabel><UiLabel className="text-xs text-slate-600">Driver sign-in account<UiSelect className={inputClass} name="user_id" defaultValue=""><option value="">No account linked</option>{members.filter(member => member.role === "DRIVER" && member.is_active && !drivers.some(driver => driver.account_email === member.email)).map(member => <option key={member.id} value={member.id}>{member.name || member.email} · {member.email}</option>)}</UiSelect></UiLabel><UiBox className="xl:col-span-4"><UiButton disabled={busy} className="h-10 rounded-lg bg-slate-950 px-4 text-xs font-semibold text-white">{busy ? "Saving…" : "Save driver"}</UiButton></UiBox></UiForm>
        </UiSection>}

        <UiSection className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          {assetView === "vehicles" ? <div className="overflow-x-auto"><UiTable className="w-full min-w-[720px] text-left"><UiTableHead><UiTableRow><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Vehicle</UiTh><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Type and capacity</UiTh><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Fuel benchmark</UiTh><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Ownership</UiTh><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Status</UiTh></UiTableRow></UiTableHead><UiTableBody>{vehicles.filter(vehicle => `${vehicle.registration_number} ${vehicle.make_model || ""} ${vehicle.vehicle_type || ""}`.toLowerCase().includes(assetSearch.toLowerCase())).map(vehicle => <UiTableRow key={vehicle.id} className="border-t border-slate-100"><UiTd className="px-4 py-3"><UiText className="text-xs font-semibold text-slate-900">{vehicle.registration_number}</UiText><UiText className="mt-0.5 text-[10px] text-slate-500">{vehicle.make_model || "Model not recorded"}</UiText></UiTd><UiTd className="px-4 py-3 text-xs text-slate-700">{vehicle.vehicle_type || "Not configured"}<UiText className="mt-0.5 text-[10px] text-slate-500">{vehicle.capacity ? `${vehicle.capacity} ${vehicle.capacity_unit || ""}` : "Capacity not recorded"}</UiText></UiTd><UiTd className="px-4 py-3 text-xs tabular-nums text-slate-700">{vehicle.expected_km_per_litre ? `${vehicle.expected_km_per_litre} km/L` : "Not configured"}</UiTd><UiTd className="px-4 py-3 text-xs text-slate-700">{vehicle.ownership_type || "Not recorded"}</UiTd><UiTd className="px-4 py-3"><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${vehicle.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{vehicle.status === "ACTIVE" ? "Active" : vehicle.status.replaceAll("_", " ")}</UiSpan></UiTd></UiTableRow>)}</UiTableBody></UiTable>{!vehicles.some(vehicle => `${vehicle.registration_number} ${vehicle.make_model || ""} ${vehicle.vehicle_type || ""}`.toLowerCase().includes(assetSearch.toLowerCase())) && <EmptyState kind={assetSearch ? "search" : "empty"} title={assetSearch ? "No vehicles found" : "No vehicles registered"} description={assetSearch ? "Try a different registration or model." : "Register a vehicle to make it available for trip assignment."} actionLabel={assetSearch ? "Clear search" : "Add vehicle"} onAction={() => assetSearch ? setAssetSearch("") : setVehicleFormOpen(true)}/>}</div> : <div className="overflow-x-auto"><UiTable className="w-full min-w-[680px] text-left"><UiTableHead><UiTableRow><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Driver</UiTh><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Contact and reference</UiTh><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Driver account</UiTh><UiTh className="px-4 py-3 text-[10px] uppercase tracking-wide text-slate-500">Status</UiTh></UiTableRow></UiTableHead><UiTableBody>{drivers.filter(driver => `${driver.name} ${driver.contact_phone || ""} ${driver.reference_code || ""} ${driver.account_email || ""}`.toLowerCase().includes(assetSearch.toLowerCase())).map(driver => <UiTableRow key={driver.id} className="border-t border-slate-100"><UiTd className="px-4 py-3"><UiText className="text-xs font-semibold text-slate-900">{driver.name}</UiText><UiText className="mt-0.5 text-[10px] text-slate-500">{driver.reference_code || "No staff reference"}</UiText></UiTd><UiTd className="px-4 py-3 text-xs text-slate-700">{driver.contact_phone || "No phone recorded"}</UiTd><UiTd className="px-4 py-3 text-xs text-slate-700">{driver.account_email || "No sign-in account"}</UiTd><UiTd className="px-4 py-3"><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${driver.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{driver.status === "ACTIVE" ? "Active" : driver.status.replaceAll("_", " ")}</UiSpan></UiTd></UiTableRow>)}</UiTableBody></UiTable>{!drivers.some(driver => `${driver.name} ${driver.contact_phone || ""} ${driver.reference_code || ""} ${driver.account_email || ""}`.toLowerCase().includes(assetSearch.toLowerCase())) && <EmptyState kind={assetSearch ? "search" : "empty"} title={assetSearch ? "No drivers found" : "No drivers registered"} description={assetSearch ? "Try a different name, phone, or account." : "Add a driver and optionally link their phone trip-view account."} actionLabel={assetSearch ? "Clear search" : "Add driver"} onAction={() => assetSearch ? setAssetSearch("") : setDriverFormOpen(true)}/>}</div>}
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
        <UiForm className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" onSubmit={e => void addLine(e, trip, "expenses")}><UiInput className={inputClass} name="description" placeholder="Cost description (e.g. diesel)" required/><UiInput className={inputClass} name="amount" type="number" min="0.01" step="0.01" placeholder="₹ actual" required/><UiSelect className={inputClass} name="category" aria-label="Cost category"><option value="FUEL">Fuel</option><option value="TOLL">Toll</option><option value="LOADING">Loading</option><option value="REPAIR">Repair</option><option value="OTHER">Other</option></UiSelect><UiInput className={inputClass} name="budgeted_amount" type="number" min="0" step="0.01" placeholder="₹ budget (optional)" aria-label="Planned cost budget"/><UiInput className={inputClass} name="quantity_litres" type="number" min="0.01" step="0.01" placeholder="Fuel litres" aria-label="Fuel litres for efficiency monitoring"/><UiSelect className={inputClass} name="fuel_fill_type" aria-label="Fuel fill type"><option value="UNKNOWN">Fill type not recorded</option><option value="FULL">Full tank</option><option value="PARTIAL">Partial fill</option></UiSelect><UiInput className={inputClass} name="odometer_km" type="number" min="0" step="0.1" placeholder="Fill odometer (km)" aria-label="Odometer at fuel fill"/><UiInput className={inputClass} name="incurred_at" type="date" aria-label="Fuel fill date"/><UiInput className={inputClass} name="payment_reference" placeholder="Receipt / transaction ref" aria-label="Fuel transaction reference"/><UiLabel className="flex items-center text-xs text-slate-500">Receipt<UiInput className="ml-2 w-32 text-xs" name="receipt_file" type="file" accept="application/pdf,image/jpeg,image/png,image/heic" aria-label="Attach cost receipt"/></UiLabel><UiButton disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Add cost</UiButton></UiForm>
      </UiBox>}
      {(trip.revenue_lines.length > 0 || trip.expense_lines.length > 0) && <UiBox className="mt-4 grid gap-4 border-t border-line pt-3 text-xs sm:grid-cols-2"><UiBox><UiStrong className="text-slate-500">Income</UiStrong>{trip.revenue_lines.map(line => <UiText key={line.id} className="mt-1 flex justify-between gap-2"><UiSpan>{line.description} · {lineStatusLabel[line.status] || line.status.toLowerCase()}</UiSpan><UiSpan>₹{line.amount}</UiSpan></UiText>)}</UiBox><UiBox><UiStrong className="text-slate-500">Costs</UiStrong>{trip.expense_lines.map(line => <UiBox key={line.id} className="mt-2 rounded-lg border border-line p-2"><UiText className="flex justify-between gap-2"><UiSpan>{line.category} · {line.description} · {line.receipt_name || "Receipt missing"} · {lineStatusLabel[line.status] || line.status.toLowerCase()}{line.category === "FUEL" && line.fuel_fill_type && <> · {line.fuel_fill_type.toLowerCase()} fill · {line.quantity_litres || "—"} L · {line.odometer_km || "—"} km · Ref {line.payment_reference || "—"}</>}{line.budgeted_amount !== null && line.budgeted_amount !== undefined && <> · Budget ₹{line.budgeted_amount}{Number(line.amount) > Number(line.budgeted_amount) && <UiStrong className="text-rose-700"> · Over budget ₹{(Number(line.amount) - Number(line.budgeted_amount)).toFixed(2)}</UiStrong>}</>}</UiSpan><UiSpan>₹{line.amount}</UiSpan></UiText>{line.category === "FUEL" && <UiButton type="button" onClick={() => setCorrectingFuel(correctingFuel === line.id ? null : line.id)} className="mt-1 rounded-md border border-line px-2 py-1 text-[10px] font-semibold">{correctingFuel === line.id ? "Close correction" : "Correct fuel entry"}</UiButton>}{correctingFuel === line.id && <UiForm className="mt-2 grid gap-2 sm:grid-cols-2" onSubmit={event => void correctFuelLine(event, trip, line)}><UiInput className={inputClass} name="description" defaultValue={line.description} aria-label="Fuel description" required/><UiInput className={inputClass} name="amount" type="number" min="0.01" step="0.01" defaultValue={line.amount} aria-label="Fuel cost" required/><UiInput className={inputClass} name="quantity_litres" type="number" min="0.01" step="0.01" defaultValue={line.quantity_litres || ""} aria-label="Fuel litres" placeholder="Litres"/><UiSelect className={inputClass} name="fuel_fill_type" defaultValue={line.fuel_fill_type || "UNKNOWN"} aria-label="Fuel fill type"><option value="UNKNOWN">Type unknown</option><option value="FULL">Full tank</option><option value="PARTIAL">Partial fill</option></UiSelect><UiInput className={inputClass} name="odometer_km" type="number" min="0" step="0.1" defaultValue={line.odometer_km || ""} aria-label="Odometer at fill" placeholder="Fill odometer (km)"/><UiInput className={inputClass} name="incurred_at" type="date" defaultValue={line.incurred_at || ""} aria-label="Fill date"/><UiInput className={inputClass} name="payment_reference" defaultValue={line.payment_reference || ""} aria-label="Receipt / transaction reference" placeholder="Receipt / transaction ref"/><UiInput className={`${inputClass} sm:col-span-2`} name="reason" minLength={8} maxLength={500} placeholder="Correction reason (required)" required/><UiButton disabled={busy} className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white sm:col-span-2">{busy ? "Saving correction…" : "Save correction for review"}</UiButton></UiForm>}</UiBox>)}</UiBox></UiBox>}
      <UiBox className="mt-4 flex flex-wrap gap-2">{trip.status === "DRAFT" && <UiButton onClick={() => void tripAction(trip, "start")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Check in at pickup</UiButton>}{trip.status === "IN_PROGRESS" && <>{!trip.loaded_at && <UiButton onClick={() => void tripAction(trip, "load")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Confirm load</UiButton>}<UiButton onClick={() => void tripAction(trip, "complete")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Complete trip</UiButton></>}{["DRAFT", "IN_PROGRESS", "COMPLETED", "REJECTED"].includes(trip.status) && <UiButton onClick={() => void tripAction(trip, "submit")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Send trip for review</UiButton>}{trip.status === "SUBMITTED" && <><UiButton onClick={() => void tripAction(trip, "approve")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Approve trip</UiButton><UiButton onClick={() => void tripAction(trip, "reject")} className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700">Request changes</UiButton></>}</UiBox>
    </UiArticle>)}{tripPage.controls}</CollectionExplorer>{trips.length === 0 && <UiBox className={`${cardClass} text-sm text-slate-500`}>{Object.values(filters).some(Boolean) ? "No trips match these filters. Clear filters or try a different search." : "No trips yet. Add a truck and driver above, then create your first trip."}</UiBox>}</UiBox></UiSection>
    </>}
  </UiMain>;
}
