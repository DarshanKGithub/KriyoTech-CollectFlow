"use client";

import { useCallback, useEffect, useState } from "react";
import { AppLink } from "@/components/product-ui";
import { EmptyState } from "@/components/empty-state";
import { PageSkeleton } from "@/components/content-skeleton";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { UiBox, UiButton, UiH1, UiHeader, UiMain, UiSection, UiText } from "@/components/product-ui";
import { Pause, Play, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { TripMap, type MapPoint } from "./trip-map";
import { FleetLiveMap } from "./fleet-live-map";

type LiveTruck = { trip_id:string;trip_number:string;vehicle:string;driver:string;origin:string;destination:string;status:"LIVE"|"STALE"|"WAITING_FOR_GPS";latitude:string|null;longitude:string|null;accuracy_m:string|null;speed_kmh:string|null;heading_degrees:string|null;captured_at:string|null;last_seen_at:string|null;age_seconds:number|null;estimated_arrival_at:string|null;eta_method:string|null;eta_sample_count:number;delivery_at_risk:boolean;delivery_due_at:string|null;stationary_stop:{started_at:string;stationary_seconds:number;engine_idle_seconds:number;ignition_on:boolean|null;engine_idle_measured:boolean}|null };
type Payload = { updated_at:string;refresh_seconds:number;trips:LiveTruck[] };
type LocationPoint = MapPoint;
const dayInput=(date:Date)=>{const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);return local.toISOString().slice(0,10);};
const GAP_LIMIT_MS=2*60*1000;

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
 return <div className="mt-4 border-t border-line pt-3"><button type="button" onClick={()=>open?setOpen(false):void loadHistory()} className="text-xs font-semibold text-forest">{open?"Hide route replay":"View route history and playback"}</button>
  {open&&<div className="mt-3 rounded-xl border border-line bg-slate-50 p-3"><form className="mb-3 grid grid-cols-2 items-end gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={event=>{event.preventDefault();void applyWindow();}}><label className="text-[11px] font-medium text-slate-600">From<input type="date" value={fromDate} max={toDate} onChange={event=>setFromDate(event.target.value)} className="mt-1 block w-full rounded-md border border-line bg-white px-2 py-1.5 text-xs"/></label><label className="text-[11px] font-medium text-slate-600">Through<input type="date" value={toDate} min={fromDate} onChange={event=>setToDate(event.target.value)} className="mt-1 block w-full rounded-md border border-line bg-white px-2 py-1.5 text-xs"/></label><button type="submit" disabled={loading||loadingMore} className="col-span-2 rounded-md bg-forest px-3 py-2 text-xs font-semibold text-white disabled:opacity-50 sm:col-span-1">Apply dates</button></form>{windowError&&<UiText role="alert" className="mb-2 text-xs text-rose-700">{windowError}</UiText>}{loading?<UiText className="text-xs text-slate-500">Loading recorded GPS points…</UiText>:error?<UiText role="alert" className="text-xs text-rose-700">{error}</UiText>:!points.length?<UiText className="text-xs text-slate-500">No route history was recorded in this date window.</UiText>:<>
   <UiText className="text-xs font-semibold">Trip route · {points.length.toLocaleString()} GPS points</UiText>
   <TripMap points={points} selectedIndex={index}/>
   <UiBox className="mt-2 flex items-center gap-3"><button type="button" disabled={points.length<2} onClick={()=>{if(playing){setPlaying(false);}else{if(index>=points.length-1)setIndex(0);setPlaying(true);}}} aria-label={playing?"Pause route playback":"Play route playback"} className="grid size-9 shrink-0 place-items-center rounded-lg bg-forest text-white disabled:opacity-40">{playing?<Pause size={15}/>:<Play size={15}/>}</button><label className="block flex-1 text-[11px] text-slate-600">Playback point {index+1} of {points.length}<input aria-label="Route playback position" type="range" min={0} max={points.length-1} value={index} onChange={event=>{setPlaying(false);setIndex(Number(event.target.value));}} className="mt-1 block w-full accent-emerald-700"/></label></UiBox>
   {selected&&<UiBox className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600"><span>{new Date(selected.captured_at).toLocaleString()} · {Number(selected.latitude).toFixed(6)}, {Number(selected.longitude).toFixed(6)}{selected.speed_kmh?` · ${Number(selected.speed_kmh).toFixed(0)} km/h`:""}{gapBefore>GAP_LIMIT_MS&&<span className="ml-1 font-semibold text-amber-800">· GPS gap {Math.round(gapBefore/60000)} min before this point</span>}</span><a target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${encodeURIComponent(selected.latitude)}&mlon=${encodeURIComponent(selected.longitude)}#map=16/${encodeURIComponent(selected.latitude)}/${encodeURIComponent(selected.longitude)}`} className="font-semibold text-forest">Open point on map</a></UiBox>}
   {hasMore&&<button type="button" onClick={()=>void loadMore()} disabled={loadingMore} className="mt-2 text-xs font-semibold text-forest">{loadingMore?"Loading more points…":"Load next 5,000 points"}</button>}
  </>}</div>}
 </div>;
}

export default function FleetLiveTrackingPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (document.hidden) return;
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
  const selected = trips.find(trip => trip.trip_id === selectedTripId) || null;
  const locations = trips.filter(trip => trip.latitude !== null && trip.longitude !== null);
  const liveCount = trips.filter(trip => trip.status === "LIVE").length;
  const staleCount = trips.filter(trip => trip.status === "STALE").length;
  const waitingCount = trips.filter(trip => trip.status === "WAITING_FOR_GPS").length;
  const visibleTrips = trips.filter(trip => `${trip.vehicle} ${trip.driver} ${trip.trip_number} ${trip.origin} ${trip.destination}`.toLowerCase().includes(query.toLowerCase()));

  return <UiMain className="w-full min-w-0 space-y-5 px-4 py-6 sm:px-6 lg:px-8">
    <UiHeader className="flex flex-wrap items-end justify-between gap-3">
      <UiBox>
        <UiText className="text-[11px] font-bold uppercase tracking-[.16em] text-forest">Fleet operations · Control center</UiText>
        <UiH1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Live fleet</UiH1>
        <UiText className="mt-1 max-w-3xl text-sm text-slate-500">Monitor active trips, GPS freshness and estimated arrivals. Locations refresh every 15 seconds.</UiText>
      </UiBox>
      <UiBox className="flex items-center gap-2">
        <UiText className="hidden text-xs text-slate-500 sm:block">{busy ? "Updating locations…" : data?.updated_at ? `Updated ${new Date(data.updated_at).toLocaleTimeString()}` : "Waiting for update"}</UiText>
        <UiButton type="button" onClick={() => void load()} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm font-semibold"><RefreshCw size={14}/>{busy ? "Refreshing…" : "Refresh"}</UiButton>
      </UiBox>
    </UiHeader>

    {error && <WorkflowFeedback message={error} onRefresh={() => void load()}/>}
    <UiSection className="grid grid-cols-2 divide-x divide-line overflow-hidden rounded-xl border border-line bg-white sm:grid-cols-4">
      {[
        { label: "Active trips", value: trips.length, detail: "Currently underway", tone: "text-ink" },
        { label: "Live GPS", value: liveCount, detail: "Updated within 2 min", tone: "text-emerald-700" },
        { label: "Stale GPS", value: staleCount, detail: "Needs a location check", tone: staleCount ? "text-amber-700" : "text-ink" },
        { label: "Waiting for GPS", value: waitingCount, detail: "No trip sample yet", tone: "text-slate-600" },
      ].map(metric => <UiBox key={metric.label} className="min-w-0 px-3 py-3 sm:px-4"><UiText className="text-[11px] font-medium text-slate-500">{metric.label}</UiText><UiText className={`mt-1 text-2xl font-semibold tabular-nums ${metric.tone}`}>{metric.value}</UiText><UiText className="mt-0.5 truncate text-[10px] text-slate-400">{metric.detail}</UiText></UiBox>)}
    </UiSection>

    <UiSection className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
      <UiText className="text-xs leading-5 text-sky-950"><strong>Phone tracking and ETA.</strong> Drivers must allow location access and keep the Driver Phone View open during an active trip. GPS older than two minutes is marked stale. ETA uses configured Google Maps Routes when available, or a historical route median with at least three completed trips. Route restrictions still need operator review.</UiText>
    </UiSection>

    {!trips.length ? <EmptyState title="No active trips to track" description="When a driver starts an assigned trip, KriyoPay will request phone location permission and show the latest update here." actionLabel="Open Fleet & trips" onAction={() => window.location.assign("/fleet")}/> : <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,.85fr)]">
      <div className="min-w-0 space-y-4">
        <FleetLiveMap vehicles={trips} selectedTripId={selectedTripId} onSelect={setSelectedTripId}/>
        <UiSection className="overflow-hidden rounded-xl border border-line bg-white">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
            <div><UiText className="text-sm font-semibold">Active vehicles</UiText><UiText className="mt-0.5 text-[11px] text-slate-500">Select a vehicle to inspect trip and GPS status.</UiText></div>
            <input aria-label="Search active vehicles" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search vehicle, driver or route" className="h-9 w-full rounded-lg border border-line bg-white px-3 text-xs outline-none focus:border-forest focus:ring-2 focus:ring-emerald-100 sm:w-64"/>
          </div>
          <div className="max-h-[390px] divide-y divide-line overflow-y-auto">
            {visibleTrips.map(truck => <button key={truck.trip_id} type="button" onClick={() => setSelectedTripId(truck.trip_id)} aria-pressed={truck.trip_id === selectedTripId} className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-forest ${truck.trip_id === selectedTripId ? "bg-emerald-50/70" : ""}`}>
              <span className="min-w-0"><span className="block truncate text-sm font-semibold text-ink">{truck.vehicle}<span className="ml-2 text-[11px] font-normal text-slate-500">{truck.trip_number}</span></span><span className="mt-0.5 block truncate text-xs text-slate-500">{truck.driver} · {truck.origin || "Origin"} → {truck.destination || "Destination"}</span><span className="mt-1 block text-[10px] text-slate-400">{truck.captured_at ? `GPS ${new Date(truck.captured_at).toLocaleTimeString()}${truck.speed_kmh ? ` · ${Number(truck.speed_kmh).toFixed(0)} km/h` : ""}` : "Waiting for first GPS sample"}</span></span>
              <span className={`h-fit rounded-full px-2 py-1 text-[9px] font-bold ${truck.status === "LIVE" ? "bg-emerald-100 text-emerald-800" : truck.status === "STALE" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"}`}>{truck.status.replaceAll("_", " ")}</span>
            </button>)}
            {!visibleTrips.length && <p className="px-4 py-6 text-center text-xs text-slate-500">No active vehicles match this search.</p>}
          </div>
        </UiSection>
      </div>

      <div className="min-w-0 space-y-4">
        {selected ? <>
          <UiSection className="rounded-xl border border-line bg-white p-4">
            <div className="flex items-start justify-between gap-3"><div><UiText className="text-[10px] font-bold uppercase tracking-wider text-forest">Selected trip</UiText><UiText className="mt-1 text-lg font-semibold">{selected.vehicle}</UiText><UiText className="text-xs text-slate-500">{selected.trip_number} · {selected.driver}</UiText></div><span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${selected.status === "LIVE" ? "bg-emerald-100 text-emerald-800" : selected.status === "STALE" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"}`}>{selected.status.replaceAll("_", " ")}</span></div>
            <div className="my-4 flex items-center gap-2 text-sm"><span className="min-w-0 truncate">{selected.origin || "Origin"}</span><span className="text-slate-400">→</span><span className="min-w-0 truncate font-medium">{selected.destination || "Destination"}</span></div>
            {selected.latitude !== null && selected.longitude !== null ? <div className="rounded-lg bg-slate-50 p-3"><UiText className="text-xs font-semibold tabular-nums">{Number(selected.latitude).toFixed(6)}, {Number(selected.longitude).toFixed(6)}</UiText><UiText className="mt-1 text-[11px] text-slate-500">{selected.speed_kmh ? `${Number(selected.speed_kmh).toFixed(0)} km/h · ` : ""}{selected.accuracy_m ? `GPS accuracy ±${Number(selected.accuracy_m).toFixed(0)} m · ` : ""}{selected.captured_at ? new Date(selected.captured_at).toLocaleString() : ""}</UiText></div> : <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">Waiting for the driver’s first phone GPS update.</p>}
            {selected.stationary_stop && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3"><UiText className="text-xs font-semibold text-amber-950">Stationary · {Math.floor(selected.stationary_stop.stationary_seconds/60)} min</UiText><UiText className="mt-1 text-[11px] leading-5 text-amber-900">{selected.stationary_stop.engine_idle_measured?`Engine-on stationary time measured: ${Math.floor(selected.stationary_stop.engine_idle_seconds/60)} min from consecutive tracker fixes.`:selected.stationary_stop.ignition_on===false?"Latest tracker fix reports ignition off; no engine-idle time counted.":selected.stationary_stop.ignition_on===true?"Ignition is on, but engine-idle time is counted only when consecutive fixes also confirm speed at or below 3 km/h.":"Engine-idle time is unconfirmed because this feed has no ignition evidence."}</UiText></div>}
            {selected.status === "STALE" && selected.age_seconds !== null && <p className="mt-2 text-xs text-amber-800">Last update {Math.floor(selected.age_seconds / 60)} minute(s) ago. Ask the driver to reopen the trip page and check location permission.</p>}
            {selected.estimated_arrival_at && <div className={`mt-3 rounded-lg border p-3 ${selected.delivery_at_risk ? "border-rose-200 bg-rose-50" : "border-line bg-white"}`}><UiText className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Estimated arrival</UiText><UiText className="mt-1 text-sm font-semibold">{new Date(selected.estimated_arrival_at).toLocaleString()}</UiText><UiText className="mt-1 text-[10px] text-slate-500">{selected.eta_method === "GOOGLE_TRAFFIC" ? "Google Maps road and traffic estimate" : `Historical route estimate · ${selected.eta_sample_count} prior trips`}</UiText>{selected.delivery_at_risk && <UiText className="mt-1 text-xs font-semibold text-rose-700">At risk · scheduled {selected.delivery_due_at ? new Date(selected.delivery_due_at).toLocaleString() : ""}</UiText>}</div>}
          </UiSection>
          <TripHistory key={selected.trip_id} tripId={selected.trip_id}/>
        </> : <div className="rounded-xl border border-line bg-white p-5 text-sm text-slate-500">Select a vehicle to see trip details and route history.</div>}
        {!locations.length && <p className="text-[11px] leading-5 text-slate-500">No active vehicle has reported a location. Start a trip with a phone that has GPS permission, or connect a configured GPS provider.</p>}
      </div>
    </div>}
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-[10px] text-slate-400"><span>{data?.updated_at ? `Live feed refreshed ${new Date(data.updated_at).toLocaleString()}` : "Live feed not yet updated"}</span><AppLink href="/fleet" className="font-semibold text-forest">← Fleet & trips</AppLink></div>
  </UiMain>;
}
