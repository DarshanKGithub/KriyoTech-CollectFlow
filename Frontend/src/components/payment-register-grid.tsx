"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Box, Button, LinearProgress, Stack, TextField, Typography } from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { TransactionDetails } from "@/components/transaction-details";
import { Money, FinancialStatus } from "@/components/financial-ui";
import { financialDate, apiError, type LedgerPayment } from "@/lib/finance";
import { apiFetch } from "@/lib/api";
import { useGridPreferences } from "@/components/grid-preferences";
import { GridDensityControl } from "@/components/grid-density-control";

export function PaymentRegisterGrid({vendors,refreshVersion=0}:{vendors:{id:string;name:string}[];refreshVersion?:number}) {
  const [selected,setSelected]=useState<LedgerPayment|null>(null),[payments,setPayments]=useState<LedgerPayment[]>([]);
  const [pagination,setPagination]=useState({page:0,pageSize:25}),[count,setCount]=useState(0),[total,setTotal]=useState<string|null>(null);
  const [search,setSearch]=useState(""),[query,setQuery]=useState(""),[from,setFrom]=useState(""),[to,setTo]=useState("");
  const [loading,setLoading]=useState(false),[error,setError]=useState("");
  const sequence=useRef({value:0});
  const {ready:_ready,...preferences}=useGridPreferences("payments",[{field:"paid_at",sort:"desc"}]);
  const sorting=preferences.sortModel[0];
  const sort=(sorting?.sort==="asc"?"":"-")+(["paid_at","amount","reference_number","mode"].includes(sorting?.field||"")?sorting.field:"paid_at");
  useEffect(()=>{const timer=setTimeout(()=>setQuery(search),300);return()=>clearTimeout(timer);},[search]);
  useEffect(()=>{setPagination(value=>({...value,page:0}));},[query,from,to,sort]);
  const load=useCallback(async()=>{
    const request=++sequence.current.value;setLoading(true);setError("");
    try {
      if(from&&to&&from>to)throw new Error("End date must follow start date.");
      const params=new URLSearchParams({paginated:"1",page:String(pagination.page+1),page_size:String(pagination.pageSize),search:query,sort});
      if(from)params.set("from",from);if(to)params.set("to",to);
      const response=await apiFetch("/payments?"+params);const data=await response.json();
      if(!response.ok||!Array.isArray(data.results))throw new Error(apiError(data,"Could not load the payment register."));
      if(request===sequence.current.value){setPayments(data.results);setCount(data.count);setTotal(data.total_recorded_amount);}
    }catch(e){if(request===sequence.current.value){setPayments([]);setCount(0);setTotal(null);setError((e as Error).message);}}
    finally{if(request===sequence.current.value)setLoading(false);}
  },[pagination.page,pagination.pageSize,query,sort,from,to]);
  useEffect(()=>{const tracker=sequence.current;void load();return()=>{tracker.value++;};},[load,refreshVersion]);
  const columns=useMemo<GridColDef<LedgerPayment>[]>(()=>[
    {field:"paid_at",headerName:"Payment date",width:150,valueFormatter:value=>financialDate(String(value))},
    {field:"vendor",headerName:"Supplier",minWidth:180,flex:1.5,sortable:false,valueGetter:(_,row)=>row.vendor_name||vendors.find(item=>item.id===row.vendor)?.name||"Supplier not provided"},
    {field:"amount",headerName:"Ledger amount · INR",width:180,renderCell:({row})=><Money value={row.amount}/>},
    {field:"mode",headerName:"Method",width:150,valueFormatter:value=>String(value).replaceAll("_"," ")},
    {field:"reference_number",headerName:"Reference",minWidth:180,flex:1},
    {field:"allocations",headerName:"Invoices",width:95,sortable:false,valueGetter:(_,row)=>row.allocations.length},
    {field:"record_status",headerName:"Record status",width:170,sortable:false,renderCell:()=> <FinancialStatus status="RECORDED"/>},
    {field:"details",headerName:"Details",width:120,sortable:false,disableExport:true,renderCell:({row})=><Button onClick={()=>setSelected(row)}>View details</Button>}
  ],[vendors]);
  return <><Stack direction={{xs:"column",md:"row"}} spacing={2} sx={{p:2}}><TextField label="Search all recorded payments" value={search} onChange={event=>setSearch(event.target.value)} slotProps={{htmlInput:{maxLength:120}}} sx={{flex:1}}/><TextField label="From date" type="date" value={from} onChange={event=>setFrom(event.target.value)} slotProps={{inputLabel:{shrink:true}}}/><TextField label="To date" type="date" value={to} onChange={event=>setTo(event.target.value)} slotProps={{inputLabel:{shrink:true}}}/></Stack>
    {error&&<Alert severity="error" action={<Button onClick={()=>void load()}>Retry</Button>}>{error}</Alert>}
    <Typography variant="body2" sx={{px:2,pb:2}}>{count} filtered active payments · Recorded total {total!==null?<Money value={total}/>:"unavailable"}. Internal ledger total, not a bank balance.</Typography>
    {loading&&<LinearProgress aria-label="Loading payment register"/>}
    <Box sx={{height:520,display:"flex",flexDirection:"column"}}><GridDensityControl value={preferences.density} onChange={preferences.onDensityChange}/><DataGrid {...preferences} rows={payments} columns={columns} loading={loading} rowCount={count} paginationMode="server" sortingMode="server" paginationModel={pagination} onPaginationModelChange={setPagination} disableColumnFilter disableRowSelectionOnClick showToolbar pageSizeOptions={[10,25,50,100]} slotProps={{toolbar:{showQuickFilter:false,csvOptions:{disableToolbarButton:true},printOptions:{disableToolbarButton:true}}}} sx={{flex:1,minHeight:0,border:0,fontSize:13}}/></Box>
    <TransactionDetails payment={selected} counterparty={selected?.vendor_name||vendors.find(item=>item.id===selected?.vendor)?.name||"Supplier"} onClose={()=>setSelected(null)}/></>;
}
