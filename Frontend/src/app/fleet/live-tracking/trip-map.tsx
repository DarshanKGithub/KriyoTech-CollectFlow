"use client";
/* Map tiles are remote, viewport-sized images; Next's image optimizer must not proxy them. */
/* eslint-disable @next/next/no-img-element */

import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus } from "lucide-react";

export type MapPoint = { latitude:string;longitude:string;captured_at:string;speed_kmh:string|null;accuracy_m:string|null };

const TILE_SIZE = 256;
const MAX_LATITUDE = 85.05112878;
const GPS_GAP_MS = 2 * 60 * 1000;
const TILE_URL_TEMPLATE = process.env.NEXT_PUBLIC_MAP_TILE_URL_TEMPLATE || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION = process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION || "© OpenStreetMap contributors";
const TILE_ATTRIBUTION_URL = process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION_URL || "https://www.openstreetmap.org/copyright";

function worldPoint(point:MapPoint, zoom:number) {
  const scale = 2 ** zoom;
  const latitude = Math.max(-MAX_LATITUDE, Math.min(MAX_LATITUDE, Number(point.latitude)));
  const longitude = Number(point.longitude);
  const sin = Math.sin(latitude * Math.PI / 180);
  return {
    x: ((longitude + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale,
  };
}

export function TripMap({ points, selectedIndex }:{points:MapPoint[];selectedIndex:number}) {
  const [zoom,setZoom] = useState(12);
  const [size,setSize] = useState({width:900,height:330});
  const viewportRef = useRef<HTMLDivElement>(null);
  const selected = points[selectedIndex];
  useEffect(()=>{
    const element=viewportRef.current;
    if(!element)return;
    const observer=new ResizeObserver(entries=>{
      const rect=entries[0]?.contentRect;
      if(rect?.width&&rect.height)setSize({width:rect.width,height:rect.height});
    });
    observer.observe(element);
    return()=>observer.disconnect();
  },[]);
  const map = useMemo(() => {
    if (!selected) return null;
    const scale = 2 ** zoom;
    const center = worldPoint(selected, zoom);
    const columns = Math.ceil(size.width / TILE_SIZE) + 2;
    const rows = Math.ceil(size.height / TILE_SIZE) + 2;
    const firstX = Math.floor(center.x - size.width / (2 * TILE_SIZE));
    const firstY = Math.floor(center.y - size.height / (2 * TILE_SIZE));
    const tiles = [];
    for (let row=0;row<rows;row++) for (let column=0;column<columns;column++) {
      const x = firstX + column;
      const y = firstY + row;
      if (y < 0 || y >= scale) continue;
      const wrappedX = ((x % scale) + scale) % scale;
      const src=TILE_URL_TEMPLATE.replaceAll("{z}",String(zoom)).replaceAll("{x}",String(wrappedX)).replaceAll("{y}",String(y));
      tiles.push({key:`${zoom}/${x}/${y}`,src,left:(x-center.x)*TILE_SIZE+size.width/2,top:(y-center.y)*TILE_SIZE+size.height/2});
    }
    const screenPoint = (point:MapPoint) => {
      const world = worldPoint(point, zoom);
      return {x:(world.x-center.x)*TILE_SIZE+size.width/2,y:(world.y-center.y)*TILE_SIZE+size.height/2};
    };
    const continuousSegments:MapPoint[][]=[];
    const gaps:{from:MapPoint;to:MapPoint;minutes:number}[]=[];
    points.forEach((point,index)=>{
      const previous=points[index-1];
      if(index===0||new Date(point.captured_at).getTime()-new Date(previous.captured_at).getTime()<=GPS_GAP_MS){
        if(!continuousSegments.length)continuousSegments.push([]);
        continuousSegments[continuousSegments.length-1].push(point);
      }else{
        gaps.push({from:previous,to:point,minutes:Math.round((new Date(point.captured_at).getTime()-new Date(previous.captured_at).getTime())/60000)});
        continuousSegments.push([point]);
      }
    });
    const paths=continuousSegments.filter(segment=>segment.length>1).map(segment=>segment.map((point,index)=>{
      const position=screenPoint(point);
      return `${index?"L":"M"} ${position.x.toFixed(1)} ${position.y.toFixed(1)}`;
    }).join(" "));
    const gapSegments=gaps.map(gap=>({from:screenPoint(gap.from),to:screenPoint(gap.to),minutes:gap.minutes}));
    return {tiles,paths,gapSegments,selectedPosition:screenPoint(selected),startPosition:screenPoint(points[0]),endPosition:screenPoint(points[points.length-1])};
  },[points,selected,size,zoom]);

  if (!selected || !map) return null;
  return <div className="relative mt-2 overflow-hidden rounded-lg border border-slate-200 bg-[#DCE5E0]">
    <div ref={viewportRef} className="relative h-[260px] w-full sm:h-[330px]">
      <div className="absolute inset-0 overflow-hidden">
        {map.tiles.map(tile=><img key={tile.key} src={tile.src} alt="" aria-hidden="true" draggable={false} className="pointer-events-none absolute max-w-none select-none" style={{left:tile.left,top:tile.top,width:TILE_SIZE,height:TILE_SIZE}}/>)}
        <svg role="img" aria-label="Recorded GPS route, start, destination, and selected playback position" viewBox={`0 0 ${size.width} ${size.height}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-hidden">
          {map.paths.map((path,index)=><path key={`route-${index}`} d={path} fill="none" stroke="#16734A" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" opacity=".9"/>)}
          {map.gapSegments.map((gap,index)=><g key={`gap-${index}`}><path d={`M ${gap.from.x.toFixed(1)} ${gap.from.y.toFixed(1)} L ${gap.to.x.toFixed(1)} ${gap.to.y.toFixed(1)}`} fill="none" stroke="#d97706" strokeWidth="4" strokeDasharray="7 7" strokeLinecap="round" opacity=".9"><title>No GPS fixes for approximately {gap.minutes} minutes</title></path><circle cx={gap.from.x} cy={gap.from.y} r="5" fill="#f59e0b" stroke="white" strokeWidth="2"/><circle cx={gap.to.x} cy={gap.to.y} r="5" fill="#f59e0b" stroke="white" strokeWidth="2"/></g>)}
          {points.length>1&&<><circle cx={map.startPosition.x} cy={map.startPosition.y} r="7" fill="#16734A" stroke="white" strokeWidth="3"/><circle cx={map.endPosition.x} cy={map.endPosition.y} r="7" fill="#be123c" stroke="white" strokeWidth="3"/></>}
          <circle cx={map.selectedPosition.x} cy={map.selectedPosition.y} r="9" fill="#16734A" stroke="white" strokeWidth="4"/>
        </svg>
      </div>
      <div className="absolute right-2 top-2 grid overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm">
        <button type="button" aria-label="Zoom in" onClick={()=>setZoom(value=>Math.min(18,value+1))} disabled={zoom>=18} className="grid size-9 place-items-center text-slate-700 hover:bg-slate-50 disabled:opacity-40"><Plus size={16}/></button>
        <button type="button" aria-label="Zoom out" onClick={()=>setZoom(value=>Math.max(3,value-1))} disabled={zoom<=3} className="grid size-9 place-items-center border-t border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40"><Minus size={16}/></button>
      </div>
      <div className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-[10px] text-slate-700 shadow">Zoom {zoom}{map.gapSegments.length>0&&<span className="ml-2 text-amber-800">Dashed amber: GPS gap over 2 min</span>}</div>
      <a href={TILE_ATTRIBUTION_URL} target="_blank" rel="noreferrer" className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-[10px] text-slate-700 shadow">{TILE_ATTRIBUTION}</a>
    </div>
    <p className="border-t border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-500">Map tiles are provided by the configured map service. Requested map areas are sent to that provider.</p>
  </div>;
}
