"use client";
import { CollectionExplorer } from "@/components/collection-explorer";
import { applyFieldErrors } from "@/components/form-validation";
import { EmptyState } from "@/components/empty-state";
import { PageSkeleton } from "@/components/content-skeleton";
import { AppLink as Link, UiAlert, UiArticle, UiBox, UiButton, UiForm, UiH1, UiH2, UiH3, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiSpan, UiStrong, UiTable, UiTableBody, UiTableHead, UiTableRow, UiTd, UiText, UiTh } from "@/components/product-ui";
import { requestInput } from "@/components/product-dialogs";
import { useListPagination } from "@/components/list-pagination";
import { LiveData } from "@/components/live-data";
import { FleetLiveMap, type FleetMapVehicle } from "./live-tracking/fleet-live-map";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
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
const tripNextStep = (trip: Trip) => {
    if (trip.status === "DRAFT") return "Next: confirm the truck has arrived at pickup.";
    if (trip.status === "IN_PROGRESS" && !trip.loaded_at) return "Next: confirm the goods are loaded.";
    if (trip.status === "IN_PROGRESS") return "Next: mark the delivery finished.";
    if (trip.status === "COMPLETED" || trip.status === "REJECTED") return "Next: send this trip for approval.";
    if (trip.status === "SUBMITTED") return "A manager needs to approve this trip.";
    return "This trip is approved and finished.";
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
    trip_number?: string | null;
    truck?: string | null;
    driver_name?: string | null;
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
    trip_id?: string;
    trip_number?: string;
    vehicle_id?: string;
    truck?: string;
    message: string;
    amount: string;
};
const alertTypeLabel: Record<string, string> = {
    BUDGET_OVERRUN: "Over budget", DELIVERY_DELAY: "Delivery was late", DUPLICATE_RECEIPT: "Receipt used more than once",
    FUEL_COST_PER_KM_ANOMALY: "High fuel cost for distance", FUEL_PRICE_ANOMALY: "Fuel price looks high",
    LOW_FUEL_EFFICIENCY: "Low fuel efficiency", LOW_MARGIN: "Low trip earnings", MISSING_DELIVERY_PROOF: "Delivery proof missing",
    MISSING_FUEL_QUANTITY: "Fuel litres missing", MISSING_FUEL_RECORD: "Fuel cost missing", PREDICTED_DELIVERY_DELAY: "Delivery may be late",
    ROUTE_DISTANCE_ANOMALY: "Route distance looks unusual", TRUCK_DOCUMENT_EXPIRY: "Truck document due", TRUCK_MAINTENANCE_DUE: "Truck service due",
};
const inputClass = "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest";
const cardClass = "rounded-xl border border-line bg-white p-5 shadow-sm";
const openStatuses = ["OPEN", "IN_PROGRESS"];
const tripStatusLabel: Record<string, string> = { DRAFT: "Not started", IN_PROGRESS: "On the road", COMPLETED: "Delivery finished", SUBMITTED: "Waiting for manager", APPROVED: "Finished", REJECTED: "Needs changes" };
const tripStatusStyle: Record<string, string> = { DRAFT: "bg-blue-50 text-blue-700", IN_PROGRESS: "bg-emerald-50 text-emerald-700", COMPLETED: "bg-amber-50 text-amber-800", SUBMITTED: "bg-violet-50 text-violet-700", APPROVED: "bg-emerald-50 text-emerald-700", REJECTED: "bg-rose-50 text-rose-700" };
const lineStatusLabel: Record<string, string> = { DRAFT: "Not checked yet", SUBMITTED: "Waiting for approval", APPROVED: "Approved", REJECTED: "Needs changes" };
const followUpCategoryLabel: Record<string, string> = { MISSING_RECEIPT: "Receipt missing", BUDGET_VARIANCE: "Cost over budget", DELAY: "Trip delay", CUSTOMER_UNAVAILABLE: "Customer unavailable", VEHICLE_ISSUE: "Truck issue", CARGO_ISSUE: "Cargo issue", ROUTE_ISSUE: "Route issue", OTHER: "Other issue" };
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
    const [tripSearch, setTripSearch] = useState("");
    const [tripStatusFilter, setTripStatusFilter] = useState("");
    const [alertSearch, setAlertSearch] = useState("");
    const [followUpSearch, setFollowUpSearch] = useState("");
    const [followUpStatusFilter, setFollowUpStatusFilter] = useState("");
    const [tripReport, setTripReport] = useState<TripReport | null>(null);
    const [reportError, setReportError] = useState("");
    const [message, setMessage] = useState("");
    const [alertsError, setAlertsError] = useState("");
    const [busy, setBusy] = useState(false);
    const [correctingFuel, setCorrectingFuel] = useState<string | null>(null);
    const [moneyTripId, setMoneyTripId] = useState<string | null>(null);
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
        if (path === "/fleet/trips") {
            for (const field of ["customer_reference", "origin", "destination", "starts_at", "odometer_start"])
                if (data[field] === "") delete data[field];
        }
        try {
            await send(path, "POST", data);
            formElement.reset();
            if (path === "/fleet/vehicles") setVehicleFormOpen(false);
            if (path === "/fleet/drivers") setDriverFormOpen(false);
            try {
                await refresh();
                setMessage(path === "/fleet/trips" ? "Trip created and ready for dispatch." : "Saved successfully.");
            } catch {
                setMessage(path === "/fleet/trips" ? "Trip created, but the page could not refresh. Refresh before continuing." : "Saved successfully, but the page could not refresh. Refresh before continuing.");
            }
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
        const odometerEnd = action === "complete" ? (await requestInput("Truck reading when delivery is finished (optional):")) : null;
        if (action === "complete" && odometerEnd === null)
            return;
        const labels = { start: "Truck arrival recorded.", load: "Goods marked as loaded.", complete: "Delivery marked finished.", submit: "Trip sent for approval.", approve: "Trip approved.", reject: "Changes requested." };
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
    const filteredAlerts = alerts.filter(alert => `${alertTypeLabel[alert.kind] || alert.kind} ${alert.trip_number || ""} ${alert.truck || ""} ${alert.message}`.toLowerCase().includes(alertSearch.trim().toLowerCase()));
    const pageMeta: Record<string, { eyebrow: string; title: string; description: string }> = {
        overview: { eyebrow: "Operations", title: "Fleet control center", description: "A live view of vehicles, trips, and the work that needs attention." },
        "fleet-setup": { eyebrow: "Fleet directory", title: "Trucks & drivers", description: "Manage the vehicles and people available to your operation." },
        "trip-create": { eyebrow: "Dispatch", title: "Plan a trip", description: "Assign an available truck and driver to a customer movement." },
        trips: { eyebrow: "Operations", title: "Trips", description: "See where each truck is, what needs doing next, and which trips are finished." },
        alerts: { eyebrow: "Operations", title: "Trip alerts", description: "See what needs checking across trips, fuel, and trucks." },
        "follow-ups": { eyebrow: "Operations", title: "Open follow-ups", description: "Resolve missing evidence and costs that need an operator decision." },
        "trip-reports": { eyebrow: "Insights", title: "Trip profitability", description: "Compare approved trip revenue, costs, and margin over time." },
        "driver-salaries": { eyebrow: "Finance", title: "Driver settlements", description: "Review driver earnings, approved payments, and outstanding balances." },
    };
    const currentPage = pageMeta[focusSection] || pageMeta.overview;
    const overviewCards = [
        { label: "Active trucks", value: dashboard ? dashboard.active_vehicles : "—", icon: Truck, tone: "text-slate-900", accent: "bg-slate-100 text-slate-700" },
        { label: "Active drivers", value: dashboard ? dashboard.active_drivers : "—", icon: UsersRound, tone: "text-slate-900", accent: "bg-slate-100 text-slate-700" },
        { label: "Trips underway", value: dashboard ? dashboard.trips_in_progress : "—", icon: Route, tone: "text-slate-900", accent: "bg-emerald-50 text-emerald-700" },
        { label: "Awaiting review", value: dashboard ? dashboard.trips_awaiting_review : "—", icon: ClipboardList, tone: dashboard?.trips_awaiting_review ? "text-amber-700" : "text-slate-900", accent: "bg-amber-50 text-amber-700" },
        { label: "Approved balance", value: dashboard ? `₹${dashboard.approved_trip_margin}` : "—", icon: ArrowUpRight, tone: "text-emerald-700", accent: "bg-emerald-50 text-emerald-700" },
    ];
    const tripRegisterRows = trips.filter(trip => {
        const search = tripSearch.trim().toLowerCase();
        const matchesSearch = !search || [trip.trip_number, trip.vehicle.registration_number, trip.driver.name, trip.origin, trip.destination, trip.transport_order?.order_number, trip.transport_order?.customer_name].some(value => value?.toLowerCase().includes(search));
        const matchesStatus = !tripStatusFilter || (tripStatusFilter === "NEEDS_ACTION" ? ["COMPLETED", "REJECTED"].includes(trip.status) : trip.status === tripStatusFilter);
        return matchesSearch && matchesStatus;
    });
    const tripPage = useListPagination(tripRegisterRows, `${JSON.stringify(filters)}:${focusSection}:${tripSearch}:${tripStatusFilter}`);
    const etaEvaluations = trips.filter(trip => trip.eta_error_minutes !== null && trip.eta_error_minutes !== undefined);
    const averageEtaError = etaEvaluations.length ? etaEvaluations.reduce((total, trip) => total + Math.abs(trip.eta_error_minutes || 0), 0) / etaEvaluations.length : null;
    const filteredFollowUps = activeFollowUps.filter(item => (!followUpStatusFilter || item.status === followUpStatusFilter) && `${followUpCategoryLabel[item.category] || item.category.replace(/^DRIVER_/, "").replaceAll("_", " ")} ${item.description} ${item.trip_number || ""} ${item.truck || ""} ${item.driver_name || ""}`.toLowerCase().includes(followUpSearch.trim().toLowerCase()));
    const followUpPage = useListPagination(filteredFollowUps);
    const salaryPage = useListPagination(salaryRecords);
    if (initialLoading) return <PageSkeleton variant="cards" label="Loading fleet operations" />;
    if (focusSection === "overview") {
      const workItems = [
        { label: "Trips awaiting review", value: dashboard?.trips_awaiting_review ?? "—", href: "/fleet/trips" },
        { label: "Open follow-ups", value: dashboard?.open_follow_ups ?? "—", href: "/fleet/follow-ups" },
        { label: "Driver payments remaining", value: dashboard ? `₹${dashboard.driver_salary_remaining}` : "—", href: "/fleet/driver-salaries" },
      ].filter(item => canShowNavigation(item.href, navigationAccess));
      const quickLinks = [
        { label: "Fleet directory", href: "/fleet/trucks", icon: Truck },
        { label: "Maintenance", href: "/fleet/maintenance", icon: Wrench },
        { label: "Fuel and trip costs", href: "/fleet/operational-reports", icon: Fuel },
      ].filter(item => canShowNavigation(item.href, navigationAccess));
      return <UiMain className="fleet-control-center flex w-full min-w-0 flex-col gap-3 px-3 py-3 sm:px-4">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-2">
          <UiH1 className="text-2xl font-bold tracking-tight text-ink">Fleet control center</UiH1>
          {canShowNavigation("/fleet/dispatch", navigationAccess) && <Link href="/fleet/dispatch" className="inline-flex items-center gap-2 rounded-lg bg-forest px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800"><Route size={15} />Open dispatch</Link>}
        </header>

        <UiSection aria-label="Fleet performance snapshot" className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          {overviewCards.map(metric => {
            const Icon = metric.icon;
            return <UiArticle key={metric.label} className="flex min-w-0 items-center gap-2.5 rounded-lg border border-line bg-white px-3 py-2">
              <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${metric.accent}`}><Icon size={16} aria-hidden /></span>
              <div className="min-w-0"><p className="text-xs font-medium text-slate-600">{metric.label}</p><p className={`text-lg font-bold leading-tight tabular-nums ${metric.tone}`}>{metric.value}</p></div>
            </UiArticle>;
          })}
        </UiSection>

        {message && <div role="status" className="shrink-0 rounded-md border border-line bg-white px-3 py-2 text-xs">{message}</div>}

        <div className="grid min-h-0 min-w-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(300px,29%)]">
          <section aria-label="Live operations" className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-line bg-white">
            <header className="flex shrink-0 items-center justify-between gap-2 border-b border-line px-3 py-2">
              <UiH2 className="text-base font-bold text-ink">Live operations</UiH2>
              {trackingAccess && <Link href="/fleet/live-tracking" className="inline-flex items-center gap-1 text-xs font-semibold text-forest">Open live tracking <ArrowUpRight size={14} /></Link>}
            </header>
            {trackingAccess
              ? <FleetLiveMap compact fitPanel vehicles={trackingTrips} selectedTripId={selectedTrackingTrip} onSelect={setSelectedTrackingTrip} />
              : <div className="grid min-h-48 flex-1 place-items-center px-4 py-8 text-center"><div><MapPin size={22} className="mx-auto text-slate-500" /><p className="mt-2 text-sm font-semibold">Live map unavailable</p><p className="mt-1 text-xs text-slate-600">{trackingMessage || "Your role does not have access to live locations."}</p></div></div>}
            {trackingAccess && trackingTrips.length > 0 && <div aria-label="Select a truck on the map" className="flex shrink-0 gap-2 overflow-x-auto border-t border-line px-3 py-2">
              {trackingTrips.slice(0, 4).map(trip => <button key={trip.trip_id} type="button" onClick={() => setSelectedTrackingTrip(trip.trip_id)} aria-pressed={trip.trip_id === selectedTrackingTrip}
                className="inline-flex shrink-0 items-center gap-2 rounded-md border border-line px-2 py-1 text-xs font-semibold hover:bg-slate-50 aria-pressed:border-emerald-700 aria-pressed:bg-emerald-50">
                {trip.vehicle}<span className={trip.status === "LIVE" ? "text-emerald-700" : "text-amber-800"}>{trip.status === "LIVE" ? "Live" : trip.status === "STALE" ? "Out of date" : "No GPS yet"}</span>
              </button>)}
            </div>}
          </section>

          <div className="flex min-h-0 min-w-0 flex-col gap-3">
            <section aria-label="Work queue" className="shrink-0 rounded-xl border border-line bg-white px-3 py-2.5">
              <header className="mb-1 flex items-center gap-2"><ClipboardList size={16} className="text-forest" aria-hidden /><UiH2 className="text-base font-bold text-ink">Work queue</UiH2></header>
              <div className="divide-y divide-slate-100">
                {workItems.map(item => <Link key={item.href} href={item.href} className="flex items-center gap-2 py-1.5 text-sm hover:text-forest">
                  <span className="flex-1">{item.label}</span><strong className="shrink-0 tabular-nums">{item.value}</strong><ArrowUpRight size={13} aria-hidden />
                </Link>)}
                {workItems.length === 0 && <p className="py-1 text-sm text-slate-600">No work queues available for your role.</p>}
              </div>
            </section>

            <section aria-label="Fleet alerts" className="flex min-h-0 min-w-0 flex-1 flex-col rounded-xl border border-line bg-white px-3 py-2.5">
              <header className="mb-2 flex shrink-0 items-center gap-2">
                <CircleAlert size={16} className="text-amber-700" aria-hidden /><UiH2 className="flex-1 text-base font-bold text-ink">Alerts to check</UiH2>
                {!alertsError && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800">{alerts.length}</span>}
                {canShowNavigation("/fleet/alerts", navigationAccess) && <Link href="/fleet/alerts" className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-forest">See all <ArrowUpRight size={13} /></Link>}
              </header>
              {alertsError ? <p role="alert" className="rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-900">{alertsError}</p> : alerts.length
                ? <ul tabIndex={0} aria-label="Alerts to check" className="min-h-0 max-h-96 space-y-1.5 overflow-y-auto pr-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest lg:max-h-none">
                  {alerts.map(alert => <li key={alert.id} className="rounded-md border border-amber-100 bg-amber-50/50 px-2.5 py-1.5">
                    <p className="text-xs font-bold text-amber-900">{alertTypeLabel[alert.kind] || alert.kind.replaceAll("_", " ")}{alert.trip_number ? ` · ${alert.trip_number}` : alert.truck ? ` · ${alert.truck}` : ""}</p>
                    <p className="mt-0.5 line-clamp-2 text-xs leading-4 text-slate-700">{alert.message}</p>
                  </li>)}
                </ul>
                : <p className="rounded-md bg-emerald-50 px-2.5 py-2 text-sm text-emerald-800">No alerts need checking.</p>}
            </section>
          </div>
        </div>

        <footer className="flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 [&>div]:mt-0">
          <nav aria-label="Fleet quick links" className="flex flex-wrap items-center gap-3">
            {quickLinks.map(item => <Link key={item.href} href={item.href} className="inline-flex items-center gap-1 text-xs font-semibold text-forest"><item.icon size={14} aria-hidden />{item.label}</Link>)}
          </nav>
          <LiveData onRefresh={refresh} paused={busy} interval={60000} compact />
        </footer>
      </UiMain>;
    }
    return <UiMain className="w-full min-w-0 px-4 py-7 sm:px-6 lg:px-8">
      <UiBox className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <UiBox>
          <UiText className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-500">{currentPage.eyebrow}</UiText>
          <UiH1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">{currentPage.title}</UiH1>
          <UiText className="mt-1 max-w-2xl text-sm text-slate-500">{currentPage.description}</UiText>
        </UiBox>
        <UiBox className="flex flex-wrap items-center gap-2">

          <UiButton type="button" onClick={() => void refresh()} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"><RefreshCw size={14}/>{busy ? "Refreshing" : "Refresh data"}</UiButton>
        </UiBox>
      </UiBox>
      {focusSection === "alerts" && <LiveData onRefresh={refresh} paused={busy} interval={60000} compact/>}
      {alertsError && focusSection === "alerts" && <UiBox role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><span>{alertsError}</span><UiButton type="button" onClick={() => void refresh().catch(() => setAlertsError("Fleet alerts could not be loaded. Check the connection and retry."))} className="font-semibold underline">Retry</UiButton></UiBox>}
      {message && <UiBox role="status" className="mb-5 rounded-lg border border-line bg-white px-4 py-3 text-sm text-slate-700">{message}</UiBox>}

      {focusSection === "alerts" && <>
        <UiSection aria-label="Alert summary" className="mb-5 grid gap-3 sm:grid-cols-3">
          {[{ label: "Alerts to review", value: alerts.length, tone: "text-amber-700", mark: "bg-amber-100" }, { label: "Trip alerts", value: alerts.filter(alert => Boolean(alert.trip_id)).length, tone: "text-slate-900", mark: "bg-slate-100" }, { label: "Truck alerts", value: alerts.filter(alert => Boolean(alert.vehicle_id)).length, tone: "text-slate-900", mark: "bg-slate-100" }].map(item => <UiArticle key={item.label} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4"><span className={`grid size-10 place-items-center rounded-lg ${item.mark}`}><CircleAlert size={18} className={item.tone}/></span><UiBox><UiText className="text-xs text-slate-500">{item.label}</UiText><UiText className={`mt-1 text-2xl font-bold tabular-nums ${item.tone}`}>{item.value}</UiText></UiBox></UiArticle>)}
        </UiSection>
        <UiSection aria-label="Find alerts" className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4"><UiBox className="min-w-48 flex-1"><UiLabel className="text-xs font-semibold text-slate-600">Find an alert<UiInput className={`${inputClass} mt-1`} value={alertSearch} onChange={event => setAlertSearch(event.target.value)} placeholder="Trip number, truck, or problem" aria-label="Search alerts"/></UiLabel></UiBox><UiText className="text-xs text-slate-500">{filteredAlerts.length} shown</UiText>{alertSearch && <UiButton type="button" onClick={() => setAlertSearch("")} className="rounded-lg border border-line px-3 py-2 text-sm">Clear search</UiButton>}</UiSection>
        <UiSection aria-label="Fleet alerts" className="space-y-3">{filteredAlerts.map(alert => { const vehicleAlert = Boolean(alert.vehicle_id); const href = alert.kind === "TRUCK_MAINTENANCE_DUE" ? "/fleet/maintenance" : vehicleAlert ? "/fleet/trucks" : "/fleet/trips"; return <UiArticle key={alert.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><UiBox className="flex flex-wrap items-start justify-between gap-4 p-4 sm:p-5"><UiBox className="flex min-w-0 flex-1 items-start gap-3"><span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-amber-50 text-amber-700"><CircleAlert size={17}/></span><UiBox className="min-w-0"><UiBox className="flex flex-wrap items-center gap-2"><UiH3 className="text-sm font-semibold text-slate-900">{alertTypeLabel[alert.kind] || alert.kind.replaceAll("_", " ")}</UiH3><UiSpan className="rounded-full bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-800">Check this</UiSpan></UiBox><UiText className="mt-1 text-xs leading-5 text-slate-600">{alert.message}</UiText><UiText className="mt-2 text-[11px] font-medium text-slate-500">{alert.trip_number ? `Trip ${alert.trip_number}` : alert.truck ? `Truck ${alert.truck}` : "Fleet alert"}</UiText></UiBox></UiBox><Link href={href} className="ml-12 inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 sm:ml-0">{alert.kind === "TRUCK_MAINTENANCE_DUE" ? "Open maintenance" : vehicleAlert ? "Open trucks" : "Open trips"}<ArrowUpRight size={14}/></Link></UiBox></UiArticle>; })}{filteredAlerts.length === 0 && <UiBox className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-12 text-center"><UiText className="text-sm font-semibold text-slate-800">{alertSearch ? "No alerts found" : "All clear"}</UiText><UiText className="mt-1 text-xs text-slate-500">{alertSearch ? "Try a different trip number, truck, or problem." : "There are no trip or truck alerts to review right now."}</UiText>{alertSearch && <UiButton type="button" onClick={() => setAlertSearch("")} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">Clear search</UiButton>}</UiBox>}</UiSection>
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
    <UiSection id="trip-create" className="mb-7 overflow-hidden rounded-xl border border-line bg-white">
      <UiForm onSubmit={e => void submitForm(e, "/fleet/trips")}>
        <UiBox className="border-b border-line px-5 py-4 sm:px-6"><UiH2 className="text-base font-bold">Trip details</UiH2><UiText className="mt-1 text-sm text-slate-500">Pick an active truck and driver. Link an order to fill the route automatically.</UiText></UiBox>
        <UiBox className="grid gap-x-8 gap-y-6 p-5 sm:grid-cols-2 sm:p-6">
          <UiBox className="space-y-3"><UiBox><UiH3 className="text-xs font-bold uppercase tracking-wide text-slate-500">Booking</UiH3><UiText className="mt-1 text-xs text-slate-400">Use an existing order or create a trip without one.</UiText></UiBox>
            <UiLabel className="block text-xs font-semibold text-slate-600">Trip number<UiInput className={`${inputClass} mt-1`} name="trip_number" required maxLength={64} placeholder="e.g. TRIP-1042"/></UiLabel>
            <UiLabel className="block text-xs font-semibold text-slate-600">Transport order <UiSpan className="font-normal text-slate-400">· optional</UiSpan><UiSelect className={`${inputClass} mt-1`} name="transport_order_id" defaultValue=""><option value="">No order linked</option>{orders.map(order => <option key={order.id} value={order.id}>{order.order_number} · {order.customer.name} · {order.origin} → {order.destination}</option>)}</UiSelect><UiText className="mt-1 block text-[10px] font-normal text-slate-500">Linked orders supply the customer reference and route when those fields are left blank.</UiText></UiLabel>
            <UiLabel className="block text-xs font-semibold text-slate-600">Customer reference <UiSpan className="font-normal text-slate-400">· optional</UiSpan><UiInput className={`${inputClass} mt-1`} name="customer_reference" maxLength={120} placeholder="Booking or customer reference"/></UiLabel>
          </UiBox>
          <UiBox className="space-y-3"><UiBox><UiH3 className="text-xs font-bold uppercase tracking-wide text-slate-500">Assignment</UiH3><UiText className="mt-1 text-xs text-slate-400">Only active resources in this workspace can be assigned.</UiText></UiBox>
            <UiLabel className="block text-xs font-semibold text-slate-600">Truck<UiSelect className={`${inputClass} mt-1`} name="vehicle_id" required defaultValue=""><option value="" disabled>Select a truck</option>{vehicles.filter(v => v.status === "ACTIVE").map(v => <option key={v.id} value={v.id}>{v.registration_number}{v.make_model ? ` · ${v.make_model}` : ""}</option>)}</UiSelect></UiLabel>
            <UiLabel className="block text-xs font-semibold text-slate-600">Driver<UiSelect className={`${inputClass} mt-1`} name="driver_id" required defaultValue=""><option value="" disabled>Select a driver</option>{drivers.filter(d => d.status === "ACTIVE").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</UiSelect></UiLabel>
          </UiBox>
          <UiBox className="space-y-3"><UiBox><UiH3 className="text-xs font-bold uppercase tracking-wide text-slate-500">Route</UiH3><UiText className="mt-1 text-xs text-slate-400">If an order is linked, its pickup and delivery locations are used by default.</UiText></UiBox>
            <UiLabel className="block text-xs font-semibold text-slate-600">Pickup location <UiSpan className="font-normal text-slate-400">· optional</UiSpan><UiInput className={`${inputClass} mt-1`} name="origin" maxLength={240} placeholder="City, address, or site"/></UiLabel>
            <UiLabel className="block text-xs font-semibold text-slate-600">Delivery location <UiSpan className="font-normal text-slate-400">· optional</UiSpan><UiInput className={`${inputClass} mt-1`} name="destination" maxLength={240} placeholder="City, address, or site"/></UiLabel>
          </UiBox>
          <UiBox className="space-y-3"><UiBox><UiH3 className="text-xs font-bold uppercase tracking-wide text-slate-500">Timing & odometer</UiH3><UiText className="mt-1 text-xs text-slate-400">Add these when known; they can also be recorded during trip check-in.</UiText></UiBox>
            <UiLabel className="block text-xs font-semibold text-slate-600">Planned start <UiSpan className="font-normal text-slate-400">· optional</UiSpan><UiInput className={`${inputClass} mt-1`} type="datetime-local" name="starts_at"/></UiLabel>
            <UiLabel className="block text-xs font-semibold text-slate-600">Starting odometer (km) <UiSpan className="font-normal text-slate-400">· optional</UiSpan><UiInput className={`${inputClass} mt-1`} name="odometer_start" type="number" min="0" step="0.1" placeholder="Truck reading at departure"/></UiLabel>
          </UiBox>
        </UiBox>
        {(!vehicles.some(v => v.status === "ACTIVE") || !drivers.some(d => d.status === "ACTIVE")) && <UiBox role="status" className="mx-5 mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900 sm:mx-6"><UiText><UiStrong className="font-semibold">Assignment setup needed.</UiStrong> Add at least one active truck and one active driver before creating a trip.</UiText><Link href="/fleet/trucks" className="font-semibold text-forest">Open fleet directory →</Link></UiBox>}
        <UiBox className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-slate-50/70 px-5 py-4 sm:px-6"><UiText className="text-xs text-slate-500">The trip starts in draft. Dispatch check-in begins the operational timeline.</UiText><UiButton disabled={busy || !vehicles.some(v => v.status === "ACTIVE") || !drivers.some(d => d.status === "ACTIVE")} className="inline-flex items-center gap-2 rounded-lg bg-forest px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Creating trip…" : "Create trip"}</UiButton></UiBox>
      </UiForm>
    </UiSection>
    </>}

    {(!focusSection || focusSection === 'follow-ups') && <>
    <UiSection id="follow-ups" className="mb-7">
      <UiBox className="mb-4 flex flex-wrap items-end justify-between gap-3"><UiBox><UiH2 className="text-lg font-semibold">Issues to resolve</UiH2><UiText className="mt-1 text-sm text-slate-500">Each item explains what needs attention and which trip it belongs to.</UiText></UiBox><UiSpan className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800">{activeFollowUps.length} open</UiSpan></UiBox>
      <UiSection aria-label="Find and filter follow-ups" className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-white p-4"><UiLabel className="min-w-56 flex-1 text-xs font-semibold text-slate-600">Search issues<UiInput className={`${inputClass} mt-1`} value={followUpSearch} onChange={event => setFollowUpSearch(event.target.value)} placeholder="Issue, trip, truck, or driver" aria-label="Search follow-ups"/></UiLabel><UiLabel className="text-xs font-semibold text-slate-600">Show<UiSelect className={`${inputClass} mt-1 min-w-44`} value={followUpStatusFilter} onChange={event => setFollowUpStatusFilter(event.target.value)} aria-label="Filter follow-ups"><option value="">All open issues</option><option value="OPEN">Not started</option><option value="IN_PROGRESS">In progress</option></UiSelect></UiLabel>{(followUpSearch || followUpStatusFilter) && <UiButton type="button" onClick={() => { setFollowUpSearch(""); setFollowUpStatusFilter(""); }} className="rounded-lg border border-line px-3 py-2 text-sm">Clear</UiButton>}</UiSection>
      <UiBox className="grid gap-3 lg:grid-cols-2">{followUpPage.rows.map(item => { const overdue = item.due_at && new Date(item.due_at).getTime() < Date.now(); return <UiArticle key={item.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><UiBox className="p-4 sm:p-5"><UiBox className="flex flex-wrap items-center justify-between gap-2"><UiSpan className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-800">{followUpCategoryLabel[item.category] || item.category.replace(/^DRIVER_/, "").replaceAll("_", " ")}</UiSpan><UiSpan className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${item.status === "IN_PROGRESS" ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-600"}`}>{item.status === "IN_PROGRESS" ? "In progress" : "Not started"}</UiSpan></UiBox>
        <UiText className="mt-3 text-sm font-semibold leading-5 text-slate-900">{item.description}</UiText>
        {(item.trip_number || item.truck || item.driver_name) ? <UiBox className="mt-3 flex flex-wrap gap-x-4 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">{item.trip_number && <UiText><UiStrong>Trip</UiStrong> {item.trip_number}</UiText>}{item.truck && <UiText><UiStrong>Truck</UiStrong> {item.truck}</UiText>}{item.driver_name && <UiText><UiStrong>Driver</UiStrong> {item.driver_name}</UiText>}</UiBox> : <UiText className="mt-3 text-xs text-slate-500">No trip linked</UiText>}
        <UiBox className="mt-3 flex flex-wrap items-center justify-between gap-2">{item.due_at ? <UiText className={`text-xs font-medium ${overdue ? "text-rose-700" : "text-slate-500"}`}>{overdue ? "Past due" : "Due"} · {new Date(item.due_at).toLocaleDateString()}</UiText> : <UiText className="text-xs text-slate-400">No due date</UiText>}{item.resolution_note && <UiText className="text-xs text-slate-500">Last note: {item.resolution_note}</UiText>}</UiBox>
        <UiBox className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">{item.status === "OPEN" && <UiButton onClick={() => void followUpAction(item, "start")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">Start work</UiButton>}<UiButton onClick={() => void followUpAction(item, "resolve")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Mark resolved</UiButton><UiButton onClick={() => void followUpAction(item, "waive")} className="rounded-lg px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50">Waive</UiButton></UiBox></UiBox></UiArticle>; })}{filteredFollowUps.length === 0 && <UiBox className="rounded-xl border border-dashed border-slate-300 bg-white px-5 py-12 text-center lg:col-span-2"><UiText className="text-sm font-semibold text-slate-800">{activeFollowUps.length === 0 ? "All caught up" : "No issues found"}</UiText><UiText className="mt-1 text-xs text-slate-500">{activeFollowUps.length === 0 ? "There are no open follow-ups to handle." : "Try another search or show all open issues."}</UiText>{(followUpSearch || followUpStatusFilter) && <UiButton type="button" onClick={() => { setFollowUpSearch(""); setFollowUpStatusFilter(""); }} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold">Clear filters</UiButton>}</UiBox>}</UiBox>{followUpPage.controls}
    </UiSection>    </>}

    {false && <>
    <UiSection id="driver-salaries" className="mb-7"><UiBox className="mb-3"><UiH2 className="text-lg font-semibold">Driver salary and payments</UiH2><UiText className="mt-1 text-sm text-slate-500">Record the salary owed for a month, then add one or more payments. The remaining balance updates automatically.</UiText></UiBox>
      <UiForm className={`${cardClass} mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_2fr_auto] lg:items-end`} onSubmit={createSalaryRecord}><UiLabel className="text-xs text-slate-500">Driver<UiSelect className={inputClass} name="driver_id" required defaultValue=""><option value="" disabled>Select driver</option>{drivers.filter(d => d.status === "ACTIVE").map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Salary month<UiInput className={inputClass} name="period_start" type="month" required/></UiLabel><UiLabel className="text-xs text-slate-500">Salary owed<UiInput className={inputClass} name="salary_amount" type="number" min="0.01" step="0.01" placeholder="₹ amount" required/></UiLabel><UiLabel className="text-xs text-slate-500">Note <UiSpan className="text-slate-400">(optional)</UiSpan><UiInput className={inputClass} name="notes" placeholder="Monthly salary, trip allowance, etc."/></UiLabel><UiButton disabled={busy || !drivers.some(d => d.status === "ACTIVE")} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Record salary</UiButton></UiForm>
      <UiBox className="space-y-3">{salaryPage.rows.map(record => <UiArticle key={record.id} className={cardClass}><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiH3 className="font-semibold">{record.driver.name} · {new Date(`${record.period_start}T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" })}</UiH3><UiText className="mt-1 text-sm text-slate-500">Salary ₹{record.salary_amount} · Paid ₹{record.paid_amount} · <UiSpan className="font-semibold text-ink">Remaining ₹{record.remaining_amount}</UiSpan></UiText>{record.notes && <UiText className="mt-1 text-xs text-slate-500">{record.notes}</UiText>}</UiBox>{Number(record.remaining_amount) > 0 && <UiForm className="flex flex-wrap gap-2" onSubmit={e => void paySalary(e, record)}><UiInput className="w-28 rounded-lg border border-line px-3 py-2 text-sm" name="amount" type="number" min="0.01" max={record.remaining_amount} step="0.01" placeholder="₹ payment" required/><UiInput className="w-36 rounded-lg border border-line px-3 py-2 text-sm" name="payment_date" type="date" required defaultValue={localToday()} aria-label="Payment date"/><UiInput className="w-40 rounded-lg border border-line px-3 py-2 text-sm" name="payment_reference" placeholder="Reference (optional)"/><UiButton disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Record payment</UiButton></UiForm>}</UiBox>{record.payments.length > 0 && <UiBox className="mt-3 border-t border-line pt-3 text-xs text-slate-500">{record.payments.map(payment => <UiText key={payment.id} className="mt-1 flex justify-between gap-3"><UiSpan>Payment · {payment.payment_date}{payment.payment_reference ? ` · ${payment.payment_reference}` : ""}</UiSpan><UiSpan>₹{payment.amount}</UiSpan></UiText>)}</UiBox>}</UiArticle>)}{salaryRecords.length === 0 && <EmptyState description="No salary records yet. Add a driver’s monthly salary above to start tracking payments." onAction={()=>void refresh()} actionLabel="Refresh data" />}</UiBox>
    {salaryPage.controls}</UiSection>
    </>}

    {(!focusSection || focusSection === 'trip-reports') && <>
    <UiSection id="trip-reports" className="mb-7"><UiBox className="mb-3"><UiH2 className="text-lg font-semibold">Trip reports</UiH2><UiText className="mt-1 text-sm text-slate-500">Income, costs, and margin from approved actual amounts only.</UiText></UiBox><UiForm className={`${cardClass} mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4`} onSubmit={applyTripFilters}><UiLabel className="text-xs text-slate-500">From date<UiInput className={inputClass} type="date" value={filterInputs.date_from} onChange={e => updateTripFilter("date_from", e.target.value)}/></UiLabel><UiLabel className="text-xs text-slate-500">To date<UiInput className={inputClass} type="date" value={filterInputs.date_to} onChange={e => updateTripFilter("date_to", e.target.value)}/></UiLabel><UiLabel className="text-xs text-slate-500">Truck<UiSelect aria-label="Filter truck" className={inputClass} value={filterInputs.vehicle_id} onChange={e => updateTripFilter("vehicle_id", e.target.value)}><option value="">All trucks</option>{vehicles.map(vehicle => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration_number}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Driver<UiSelect aria-label="Filter driver" className={inputClass} value={filterInputs.driver_id} onChange={e => updateTripFilter("driver_id", e.target.value)}><option value="">All drivers</option>{drivers.map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}</UiSelect></UiLabel><UiLabel className="text-xs text-slate-500">Search trip, route, or customer<UiInput className={inputClass} value={filterInputs.search} onChange={e => updateTripFilter("search", e.target.value)} placeholder="Trip no., route, customer"/></UiLabel><UiLabel className="text-xs text-slate-500">Trip status<UiSelect className={inputClass} value={filterInputs.status} onChange={e => updateTripFilter("status", e.target.value)}><option value="">All statuses</option><option value="DRAFT">Draft</option><option value="IN_PROGRESS">In progress</option><option value="COMPLETED">Completed</option><option value="SUBMITTED">Waiting for review</option><option value="APPROVED">Approved</option><option value="REJECTED">Changes requested</option></UiSelect></UiLabel><UiBox className="flex items-end gap-2"><UiButton className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">Apply filters</UiButton><UiButton className="rounded-lg border border-line px-4 py-2 text-sm" type="button" onClick={clearTripFilters}>Clear</UiButton></UiBox></UiForm>
      {reportError && <UiAlert role="alert" className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{reportError}</UiAlert>}{tripReport && <><UiBox className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[["Approved trips", tripReport.trip_count], ["Approved earnings", `₹${tripReport.income}`], ["Approved costs", `₹${tripReport.costs}`], ["Approved margin", `₹${tripReport.margin}`], ["Budget overruns", `₹${tripReport.budget_overrun_total}`]].map(([label, value]) => <UiBox className={cardClass} key={label}><UiText className="text-xs text-slate-500">{label}</UiText><UiText className="mt-2 text-xl font-bold text-ink">{value}</UiText>{label === "Budget overruns" && <UiText className="mt-1 text-[11px] text-slate-500">Budgeted lines only</UiText>}</UiBox>)}</UiBox><UiBox className="grid gap-4 lg:grid-cols-3">{reportTable("By driver", tripReport.by_driver)}{reportTable("By truck", tripReport.by_truck)}{reportTable("By month", tripReport.by_month)}</UiBox><UiBox className="mt-4 overflow-hidden rounded-lg border border-line"><UiBox className="border-b border-line bg-slate-50 px-3 py-2"><UiH3 className="text-sm font-semibold">Approved costs by category</UiH3><UiText className="mt-1 text-xs text-slate-500">Budgeted totals include only costs with a budget. Overrun is the positive difference on each budgeted cost line.</UiText></UiBox>{tripReport.by_cost_category.length === 0 ? <EmptyState description="No approved cost lines for this selection." onAction={()=>void refresh()} actionLabel="Refresh data" /> : <UiBox className="overflow-x-auto"><UiTable className="w-full min-w-[650px] text-left text-xs"><UiTableHead className="text-slate-500"><UiTableRow><UiTh className="px-3 py-2">Category</UiTh><UiTh className="px-3 py-2">Trips</UiTh><UiTh className="px-3 py-2">Actual costs</UiTh><UiTh className="px-3 py-2">Budgeted costs</UiTh><UiTh className="px-3 py-2">Over budget</UiTh></UiTableRow></UiTableHead><UiTableBody>{tripReport.by_cost_category.map(row => <UiTableRow key={row.id} className="border-t border-line"><UiTd className="px-3 py-2 font-medium">{row.name}</UiTd><UiTd className="px-3 py-2">{row.trips}</UiTd><UiTd className="px-3 py-2">₹{row.actual}</UiTd><UiTd className="px-3 py-2">₹{row.budgeted}</UiTd><UiTd className="px-3 py-2">₹{row.over_budget}</UiTd></UiTableRow>)}</UiTableBody></UiTable></UiBox>}</UiBox></>}</UiSection>
    </>}

    {(!focusSection || focusSection === 'trips') && <>
    {averageEtaError !== null && <UiArticle className={`${cardClass} mb-4`}><UiText className="text-xs font-semibold text-slate-500">Past delivery estimate difference</UiText><UiText className="mt-1 text-xl font-bold">{averageEtaError.toFixed(0)} min</UiText><UiText className="mt-1 text-xs text-slate-500">Past deliveries differed from estimates by an average of {averageEtaError.toFixed(0)} minutes across {etaEvaluations.length} trips.</UiText></UiArticle>}
    <UiSection aria-label="Trips by progress" className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">{[
      { label: "All trips", value: trips.length, note: "See every trip", filter: "", tone: "slate" },
      { label: "To start", value: trips.filter(trip => trip.status === "DRAFT").length, note: "Truck has not left yet", filter: "DRAFT", tone: "blue" },
      { label: "On the road", value: trips.filter(trip => trip.status === "IN_PROGRESS").length, note: "Trip is in progress", filter: "IN_PROGRESS", tone: "green" },
      { label: "Needs attention", value: trips.filter(trip => ["COMPLETED", "REJECTED"].includes(trip.status)).length, note: "Finish or fix this trip", filter: "NEEDS_ACTION", tone: "amber" },
      { label: "With manager", value: trips.filter(trip => trip.status === "SUBMITTED").length, note: "Waiting for a decision", filter: "SUBMITTED", tone: "violet" },
      { label: "Finished", value: trips.filter(trip => trip.status === "APPROVED").length, note: "Approved and complete", filter: "APPROVED", tone: "emerald" },
    ].map(item => { const selected = tripStatusFilter === item.filter; const tones: Record<string, string> = { slate: "bg-slate-400", blue: "bg-blue-500", green: "bg-emerald-500", amber: "bg-amber-500", violet: "bg-violet-500", emerald: "bg-emerald-500" }; return <button key={item.label} type="button" aria-pressed={selected} onClick={() => setTripStatusFilter(selected && item.filter ? "" : item.filter)} className={`group min-h-28 rounded-xl border bg-white p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-forest ${selected ? "border-forest shadow-sm ring-1 ring-forest" : "border-line hover:border-slate-300"}`}><span className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${tones[item.tone]}`} aria-hidden="true"/><span className="text-sm font-semibold text-slate-700">{item.label}</span></span><span className="mt-3 block text-3xl font-bold leading-none tabular-nums text-slate-950">{item.value}</span><span className="mt-2 block text-xs text-slate-500">{item.note}</span></button>})}</UiSection>
    <UiSection aria-label="Find a trip" className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-white p-4"><UiLabel className="min-w-56 flex-1 text-xs font-semibold">Find a trip<UiInput className={`${inputClass} mt-1`} value={tripSearch} onChange={event => setTripSearch(event.target.value)} placeholder="Trip number, driver, truck, or place" aria-label="Find a trip"/></UiLabel><UiLabel className="text-xs font-semibold">Show<UiSelect className={`${inputClass} mt-1 min-w-48`} value={tripStatusFilter} onChange={event => setTripStatusFilter(event.target.value)} aria-label="Filter trips by status"><option value="">All trips</option><option value="DRAFT">Not started</option><option value="IN_PROGRESS">On the road</option><option value="COMPLETED">Delivery finished</option><option value="SUBMITTED">Waiting for manager</option><option value="REJECTED">Needs changes</option><option value="NEEDS_ACTION">Needs attention</option><option value="APPROVED">Finished</option></UiSelect></UiLabel>{(tripSearch || tripStatusFilter) && <UiButton type="button" onClick={() => { setTripSearch(""); setTripStatusFilter(""); }} className="rounded-lg border border-line px-3 py-2 text-sm">Clear</UiButton>}</UiSection>
    <UiSection id="trips"><UiBox className="mb-3 flex items-center justify-between"><UiBox><UiH2 className="text-lg font-semibold">All trips</UiH2><UiText className="mt-1 text-sm text-slate-500">Search by trip number, driver, truck, or place. Open a trip to see what to do next.</UiText></UiBox><UiSpan className="text-xs text-slate-500">{tripRegisterRows.length} trips shown</UiSpan></UiBox><UiBox className="space-y-4"><CollectionExplorer rows={tripRegisterRows.map((trip,index)=>({id:trip.id,number:index+1,trip:trip.trip_number,truck:trip.vehicle.registration_number,driver:trip.driver.name,pickup:trip.origin,delivery:trip.destination,status:tripStatusLabel[trip.status]||trip.status,approved_earnings_INR:Number(trip.revenue_total),approved_costs_INR:Number(trip.expense_total),approved_balance_INR:trip.margin===null?null:Number(trip.margin)}))} recordPrefix="trip-record-" onOpen={id=>tripPage.reveal(tripRegisterRows.findIndex(item=>item.id===id))}>{tripPage.rows.map(trip => <UiArticle id={`trip-record-${trip.id}`} tabIndex={-1} key={trip.id} className="overflow-hidden rounded-2xl border border-line bg-white shadow-sm">
      <UiBox className="grid items-start gap-5 p-5 md:grid-cols-[minmax(0,1fr)_280px]"><UiBox><UiBox className="flex flex-wrap items-center gap-2"><UiSpan aria-label={`Trip number ${tripRegisterRows.findIndex(item=>item.id===trip.id)+1}`} className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-slate-100 px-2 text-xs font-bold text-slate-600">#{String(tripRegisterRows.findIndex(item=>item.id===trip.id)+1).padStart(2,"0")}</UiSpan><UiH3 className="text-lg font-bold text-slate-950">{trip.trip_number}</UiH3><UiSpan className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tripStatusStyle[trip.status] || "bg-slate-100 text-slate-600"}`}>{tripStatusLabel[trip.status] || trip.status.replaceAll("_", " ")}</UiSpan></UiBox><UiBox className="mt-3 grid max-w-3xl grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 rounded-xl bg-slate-50 px-4 py-3"><UiBox><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">From</UiText><UiText className="mt-1 text-sm font-semibold text-slate-900">{trip.origin || "Not set"}</UiText></UiBox><span className="text-lg text-slate-400" aria-hidden="true">→</span><UiBox><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">To</UiText><UiText className="mt-1 text-sm font-semibold text-slate-900">{trip.destination || "Not set"}</UiText></UiBox></UiBox><UiText className="mt-3 text-sm text-slate-600">Truck <UiStrong>{trip.vehicle.registration_number}</UiStrong><span className="px-2 text-slate-300">·</span>Driver <UiStrong>{trip.driver.name}</UiStrong></UiText>{trip.status !== "APPROVED" && <UiBox className="mt-4 flex items-start gap-3 rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-2"><span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-emerald-600" aria-hidden="true"/><UiText className="text-sm font-semibold text-emerald-900">Next step: {tripNextStep(trip)}</UiText></UiBox>}<UiBox className="mt-3 flex flex-wrap gap-2">{trip.status === "DRAFT" && <UiButton onClick={() => void tripAction(trip, "start")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Truck arrived at pickup</UiButton>}{trip.status === "IN_PROGRESS" && (!trip.loaded_at ? <UiButton onClick={() => void tripAction(trip, "load")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Confirm goods loaded</UiButton> : <UiButton onClick={() => void tripAction(trip, "complete")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Mark delivery finished</UiButton>)}{["COMPLETED", "REJECTED"].includes(trip.status) && <UiButton onClick={() => void tripAction(trip, "submit")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Send trip for approval</UiButton>}{trip.status === "SUBMITTED" && <><UiButton onClick={() => void tripAction(trip, "approve")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Approve trip</UiButton><UiButton onClick={() => void tripAction(trip, "reject")} className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700">Ask for changes</UiButton></>}</UiBox>{trip.transport_order && <UiText className="mt-3 text-xs text-slate-500">Order {trip.transport_order.order_number} · {trip.transport_order.customer_name}</UiText>}{trip.ends_at && <UiText className="mt-2 text-xs text-slate-500">Delivery finished {new Date(trip.ends_at).toLocaleString()}{trip.odometer_end ? ` · Ending odometer ${trip.odometer_end}` : ""}</UiText>}{trip.review_note && <UiText className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">Manager’s note: {trip.review_note}</UiText>}</UiBox><UiBox className="self-start rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm"><UiText className="text-xs font-semibold uppercase tracking-wide text-slate-500">Trip summary</UiText><UiText className="mt-3 flex justify-between gap-2"><span>Earned</span><UiStrong>₹{trip.revenue_total}</UiStrong></UiText><UiText className="mt-2 flex justify-between gap-2"><span>Spent</span><UiStrong>₹{trip.expense_total}</UiStrong></UiText><UiText className={`mt-3 border-t border-line pt-3 text-sm font-semibold ${trip.margin !== null && Number(trip.margin) < 0 ? "text-rose-700" : "text-emerald-800"}`}>{trip.margin === null ? "Balance after manager checks" : <>Balance <UiStrong>₹{trip.margin}</UiStrong></>}</UiText></UiBox></UiBox>

      {(trip.status === "DRAFT" || trip.status === "IN_PROGRESS" || trip.status === "COMPLETED" || trip.status === "REJECTED") && <details className="mt-4 border-t border-line pt-3"><summary className="cursor-pointer py-2 text-sm font-semibold text-slate-700">Add trip earnings or costs</summary><UiText className="mb-3 text-xs text-slate-500">These amounts will be checked before they count in the trip total.</UiText><UiBox className="grid gap-3 lg:grid-cols-2">
        <UiForm className="flex flex-wrap gap-2" onSubmit={e => void addLine(e, trip, "revenue")}><UiText className="w-full text-xs text-slate-500">Money earned for this trip.</UiText><UiInput className={`${inputClass} min-w-24 flex-1`} name="description" placeholder="Earnings reason (e.g. delivery charge)" required/><UiInput className="w-28 rounded-lg border border-line px-3 py-2 text-sm" name="amount" type="number" min="0.01" step="0.01" placeholder="₹ amount" required/><UiButton disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Add earnings</UiButton></UiForm>
        <UiForm className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" onSubmit={e => void addLine(e, trip, "expenses")}><UiText className="text-xs text-slate-500 sm:col-span-2 xl:col-span-4">Money paid for this trip. Add the amount and what it was for.</UiText><UiInput className={inputClass} name="description" placeholder="What was paid for? (e.g. diesel)" required/><UiInput className={inputClass} name="amount" type="number" min="0.01" step="0.01" placeholder="Amount ₹" required/><UiSelect className={inputClass} name="category" aria-label="Cost category"><option value="FUEL">Fuel</option><option value="TOLL">Toll</option><option value="LOADING">Loading</option><option value="REPAIR">Repair</option><option value="OTHER">Other</option></UiSelect><details className="rounded-lg border border-line p-2 sm:col-span-2"><summary className="cursor-pointer text-xs font-semibold text-slate-600">Optional details: budget, fuel, receipt</summary><UiBox className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3"><UiInput className={inputClass} name="budgeted_amount" type="number" min="0" step="0.01" placeholder="₹ budget (optional)" aria-label="Planned cost budget"/><UiInput className={inputClass} name="quantity_litres" type="number" min="0.01" step="0.01" placeholder="Fuel litres" aria-label="Fuel litres for efficiency monitoring"/><UiSelect className={inputClass} name="fuel_fill_type" aria-label="Fuel fill type"><option value="UNKNOWN">Fill type not recorded</option><option value="FULL">Full tank</option><option value="PARTIAL">Partial fill</option></UiSelect><UiInput className={inputClass} name="odometer_km" type="number" min="0" step="0.1" placeholder="Fill odometer (km)" aria-label="Odometer at fuel fill"/><UiInput className={inputClass} name="incurred_at" type="date" aria-label="Fuel fill date"/><UiInput className={inputClass} name="payment_reference" placeholder="Receipt / transaction ref" aria-label="Fuel transaction reference"/><UiLabel className="flex items-center text-xs text-slate-500">Receipt<UiInput className="ml-2 w-32 text-xs" name="receipt_file" type="file" accept="application/pdf,image/jpeg,image/png,image/heic" aria-label="Attach cost receipt"/></UiLabel></UiBox></details><UiButton disabled={busy} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Add cost</UiButton></UiForm>
      </UiBox></details>}
      {(trip.revenue_lines.length > 0 || trip.expense_lines.length > 0) && <><UiButton type="button" onClick={() => setMoneyTripId(trip.id)} className="mx-5 mb-4 rounded-lg border border-line px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">View trip money ({trip.revenue_lines.length + trip.expense_lines.length})</UiButton><Dialog open={moneyTripId === trip.id} onClose={() => setMoneyTripId(null)} fullWidth maxWidth="md" aria-labelledby={`trip-money-title-${trip.id}`}><DialogTitle id={`trip-money-title-${trip.id}`}>Trip money details<UiText className="mt-1 text-sm font-normal text-slate-500">{trip.trip_number}</UiText></DialogTitle><DialogContent dividers>
        <UiBox className={`grid gap-4 border-t border-line bg-slate-50/50 p-4 ${trip.revenue_lines.length > 0 && trip.expense_lines.length > 0 ? "md:grid-cols-2" : ""}`}>
          {trip.revenue_lines.length > 0 && <UiBox className="rounded-lg border border-line bg-white p-4">
            <UiText className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Money earned</UiText>
            <UiBox className="space-y-2">{trip.revenue_lines.map(line => <UiBox key={line.id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
              <UiBox><UiText className="text-sm font-medium text-slate-800">{line.description}</UiText><UiText className="mt-1 text-xs text-slate-500">{lineStatusLabel[line.status] || line.status.toLowerCase()}</UiText></UiBox>
              <UiStrong className="shrink-0 text-sm text-slate-900">₹{line.amount}</UiStrong>
            </UiBox>)}</UiBox>
          </UiBox>}
          {trip.expense_lines.length > 0 && <UiBox className="rounded-lg border border-line bg-white p-4">
            <UiText className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Money spent</UiText>
            <UiBox className="space-y-3">{trip.expense_lines.map(line => <UiBox key={line.id} className="rounded-lg border border-line p-3">
              <UiBox className="flex flex-wrap items-start justify-between gap-2">
                <UiBox className="min-w-0"><UiSpan className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{line.category}</UiSpan><UiText className="mt-1 break-words text-sm font-semibold text-slate-900">{line.description}</UiText></UiBox>
                <UiStrong className="shrink-0 text-base text-slate-900">₹{line.amount}</UiStrong>
              </UiBox>
              <UiBox className="mt-3 flex flex-wrap items-center gap-2">
                <UiSpan className={`rounded-full px-2 py-1 text-[11px] font-medium ${lineStatusLabel[line.status] === "Approved" ? "bg-emerald-50 text-emerald-700" : lineStatusLabel[line.status] === "Needs changes" ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-800"}`}>{lineStatusLabel[line.status] || line.status.toLowerCase()}</UiSpan>
                <UiSpan className={`rounded-full px-2 py-1 text-[11px] font-medium ${line.receipt_name ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-800"}`}>{line.receipt_name ? "Receipt added" : "Receipt needed"}</UiSpan>
                {line.budgeted_amount !== null && line.budgeted_amount !== undefined && <UiSpan className={`rounded-full px-2 py-1 text-[11px] font-medium ${Number(line.amount) > Number(line.budgeted_amount) ? "bg-rose-50 text-rose-700" : "bg-slate-100 text-slate-600"}`}>{Number(line.amount) > Number(line.budgeted_amount) ? `Over budget ₹${(Number(line.amount) - Number(line.budgeted_amount)).toFixed(2)}` : `Budget ₹${line.budgeted_amount}`}</UiSpan>}
              </UiBox>
              {line.category === "FUEL" && <UiBox className="mt-3 grid grid-cols-2 gap-2 rounded-md bg-slate-50 p-2.5 text-xs sm:grid-cols-3">
                <UiText><span className="block text-slate-500">Fuel</span><UiStrong>{line.quantity_litres || "—"} L · {line.fuel_fill_type ? line.fuel_fill_type.toLowerCase() : "type not set"}</UiStrong></UiText>
                <UiText><span className="block text-slate-500">Truck reading</span><UiStrong>{line.odometer_km || "—"} km</UiStrong></UiText>
                {line.payment_reference && <UiText className="col-span-2 sm:col-span-1"><span className="block text-slate-500">Receipt reference</span><UiStrong className="break-all">{line.payment_reference}</UiStrong></UiText>}
              </UiBox>}
              {line.category === "FUEL" && <UiButton type="button" onClick={() => setCorrectingFuel(correctingFuel === line.id ? null : line.id)} className="mt-3 rounded-lg border border-line px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">{correctingFuel === line.id ? "Close fuel update" : "Update fuel details"}</UiButton>}
              {correctingFuel === line.id && <UiForm className="mt-3 grid gap-2 sm:grid-cols-2" onSubmit={event => void correctFuelLine(event, trip, line)}><UiInput className={inputClass} name="description" defaultValue={line.description} aria-label="Fuel description" required/><UiInput className={inputClass} name="amount" type="number" min="0.01" step="0.01" defaultValue={line.amount} aria-label="Fuel cost" required/><UiInput className={inputClass} name="quantity_litres" type="number" min="0.01" step="0.01" defaultValue={line.quantity_litres || ""} aria-label="Fuel litres" placeholder="Litres"/><UiSelect className={inputClass} name="fuel_fill_type" defaultValue={line.fuel_fill_type || "UNKNOWN"} aria-label="Fuel fill type"><option value="UNKNOWN">Type unknown</option><option value="FULL">Full tank</option><option value="PARTIAL">Partial fill</option></UiSelect><UiInput className={inputClass} name="odometer_km" type="number" min="0" step="0.1" defaultValue={line.odometer_km || ""} aria-label="Odometer at fill" placeholder="Fill odometer (km)"/><UiInput className={inputClass} name="incurred_at" type="date" defaultValue={line.incurred_at || ""} aria-label="Fill date"/><UiInput className={inputClass} name="payment_reference" defaultValue={line.payment_reference || ""} aria-label="Receipt / transaction reference" placeholder="Receipt / transaction ref"/><UiInput className="sm:col-span-2" name="reason" minLength={8} maxLength={500} placeholder="Why are you changing this?" required/><UiButton disabled={busy} className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white sm:col-span-2">{busy ? "Saving…" : "Save fuel update"}</UiButton></UiForm>}
            </UiBox>)}</UiBox>
          </UiBox>}
        </UiBox></DialogContent><DialogActions><UiButton onClick={() => setMoneyTripId(null)} className="mr-2 rounded-lg border border-line px-4 py-2 text-sm">Close</UiButton></DialogActions></Dialog></>}    </UiArticle>)}{tripPage.controls}</CollectionExplorer>{tripRegisterRows.length === 0 && <UiBox className={`${cardClass} text-sm text-slate-500`}>{(tripSearch || tripStatusFilter || Object.values(filters).some(Boolean)) ? "No trips match this search. Try another word or choose All trips." : "No trips yet. Start by creating a trip and assigning a truck and driver."}</UiBox>}</UiBox></UiSection>
    </>}
  </UiMain>;
}
