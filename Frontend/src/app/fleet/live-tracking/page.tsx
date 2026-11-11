"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Dialog, DialogActions, DialogContent, DialogTitle } from "@mui/material";
import { AppLink } from "@/components/product-ui";
import { EmptyState } from "@/components/empty-state";
import { PageSkeleton } from "@/components/content-skeleton";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { UiBox, UiButton, UiH1, UiHeader, UiMain, UiSection, UiText } from "@/components/product-ui";
import { History, LocateFixed, Pause, Play, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { TripMap, type MapPoint } from "./trip-map";
import { FleetLiveMap } from "./fleet-live-map";

type LiveTruck = { trip_id:string;trip_number:string;vehicle:string;driver:string;origin:string;destination:string;status:"LIVE"|"STALE"|"WAITING_FOR_GPS";latitude:string|null;longitude:string|null;accuracy_m:string|null;speed_kmh:string|null;heading_degrees:string|null;captured_at:string|null;last_seen_at:string|null;age_seconds:number|null;estimated_arrival_at:string|null;eta_method:string|null;eta_sample_count:number;delivery_at_risk:boolean;delivery_due_at:string|null;stationary_stop:{started_at:string;stationary_seconds:number;engine_idle_seconds:number;ignition_on:boolean|null;engine_idle_measured:boolean}|null };
type Payload = { updated_at:string;refresh_seconds:number;trips:LiveTruck[] };
type LocationPoint = MapPoint;
const dayInput=(date:Date)=>{const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);return local.toISOString().slice(0,10);};
const GAP_LIMIT_MS=2*60*1000;
const gpsLabels = { LIVE: "Live GPS", STALE: "GPS out of date", WAITING_FOR_GPS: "Waiting for GPS" } as const;
const gpsTones = { LIVE: "bg-emerald-100 text-emerald-800", STALE: "bg-amber-100 text-amber-900", WAITING_FOR_GPS: "bg-slate-100 text-slate-700" };
function locationAge(truck: LiveTruck) {
  if (!truck.captured_at) return "No location received";
  if (truck.age_seconds == null) return new Date(truck.captured_at).toLocaleString();
  if (truck.age_seconds < 60) return "Updated less than a minute ago";
  const minutes = Math.floor(truck.age_seconds / 60);
  if (minutes < 60) return `Updated ${minutes} min ago`;
  if (minutes < 1440) return `Updated ${Math.floor(minutes / 60)} hr ago`;
  const days = Math.floor(minutes / 1440);
  return `Updated ${days} ${days === 1 ? "day" : "days"} ago`;
}

function TripHistory({tripId}:{tripId:string}){
 const[open,setOpen]=useState(false);const[loading,setLoading]=useState(false);const[error,setError]=useState("");const[points,setPoints]=useState<LocationPoint[]>([]);const[index,setIndex]=useState(0);const[hasMore,setHasMore]=useState(false);const[loadingMore,setLoadingMore]=useState(false);const[playing,setPlaying]=useState(false);
 const[fromDate,setFromDate]=useState(()=>{const date=new Date();date.setDate(date.getDate()-6);return dayInput(date);});const[toDate,setToDate]=useState(()=>dayInput(new Date()));const[windowError,setWindowError]=useState("");
 const selected=points[index];
 const gapBefore=selected&&index>0?new Date(selected.captured_at).getTime()-new Date(points[index-1].captured_at).getTime():0;
 function historyUrl(offset=0){const from=new Date(`${fromDate}T00:00:00`);const to=new Date(`${toDate}T23:59:59.999`);const params=new URLSearchParams({limit:"5000",offset:String(offset),from:from.toISOString(),to:to.toISOString()});return `/fleet/trips/${tripId}/location-history?${params.toString()}`;}
 function validateWindow(){const from=new Date(`${fromDate}T00:00:00`);const to=new Date(`${toDate}T23:59:59.999`);const days=(to.getTime()-from.getTime())/86400000;if(!Number.isFinite(days)||days<0||days>31){setWindowError("Choose a valid date range of 31 days or less.");return false;}setWindowError("");return true;}
 useEffect(()=>{
  if(!playing)return;
  if(index>=points.length-1){setPlaying(false);return;}
  const timer=window.setTimeout(()=>setIndex(current=>Math.min(current+1,points.length-1)),700);
  return()=>window.clearTimeout(timer);
 },[index,playing,points.length]);
 async function loadHistory(){
  setOpen(true);if(points.length||loading)return;if(!validateWindow())return;setLoading(true);setError("");
  try{const response=await apiFetch(historyUrl());const body=await response.json();if(!response.ok)throw new Error(body.error||body.detail||"Could not load route history.");setPoints(body.points||[]);setIndex(0);setHasMore(Boolean(body.has_more));}
  catch(e){setError(e instanceof Error?e.message:"Could not load route history.");}finally{setLoading(false);}
 }
 async function applyWindow(){if(!validateWindow())return;setPoints([]);setIndex(0);setHasMore(false);setPlaying(false);setLoading(true);setError("");
  try{const response=await apiFetch(historyUrl());const body=await response.json();if(!response.ok)throw new Error(body.error||body.detail||"Could not load route history.");setPoints(body.points||[]);setHasMore(Boolean(body.has_more));}
  catch(e){setError(e instanceof Error?e.message:"Could not load route history.");}finally{setLoading(false);}}
 async function loadMore(){
  if(loadingMore||!hasMore)return;setLoadingMore(true);setError("");
  try{const response=await apiFetch(historyUrl(points.length));const body=await response.json();if(!response.ok)throw new Error(body.error||body.detail||"Could not load more route history.");setPoints(current=>[...current,...(body.points||[])]);setHasMore(Boolean(body.has_more));}
  catch(e){setError(e instanceof Error?e.message:"Could not load more route history.");}finally{setLoadingMore(false);}
 }
 const closeHistory = () => { setPlaying(false); setOpen(false); };
 return <>
  <Button variant="outlined" size="small" startIcon={<History size={16}/>} onClick={() => void loadHistory()}>Route history</Button>
  <Dialog open={open} onClose={closeHistory} fullWidth maxWidth="md" aria-labelledby="route-history-title">
   <DialogTitle id="route-history-title">Route history and playback</DialogTitle>
   <DialogContent dividers><form className="mb-3 grid grid-cols-2 items-end gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={event=>{event.preventDefault();void applyWindow();}}><label className="text-sm font-medium text-slate-600">From<input type="date" value={fromDate} max={toDate} onChange={event=>setFromDate(event.target.value)} className="mt-1 block w-full rounded-md border border-line bg-white px-2 py-1.5 text-sm"/></label><label className="text-sm font-medium text-slate-600">Through<input type="date" value={toDate} min={fromDate} onChange={event=>setToDate(event.target.value)} className="mt-1 block w-full rounded-md border border-line bg-white px-2 py-1.5 text-sm"/></label><button type="submit" disabled={loading||loadingMore} className="col-span-2 rounded-md bg-forest px-3 py-2 text-sm font-semibold text-white disabled:opacity-50 sm:col-span-1">Apply dates</button></form>{windowError&&<UiText role="alert" className="mb-2 text-xs text-rose-700">{windowError}</UiText>}{loading?<UiText className="text-xs text-slate-500">Loading recorded GPS points…</UiText>:error?<UiText role="alert" className="text-xs text-rose-700">{error}</UiText>:!points.length?<UiText className="text-xs text-slate-500">No route history was recorded in this date window.</UiText>:<>
   <UiText className="text-xs font-semibold">Trip route · {points.length.toLocaleString()} GPS points</UiText>
   <TripMap points={points} selectedIndex={index}/>
   <UiBox className="mt-2 flex items-center gap-3"><button type="button" disabled={points.length<2} onClick={()=>{if(playing){setPlaying(false);}else{if(index>=points.length-1)setIndex(0);setPlaying(true);}}} aria-label={playing?"Pause route playback":"Play route playback"} className="grid size-9 shrink-0 place-items-center rounded-lg bg-forest text-white disabled:opacity-40">{playing?<Pause size={15}/>:<Play size={15}/>}</button><label className="block flex-1 text-[11px] text-slate-600">Playback point {index+1} of {points.length}<input aria-label="Route playback position" type="range" min={0} max={points.length-1} value={index} onChange={event=>{setPlaying(false);setIndex(Number(event.target.value));}} className="mt-1 block w-full accent-emerald-700"/></label></UiBox>
   {selected&&<UiBox className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600"><span>{new Date(selected.captured_at).toLocaleString()} · {Number(selected.latitude).toFixed(6)}, {Number(selected.longitude).toFixed(6)}{selected.speed_kmh?` · ${Number(selected.speed_kmh).toFixed(0)} km/h`:""}{gapBefore>GAP_LIMIT_MS&&<span className="ml-1 font-semibold text-amber-800">· GPS gap {Math.round(gapBefore/60000)} min before this point</span>}</span><a target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${encodeURIComponent(selected.latitude)}&mlon=${encodeURIComponent(selected.longitude)}#map=16/${encodeURIComponent(selected.latitude)}/${encodeURIComponent(selected.longitude)}`} className="font-semibold text-forest">Open point on map</a></UiBox>}
   {hasMore&&<button type="button" onClick={()=>void loadMore()} disabled={loadingMore} className="mt-2 text-xs font-semibold text-forest">{loadingMore?"Loading more points…":"Load next 5,000 points"}</button>}
   </>}</DialogContent>
   <DialogActions><Button onClick={closeHistory}>Close</Button></DialogActions>
  </Dialog>
 </>;
}

export default function FleetLiveTrackingPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<LiveTruck["status"] | "">("");
  const [focusTruck, setFocusTruck] = useState(false);
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (document.hidden || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      const response = await apiFetch("/fleet/live-locations");
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || body.detail || "Could not load live truck locations.");
      setData(body);
      setSelectedTripId(current => body.trips.some((trip: LiveTruck) => trip.trip_id === current) ? current : body.trips[0]?.trip_id || null);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load live truck locations.");
    } finally {
      inFlight.current = false;
      setBusy(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    const visible = () => { if (!document.hidden) void load(); };
    document.addEventListener("visibilitychange", visible);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", visible); };
  }, [load]);

  if (loading) return <PageSkeleton variant="cards" label="Loading live truck locations"/>;
  const trips = data?.trips || [];
  const liveCount = trips.filter(trip => trip.status === "LIVE").length;
  const staleCount = trips.filter(trip => trip.status === "STALE").length;
  const waitingCount = trips.filter(trip => trip.status === "WAITING_FOR_GPS").length;
  const visibleTrips = trips.filter(trip => (!statusFilter || trip.status === statusFilter) &&
    `${trip.vehicle} ${trip.driver} ${trip.trip_number} ${trip.origin} ${trip.destination}`.toLowerCase().includes(query.trim().toLowerCase()));
  const selected = visibleTrips.find(trip => trip.trip_id === selectedTripId) || visibleTrips[0] || null;
  const canFocus = Boolean(selected?.latitude != null && selected.longitude != null);
  const mapTrips = focusTruck && canFocus && selected ? [selected] : visibleTrips;
  const summaries = [
    { status: "" as const, label: "All active trips", count: trips.length },
    { status: "LIVE" as const, label: gpsLabels.LIVE, count: liveCount },
    { status: "STALE" as const, label: gpsLabels.STALE, count: staleCount },
    { status: "WAITING_FOR_GPS" as const, label: gpsLabels.WAITING_FOR_GPS, count: waitingCount },
  ];

  return <UiMain className="w-full min-w-0 max-w-none space-y-4 px-3 py-4 sm:px-4">
    <UiHeader className="flex flex-wrap items-end justify-between gap-3">
      <UiBox>
        <UiText className="text-[11px] font-bold uppercase tracking-[.16em] text-forest">Fleet operations · Control center</UiText>
        <UiH1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Live tracking</UiH1>
        <UiText className="mt-1 max-w-3xl text-sm text-slate-500">Find a truck, check its last location, and review its arrival estimate.</UiText>
      </UiBox>
      <UiBox className="flex items-center gap-2">
        <UiText className="hidden text-xs text-slate-500 sm:block">{busy ? "Updating locations…" : data?.updated_at ? `Updated ${new Date(data.updated_at).toLocaleTimeString()}` : "Waiting for update"}</UiText>
        <UiButton type="button" onClick={() => void load()} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm font-semibold"><RefreshCw size={14}/>{busy ? "Refreshing…" : "Refresh"}</UiButton>
      </UiBox>
    </UiHeader>

    {error && <WorkflowFeedback message={error} onRefresh={() => void load()}/>}
    <UiSection aria-label="Filter trips by GPS status" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {summaries.map(item => <button key={item.status} type="button" aria-pressed={statusFilter === item.status}
        onClick={() => { setStatusFilter(item.status); setFocusTruck(false); }}
        className={`flex items-center justify-between gap-2 rounded-xl border px-4 py-3 text-left text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest ${statusFilter === item.status ? "border-forest bg-emerald-50 text-forest" : "border-line bg-white text-slate-700 hover:bg-slate-50"}`}>
        {item.label}<span className="text-lg font-bold tabular-nums">{item.count}</span>
      </button>)}
    </UiSection>

    {!trips.length ? !error && <EmptyState title="No active trips to track" description="When a driver starts a trip and shares a location, it will appear here." actionLabel="Open dispatch" onAction={() => window.location.assign("/fleet/dispatch")}/> :
      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(290px,25%)_minmax(0,1fr)]">
        <div className="contents min-w-0 lg:block lg:space-y-4">
        <UiSection aria-label="Active trucks" className="overflow-hidden rounded-xl border border-line bg-white">
          <div className="border-b border-line p-4">
            <UiText className="text-base font-bold">Active trucks</UiText>
            <UiText className="mt-1 text-xs text-slate-600">{visibleTrips.length} of {trips.length} trips shown</UiText>
            <input aria-label="Search active trucks" value={query} onChange={event => { setQuery(event.target.value); setFocusTruck(false); }} placeholder="Truck, driver, trip, or route"
              className="mt-3 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-forest focus:ring-2 focus:ring-emerald-100"/>
          </div>
          <div className="max-h-64 divide-y divide-line overflow-y-auto lg:max-h-[560px]">
            {visibleTrips.map(truck => <button key={truck.trip_id} type="button" onClick={() => setSelectedTripId(truck.trip_id)} aria-pressed={truck.trip_id === selected?.trip_id}
              className={`block w-full px-4 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-forest ${truck.trip_id === selected?.trip_id ? "bg-emerald-50" : "hover:bg-slate-50"}`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-slate-950">{truck.vehicle}</span>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${gpsTones[truck.status]}`}>{gpsLabels[truck.status]}</span>
              </span>
              <span className="mt-1 block break-words text-sm text-slate-700">{truck.origin || "Pickup not set"} → {truck.destination || "Destination not set"}</span>
              <span className="mt-1 block text-xs text-slate-600">{truck.trip_number} · {truck.driver}</span>
              <span className="mt-1 block text-xs text-slate-600">{locationAge(truck)}{truck.delivery_at_risk && <strong className="ml-2 text-rose-700">Delivery at risk</strong>}</span>
            </button>)}
            {!visibleTrips.length && <div className="p-4 text-sm text-slate-600">No trucks match these filters. <button type="button" className="font-semibold text-forest underline" onClick={() => { setQuery(""); setStatusFilter(""); }}>Clear filters</button></div>}
          </div>
        </UiSection>
        <div className="order-3 min-w-0">
        {selected ?
          <UiSection aria-label="Selected trip" className="overflow-hidden rounded-xl border border-line bg-white">
            <div className="border-b border-line bg-slate-50 p-4">
              <UiText className="text-xs font-semibold text-slate-600">Selected trip · {selected.trip_number}</UiText>
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                <h2 className="break-words text-xl font-bold text-slate-950">{selected.vehicle}</h2>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${gpsTones[selected.status]}`}>{gpsLabels[selected.status]}</span>
              </div>
              <UiText className="mt-1 text-sm text-slate-700">Driver · {selected.driver}</UiText>
            </div>
            <div className="space-y-3 p-4">
              <dl className="m-0 grid grid-cols-2 gap-3">
                <div className="min-w-0"><dt className="text-xs text-slate-600">Pickup</dt><dd className="m-0 break-words text-sm font-semibold">{selected.origin || "Not set"}</dd></div>
                <div className="min-w-0"><dt className="text-xs text-slate-600">Delivery</dt><dd className="m-0 break-words text-sm font-semibold">{selected.destination || "Not set"}</dd></div>
              </dl>
              <div className={`rounded-lg p-3 ${selected.status === "STALE" ? "bg-amber-50 text-amber-950" : "bg-slate-50 text-slate-800"}`}>
                <p className="text-xs font-medium">Last reported location</p>
                <p className="mt-1 text-sm font-bold">{locationAge(selected)}</p>
                {selected.captured_at && <time dateTime={selected.captured_at} className="mt-1 block text-xs">{new Date(selected.captured_at).toLocaleString()}</time>}
                {selected.status === "STALE" && <p className="mt-2 text-xs">For phone tracking, ask the driver to reopen their trip and check location permission.</p>}
              </div>
              {canFocus && <details className="text-sm text-slate-600">
                <summary className="cursor-pointer font-semibold">GPS details</summary>
                <p className="mt-2 tabular-nums">{Number(selected.latitude).toFixed(6)}, {Number(selected.longitude).toFixed(6)}</p>
                <p className="mt-1 text-xs">{[selected.speed_kmh != null && `Last recorded speed ${Number(selected.speed_kmh).toFixed(0)} km/h`, selected.accuracy_m != null && `Accuracy ±${Number(selected.accuracy_m).toFixed(0)} m`].filter(Boolean).join(" · ")}</p>
              </details>}
            {selected.stationary_stop && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3"><UiText className="text-xs font-semibold text-amber-950">Stationary · {Math.floor(selected.stationary_stop.stationary_seconds/60)} min</UiText><UiText className="mt-1 text-[11px] leading-5 text-amber-900">{selected.stationary_stop.engine_idle_measured?`Engine-on stationary time measured: ${Math.floor(selected.stationary_stop.engine_idle_seconds/60)} min from consecutive tracker fixes.`:selected.stationary_stop.ignition_on===false?"Latest tracker fix reports ignition off; no engine-idle time counted.":selected.stationary_stop.ignition_on===true?"Ignition is on, but engine-idle time is counted only when consecutive fixes also confirm speed at or below 3 km/h.":"Engine-idle time is unconfirmed because this feed has no ignition evidence."}</UiText></div>}
            {selected.estimated_arrival_at && <div className={`mt-3 rounded-lg border p-3 ${selected.delivery_at_risk ? "border-rose-200 bg-rose-50" : "border-line bg-white"}`}><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Estimated arrival</UiText><UiText className="mt-1 text-sm font-semibold">{new Date(selected.estimated_arrival_at).toLocaleString()}</UiText><UiText className="mt-1 text-[10px] text-slate-500">{selected.eta_method === "GOOGLE_TRAFFIC" ? "Google Maps road and traffic estimate" : `Historical route estimate · ${selected.eta_sample_count} prior trips`}</UiText>{selected.delivery_at_risk && <UiText className="mt-1 text-xs font-semibold text-rose-700">At risk · scheduled {selected.delivery_due_at ? new Date(selected.delivery_due_at).toLocaleString() : ""}</UiText>}</div>}
              <div className="border-t border-line pt-3"><TripHistory key={selected.trip_id} tripId={selected.trip_id}/></div>
            </div>
          </UiSection>
        : <div className="rounded-xl border border-line bg-white p-5 text-sm text-slate-500">Select a vehicle to see trip details and route history.</div>}
        </div>
        </div>

        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <UiText className="text-sm font-semibold">{focusTruck && canFocus && selected ? `Map focused on ${selected.vehicle}` : "Map of matching trucks"}</UiText>
            {canFocus && <button type="button" aria-pressed={focusTruck} onClick={() => setFocusTruck(value => !value)} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-forest">
              <LocateFixed size={15} aria-hidden="true"/>{focusTruck ? "Show all matching trucks" : "Focus selected truck"}
            </button>}
          </div>
          <FleetLiveMap fillWindow key={focusTruck && canFocus ? selected?.trip_id : "fleet"} vehicles={mapTrips} selectedTripId={selected?.trip_id ?? null} onSelect={setSelectedTripId}/>
      </div>
    </div>}
    <details className="rounded-xl border border-line bg-white p-4 text-sm text-slate-600">
      <summary className="cursor-pointer font-semibold text-slate-800">How location and arrival updates work</summary>
      <p className="mt-2">The page checks for new locations every 15 seconds. GPS older than two minutes is marked out of date. Drivers using phone tracking need location permission and the Driver Phone View open during the trip.</p>
      <p className="mt-2">Arrival estimates use Google Maps Routes when configured, or past trips on the same route when enough history is available.</p>
    </details>
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-[10px] text-slate-400"><span>{data?.updated_at ? `Live feed refreshed ${new Date(data.updated_at).toLocaleString()}` : "Live feed not yet updated"}</span><AppLink href="/fleet" className="font-semibold text-forest">← Fleet & trips</AppLink></div>
  </UiMain>;
}
