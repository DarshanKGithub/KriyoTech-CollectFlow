"use client";

/* Uses the workspace's configured, attributed tile provider; no location data is simulated. */
/* eslint-disable @next/next/no-img-element */
import { useEffect, useMemo, useRef, useState } from "react";
import { LocateFixed, Maximize, Minimize, Truck } from "lucide-react";

export type FleetMapVehicle = {
  trip_id: string;
  vehicle: string;
  status: "LIVE" | "STALE" | "WAITING_FOR_GPS";
  latitude: string | null;
  longitude: string | null;
};

const TILE = 256;
const MAX_LAT = 85.05112878;
const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL_TEMPLATE || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION || "© OpenStreetMap contributors";
const ATTRIBUTION_URL = process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION_URL || "https://www.openstreetmap.org/copyright";

function world(latitude: number, longitude: number, zoom: number) {
  const scale = 2 ** zoom;
  const lat = Math.max(-MAX_LAT, Math.min(MAX_LAT, latitude));
  const sin = Math.sin(lat * Math.PI / 180);
  return {
    x: ((longitude + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale,
  };
}

function fitZoom(vehicles: FleetMapVehicle[], width: number, height: number) {
  const points = vehicles.flatMap(vehicle => {
    const lat = Number(vehicle.latitude), lon = Number(vehicle.longitude);
    return vehicle.latitude !== null && vehicle.longitude !== null && Number.isFinite(lat) && Number.isFinite(lon)
      ? [{ lat, lon }] : [];
  });
  if (points.length < 2) return 12;
  const minLat = Math.min(...points.map(point => point.lat));
  const maxLat = Math.max(...points.map(point => point.lat));
  const minLon = Math.min(...points.map(point => point.lon));
  const maxLon = Math.max(...points.map(point => point.lon));
  const xRange = Math.max((maxLon - minLon) / 360, 0.0001);
  const north = world(maxLat, 0, 0).y;
  const south = world(minLat, 0, 0).y;
  const yRange = Math.max(south - north, 0.0001);
  return Math.max(3, Math.min(15, Math.floor(Math.min(Math.log2(width / TILE / xRange), Math.log2(height / TILE / yRange)) - 1)));
}

export function FleetLiveMap({ vehicles, selectedTripId, onSelect, compact = false, fillWindow = false, fitPanel = false }: {
  vehicles: FleetMapVehicle[];
  selectedTripId: string | null;
  onSelect: (tripId: string) => void;
  compact?: boolean;
  fillWindow?: boolean;
  fitPanel?: boolean;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const mapSection = useRef<HTMLElement>(null);
  const fullscreenButton = useRef<HTMLButtonElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenError, setFullscreenError] = useState("");
  const [size, setSize] = useState({ width: 900, height: 440 });
  const [zoomOffset, setZoomOffset] = useState(0);
  useEffect(() => {
    if (!fillWindow) return;
    const section = mapSection.current;
    let wasFullscreen = false;
    function syncFullscreen() {
      const active = document.fullscreenElement === section;
      setFullscreen(active);
      if (wasFullscreen && !active) fullscreenButton.current?.focus();
      wasFullscreen = active;
    }
    document.addEventListener("fullscreenchange", syncFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncFullscreen);
  }, [fillWindow]);

  async function toggleFullscreen() {
    const section = mapSection.current;
    if (!section) return;
    setFullscreenError("");
    try {
      if (document.fullscreenElement === section) await document.exitFullscreen();
      else await section.requestFullscreen();
    } catch {
      setFullscreenError("Full screen is unavailable in this browser window.");
    }
  }
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect;
      if (rect?.width && rect.height) setSize({ width: rect.width, height: rect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const plotted = vehicles.flatMap(vehicle => {
    const latitude = Number(vehicle.latitude), longitude = Number(vehicle.longitude);
    return vehicle.latitude !== null && vehicle.longitude !== null && Number.isFinite(latitude) && Number.isFinite(longitude)
      ? [{ vehicle, latitude, longitude }] : [];
  });
  const zoom = Math.max(3, Math.min(18, fitZoom(vehicles, size.width, size.height) + zoomOffset));
  const center = useMemo(() => {
    if (!plotted.length) return { latitude: 20.5937, longitude: 78.9629 };
    return {
      latitude: (Math.min(...plotted.map(point => point.latitude)) + Math.max(...plotted.map(point => point.latitude))) / 2,
      longitude: (Math.min(...plotted.map(point => point.longitude)) + Math.max(...plotted.map(point => point.longitude))) / 2,
    };
  // Coordinates are primitive values; updating the list refreshes the projection.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vehicles.map(vehicle => `${vehicle.latitude},${vehicle.longitude}`).join("|")]);
  const map = useMemo(() => {
    const origin = world(center.latitude, center.longitude, zoom);
    const columns = Math.ceil(size.width / TILE) + 2;
    const rows = Math.ceil(size.height / TILE) + 2;
    const firstX = Math.floor(origin.x - size.width / (2 * TILE));
    const firstY = Math.floor(origin.y - size.height / (2 * TILE));
    const scale = 2 ** zoom;
    const tiles = [];
    for (let row = 0; row < rows; row++) for (let column = 0; column < columns; column++) {
      const x = firstX + column, y = firstY + row;
      if (y < 0 || y >= scale) continue;
      const wrappedX = ((x % scale) + scale) % scale;
      tiles.push({ key: `${zoom}/${x}/${y}`, src: TILE_URL.replaceAll("{z}", String(zoom)).replaceAll("{x}", String(wrappedX)).replaceAll("{y}", String(y)), left: (x - origin.x) * TILE + size.width / 2, top: (y - origin.y) * TILE + size.height / 2 });
    }
    return { tiles, markers: plotted.map(({ vehicle, latitude, longitude }) => {
      const point = world(latitude, longitude, zoom);
      return { vehicle, left: (point.x - origin.x) * TILE + size.width / 2, top: (point.y - origin.y) * TILE + size.height / 2 };
    }) };
  }, [center, plotted, size, zoom]);

  return <section ref={mapSection} aria-label="Fleet location map" className={`overflow-hidden bg-white ${fullscreen ? "flex h-full w-full flex-col" : fitPanel ? "fleet-control-map flex flex-col" : "rounded-xl border border-line"}`}>
    <div className={`flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-line px-4 ${fitPanel ? "py-1.5" : "py-3"}`}>
      <div className="flex items-center gap-2 text-sm font-semibold"><LocateFixed size={16} className="text-forest"/> Fleet map <span className="text-xs font-normal text-slate-500">{plotted.length} reporting location{plotted.length === 1 ? "" : "s"}</span></div>
      <div className="flex items-center gap-3 text-[11px] text-slate-500"><span className="inline-flex items-center gap-1"><i className="size-2 rounded-full bg-emerald-600"/>Live</span><span className="inline-flex items-center gap-1"><i className="size-2 rounded-full bg-amber-500"/>Stale</span><div className="flex overflow-hidden rounded-md border border-line"><button type="button" aria-label="Zoom in" onClick={() => setZoomOffset(value => Math.min(6, value + 1))} className="px-2 py-1 hover:bg-slate-50">+</button><button type="button" aria-label="Zoom out" onClick={() => setZoomOffset(value => Math.max(-6, value - 1))} className="border-l border-line px-2 py-1 hover:bg-slate-50">−</button></div></div>
      {fillWindow && <button ref={fullscreenButton} type="button" onClick={() => void toggleFullscreen()}
        className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-forest hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest">
        {fullscreen ? <Minimize size={15} aria-hidden="true"/> : <Maximize size={15} aria-hidden="true"/>}
        {fullscreen ? "Exit full screen" : "Full screen"}
      </button>}
    </div>
    {fullscreenError && <p role="status" className="border-b border-line px-4 py-2 text-xs text-amber-900">{fullscreenError}</p>}
    <div ref={viewport} className={`fleet-map-viewport relative isolate overflow-hidden bg-[#e9eeeb] ${fullscreen ? "min-h-0 flex-1" : fillWindow ? "h-[360px] sm:h-[460px] lg:h-[max(460px,calc(100dvh-17rem))]" : compact ? "h-[300px] sm:h-[360px]" : "h-[360px] sm:h-[460px]"}`}>
      {map.tiles.map(tile => <img key={tile.key} src={tile.src} alt="" aria-hidden="true" draggable={false} className="pointer-events-none absolute max-w-none select-none" style={{ left: tile.left, top: tile.top, width: TILE, height: TILE }}/>) }
      {map.markers.map(({ vehicle, left, top }) => {
        const active = vehicle.trip_id === selectedTripId;
        const tone = vehicle.status === "LIVE" ? "bg-emerald-700" : "bg-amber-600";
        return <button key={vehicle.trip_id} type="button" onClick={() => onSelect(vehicle.trip_id)} aria-label={`${vehicle.vehicle}, ${vehicle.status.replaceAll("_", " ")}`} aria-pressed={active} className={`absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 rounded-full border-2 border-white px-2.5 py-1.5 text-[11px] font-bold text-white shadow-md transition-transform hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest ${tone} ${active ? "z-20 ring-2 ring-slate-900 ring-offset-1" : "z-10"}`} style={{ left, top }}><Truck size={13}/>{vehicle.vehicle}</button>;
      })}
      {!plotted.length && <div className="absolute inset-0 grid place-items-center"><div className="max-w-xs rounded-xl border border-line bg-white/95 p-5 text-center shadow-sm"><LocateFixed className="mx-auto text-slate-400" size={24}/><p className="mt-2 text-sm font-semibold">No GPS coordinates yet</p><p className="mt-1 text-xs leading-5 text-slate-500">Active trips appear on this map after a driver phone or GPS provider reports a location.</p></div></div>}
      <a href={ATTRIBUTION_URL} target="_blank" rel="noreferrer" className="absolute bottom-2 right-2 z-30 rounded bg-white/90 px-2 py-1 text-[10px] text-slate-700 shadow">{ATTRIBUTION}</a>
    </div>
    <p className={`shrink-0 border-t border-line bg-slate-50 px-3 text-[10px] text-slate-500 ${fitPanel ? "py-1" : "py-2"}`}>Map tiles use the configured provider. Requested map areas are sent to that provider. Markers reflect the latest API location and do not imply a continuous route.</p>
  </section>;
}
