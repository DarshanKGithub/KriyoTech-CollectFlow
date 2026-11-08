"use client";

/* eslint-disable @next/next/no-img-element */

import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, MousePointer2, Plus, Undo2 } from "lucide-react";

const TILE = 256;
const MAX_LAT = 85.05112878;
const DEFAULT_CENTER = { latitude: 18.5204, longitude: 73.8567 };
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

function geographic(x: number, y: number, zoom: number): [number, number] {
  const scale = 2 ** zoom;
  const longitude = x / scale * 360 - 180;
  const latitude = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / scale))) * 180 / Math.PI;
  return [longitude, latitude];
}

export function GeofenceMapEditor({
  shape,
  center,
  radiusM,
  points,
  onPickCenter,
  onAddPoint,
  onUndoPoint,
}: {
  shape: "CIRCLE" | "POLYGON";
  center: { latitude: number; longitude: number } | null;
  radiusM: number;
  points: [number, number][];
  onPickCenter: (latitude: number, longitude: number) => void;
  onAddPoint: (longitude: number, latitude: number) => void;
  onUndoPoint: () => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; x: number; y: number; originX: number; originY: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const [size, setSize] = useState({ width: 840, height: 340 });
  const [zoom, setZoom] = useState(13);
  const [panCenter, setPanCenter] = useState<{ latitude: number; longitude: number } | null>(null);
  const mapCenter = useMemo(() => {
    if (panCenter) return panCenter;
    if (center) return center;
    if (shape === "POLYGON" && points.length) {
      return {
        longitude: points.reduce((sum, point) => sum + point[0], 0) / points.length,
        latitude: points.reduce((sum, point) => sum + point[1], 0) / points.length,
      };
    }
    return DEFAULT_CENTER;
  }, [center, panCenter, points, shape]);

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

  const map = useMemo(() => {
    const origin = world(mapCenter.latitude, mapCenter.longitude, zoom);
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
      tiles.push({
        key: `${zoom}/${x}/${y}`,
        src: TILE_URL.replaceAll("{z}", String(zoom)).replaceAll("{x}", String(wrappedX)).replaceAll("{y}", String(y)),
        left: (x - origin.x) * TILE + size.width / 2,
        top: (y - origin.y) * TILE + size.height / 2,
      });
    }
    const project = (longitude: number, latitude: number) => {
      const point = world(latitude, longitude, zoom);
      return [(point.x - origin.x) * TILE + size.width / 2, (point.y - origin.y) * TILE + size.height / 2] as const;
    };
    const projectedPoints = points.map(([longitude, latitude]) => project(longitude, latitude));
    const selectedCenter = center ? project(center.longitude, center.latitude) : null;
    const radiusPixels = center ? radiusM * TILE * scale / (2 * Math.PI * 6_371_008.8 * Math.max(0.01, Math.cos(center.latitude * Math.PI / 180))) : 0;
    return { tiles, projectedPoints, selectedCenter, radiusPixels };
  }, [center, mapCenter, points, radiusM, size, zoom]);

  function handleMapClick(event: React.MouseEvent<HTMLDivElement>) {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const origin = world(mapCenter.latitude, mapCenter.longitude, zoom);
    const [longitude, latitude] = geographic(
      origin.x + (event.clientX - rect.left - rect.width / 2) / TILE,
      origin.y + (event.clientY - rect.top - rect.height / 2) / TILE,
      zoom,
    );
    if (shape === "CIRCLE") onPickCenter(latitude, longitude);
    else onAddPoint(longitude, latitude);
  }

  function startPan(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const origin = world(mapCenter.latitude, mapCenter.longitude, zoom);
    drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY,
      originX: origin.x, originY: origin.y, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function movePan(event: React.PointerEvent<HTMLDivElement>) {
    const active = drag.current;
    if (!active || active.pointerId !== event.pointerId) return;
    const dx = event.clientX - active.x, dy = event.clientY - active.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) active.moved = true;
    if (!active.moved) return;
    const [longitude, latitude] = geographic(active.originX - dx / TILE, active.originY - dy / TILE, zoom);
    setPanCenter({ latitude, longitude });
  }

  function endPan(event: React.PointerEvent<HTMLDivElement>) {
    if (drag.current?.pointerId !== event.pointerId) return;
    suppressClick.current = drag.current.moved;
    drag.current = null;
  }

  return <section className="overflow-hidden rounded-xl border border-line bg-white" aria-label="Geofence map editor">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2.5">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-800"><MousePointer2 size={14} className="text-forest"/>{shape === "CIRCLE" ? "Click the map to place the site centre" : "Click the map to add polygon vertices"}</div>
      <div className="flex items-center gap-2">
        {shape === "POLYGON" && <span className="mr-1 text-[11px] text-slate-500">{points.length} point{points.length === 1 ? "" : "s"} · need 3+</span>}
        <button type="button" aria-label="Zoom out" onClick={() => setZoom(value => Math.max(3, value - 1))} className="rounded border border-line p-1.5 text-slate-700 hover:bg-slate-50"><Minus size={14}/></button>
        <span className="w-9 text-center text-[11px] tabular-nums text-slate-500">{zoom}×</span>
        <button type="button" aria-label="Zoom in" onClick={() => setZoom(value => Math.min(18, value + 1))} className="rounded border border-line p-1.5 text-slate-700 hover:bg-slate-50"><Plus size={14}/></button>
      </div>
    </div>
    <div ref={viewport} onPointerDown={startPan} onPointerMove={movePan} onPointerUp={endPan} onPointerCancel={endPan} onClick={handleMapClick} className="relative h-[300px] touch-none cursor-grab overflow-hidden bg-[#e9eeeb] active:cursor-grabbing sm:h-[340px]">
      {map.tiles.map(tile => <img key={tile.key} src={tile.src} alt="" aria-hidden="true" draggable={false} className="pointer-events-none absolute max-w-none select-none" style={{ left: tile.left, top: tile.top, width: TILE, height: TILE }}/>) }
      <svg className="pointer-events-none absolute inset-0 size-full overflow-visible" aria-hidden="true">
        {shape === "POLYGON" && map.projectedPoints.length > 0 && <>
          {map.projectedPoints.length >= 3 && <polygon points={map.projectedPoints.map(([x, y]) => `${x},${y}`).join(" ")} fill="rgba(22, 115, 74, .14)" stroke="#16734A" strokeWidth="2.5"/>}
          {map.projectedPoints.length > 1 && <polyline points={map.projectedPoints.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke="#16734A" strokeWidth="2.5" strokeDasharray="6 4"/>}
          {map.projectedPoints.map(([x, y], index) => <circle key={index} cx={x} cy={y} r="5" fill="#fff" stroke="#16734A" strokeWidth="2.5"/>)}
        </>}
        {shape === "CIRCLE" && map.selectedCenter && <>
          <circle cx={map.selectedCenter[0]} cy={map.selectedCenter[1]} r={Math.max(3, map.radiusPixels)} fill="rgba(22, 115, 74, .14)" stroke="#16734A" strokeWidth="2.5"/>
          <circle cx={map.selectedCenter[0]} cy={map.selectedCenter[1]} r="5" fill="#fff" stroke="#16734A" strokeWidth="2.5"/>
        </>}
      </svg>
      <a href={ATTRIBUTION_URL} target="_blank" rel="noreferrer" onClick={event => event.stopPropagation()} className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-[10px] text-slate-700 shadow">{ATTRIBUTION}</a>
    </div>
    <div className="flex items-center justify-between gap-2 border-t border-line bg-slate-50 px-3 py-2 text-[10px] text-slate-500">
      <span>{shape === "CIRCLE" && center ? `${center.latitude.toFixed(5)}, ${center.longitude.toFixed(5)} · ${radiusM} m radius` : "Map taps set coordinates; verify the outline before saving."}</span>
      {shape === "POLYGON" && points.length > 0 && <button type="button" onClick={onUndoPoint} className="inline-flex items-center gap-1 font-semibold text-forest"><Undo2 size={12}/>Undo last point</button>}
    </div>
    <p className="px-3 py-1.5 text-[10px] leading-4 text-slate-400">Map requests are sent to the configured tile provider. Coordinates are saved only when you submit the site form.</p>
  </section>;
}
