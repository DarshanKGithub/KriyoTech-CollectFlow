"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { Search, RefreshCw, ArrowUpRight } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useGridPreferences } from "@/components/grid-preferences";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
type RecordData = Record<string, unknown>;
const pretty = (v: unknown): string => {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return v.toLocaleString("en-IN");
  if (typeof v === "string" && v.includes("T") && !Number.isNaN(Date.parse(v))) return new Date(v).toLocaleString("en-IN");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
};
export function AdminDataTable({ title, description, endpoint, columns }: {title:string;description:string;endpoint:string;columns:string[]}) {
  const [rows,setRows]=useState<RecordData[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState(""),[query,setQuery]=useState(""),[detail,setDetail]=useState<RecordData|null>(null);
  const load=useCallback(async()=>{
    setLoading(true);setError("");setNotice("");
    try {const response=await apiFetch(endpoint);if(!response.ok)throw new Error("Could not load records. Please retry.");const data=await response.json();setRows(Array.isArray(data)?data:(data.results||[]));if(data.gateway_configured===false)setNotice("Razorpay is not configured. These are payment records; checkout is unavailable.");}
    catch(e){setError(e instanceof Error?e.message:"Could not load records.");}finally{setLoading(false);}
  },[endpoint]);
  useEffect(()=>{void load();},[load]);
  const {ready:_ready,...preferences}=useGridPreferences(`admin:${endpoint}`);
  const signature=columns.join("\u0000");
  const gridColumns=useMemo<GridColDef[]>(()=>[...signature.split("\u0000").map<GridColDef>(field=>({field,headerName:field.replaceAll("_"," "),minWidth:160,flex:1,valueGetter:(_:unknown,row:RecordData)=>row[field],valueFormatter:(value:unknown)=>pretty(value),...(field.includes("status")?{renderCell:({value})=><Badge variant="secondary" className="font-medium">{pretty(value)}</Badge>}: {})})),{field:"details",headerName:"Details",width:100,sortable:false,filterable:false,disableExport:true,renderCell:({row})=><Button size="sm" variant="ghost" aria-label={`View ${title} record`} onClick={()=>setDetail(row)}>View<ArrowUpRight className="ml-1 size-3"/></Button>}],[signature,title]);
  const data=useMemo(()=>rows.map((record,index)=>({...record,id:String(record.id??index)})).filter(row=>!query||columns.some(field=>pretty((row as RecordData)[field]).toLowerCase().includes(query.toLowerCase()))),[rows,query,columns]);
  return <section className="space-y-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-semibold tracking-tight">{title}</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p></div><Button variant="outline" size="sm" disabled={loading} onClick={()=>void load()}><RefreshCw className="mr-2 size-4"/>Refresh</Button></div>
    {notice&&<div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{notice}</div>}
    {error?<div role="alert" className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}<Button variant="outline" onClick={()=>void load()}>Retry</Button></div>:<Card className="overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div className="relative w-full sm:max-w-xs"><Search className="absolute left-3 top-3 size-4 text-muted-foreground"/><Input aria-label={`Search loaded ${title.toLowerCase()} records`} placeholder="Search loaded records…" value={query} onChange={e=>setQuery(e.target.value)} className="pl-9"/></div><Badge variant="secondary">{loading?"Loading…":`${data.length} loaded records`}</Badge></div>{loading?<div aria-label={`Loading ${title}`} className="space-y-5 p-6">{[1,2,3,4,5,6].map(n=><Skeleton key={n} className="h-9 w-full"/>)}</div>:<div className="h-[500px] min-w-0"><DataGrid {...preferences} rows={data} columns={gridColumns} showToolbar disableRowSelectionOnClick pageSizeOptions={[10,25,50]} initialState={{pagination:{paginationModel:{page:0,pageSize:10}}}} slotProps={{toolbar:{csvOptions:{disableToolbarButton:true},printOptions:{disableToolbarButton:true}}}} localeText={{noRowsLabel:query?"No matching records. Try another search.":"No records yet."}} sx={{border:0,fontSize:12}}/></div>}</Card>}
    <Sheet open={Boolean(detail)} onOpenChange={open=>{if(!open)setDetail(null);}}><SheetContent className="overflow-y-auto sm:max-w-lg"><SheetHeader><SheetTitle>Record details</SheetTitle><SheetDescription>{title} · Current loaded record</SheetDescription></SheetHeader><dl className="mt-6 divide-y">{detail&&Object.entries(detail).map(([key,value])=><div key={key} className="py-3"><dt className="text-xs font-medium capitalize text-muted-foreground">{key.replaceAll("_"," ")}</dt><dd className="mt-1 break-words text-sm">{pretty(value)}</dd></div>)}</dl></SheetContent></Sheet>
  </section>;
}

