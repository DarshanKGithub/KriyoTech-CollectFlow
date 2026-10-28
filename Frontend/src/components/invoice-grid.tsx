"use client";
import { GridDensityControl } from "@/components/grid-density-control";

import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useGridPreferences } from "@/components/grid-preferences";
import { ProcessingStatus } from "@/components/processing-status";

type InvoiceRow = {id:string;invoice_number:string;vendor_name?:string;supplier_name?:string;invoice_date?:string;invoice_total:string;status:string;extraction_error?:string;automation?:{status?:string;message?:string}};
const label = (value:string)=>value.replaceAll("_"," ").toLowerCase();
export function InvoiceGrid<T extends InvoiceRow>({rows,total,page,pageSize,actions,busy,onOrderingChange}: {
  rows:T[];total:number;page:number;pageSize:number;actions:(invoice:T)=>ReactNode;busy:string;onOrderingChange?:(value:string)=>void;
}) {
  const preferences=useGridPreferences("invoices");
  const {ready,columnVisibilityModel,onColumnVisibilityModelChange,density,onDensityChange,sortModel,onSortModelChange}=preferences;
  useEffect(()=>{if(!ready)return;const item=sortModel[0];onOrderingChange?.(item&&["invoice_date","invoice_total"].includes(item.field)?`${item.sort==="desc"?"-":""}${item.field}`:"-created_at");},[ready,sortModel,onOrderingChange]);
  const actionRef=useRef(actions);actionRef.current=actions;
  const columns=useMemo<GridColDef<T>[]>(()=>[
    {field:"supplier",headerName:"Supplier",minWidth:180,flex:1.2,sortable:false,valueGetter:(_,row)=>row.vendor_name||row.supplier_name||"Supplier to review"},
    {field:"invoice_number",headerName:"Invoice number",minWidth:150,flex:1,sortable:false},
    {field:"invoice_date",headerName:"Date",minWidth:115,sortable:true},
    {field:"invoice_total",headerName:"Amount",type:"number",minWidth:140,sortable:true,valueGetter:value=>Number(value),valueFormatter:value=>new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR"}).format(Number(value||0))},
    {field:"status",headerName:"Status",minWidth:250,flex:1.3,sortable:false,renderCell:({row})=><Box sx={{py:1}}><ProcessingStatus status={row.status} label={label(row.status)} />{row.automation?.status&&<Typography variant="caption" color={["NEEDS_ATTENTION","FAILED"].includes(row.automation.status)?"warning.main":"text.secondary"} sx={{display:"block",whiteSpace:"normal",mt:0.5,lineHeight:1.5}}>{row.automation.status.replaceAll("_"," ").toLowerCase()} · {row.automation.message}</Typography>}{row.extraction_error&&<Typography variant="caption" color="error" sx={{display:"block",whiteSpace:"normal",mt:0.5}}>{row.extraction_error}</Typography>}</Box>},
    {field:"actions",headerName:"Workflow actions",minWidth:270,flex:1.5,sortable:false,filterable:false,renderCell:({row})=><Box aria-busy={busy===row.id} sx={{display:"flex",flexWrap:"wrap",gap:1,py:1}}>{actionRef.current(row)}</Box>},
  ],[busy]);
  return <Box sx={{height:620,width:"100%",minWidth:0,display:"flex",flexDirection:"column"}}><GridDensityControl value={density} onChange={onDensityChange}/><DataGrid rows={rows} columns={columns} rowCount={total} sortingMode="server" sortModel={sortModel} onSortModelChange={onSortModelChange} columnVisibilityModel={columnVisibilityModel} onColumnVisibilityModelChange={onColumnVisibilityModelChange} density={density} onDensityChange={onDensityChange} showToolbar slotProps={{toolbar:{showQuickFilter:false,csvOptions:{disableToolbarButton:true},printOptions:{disableToolbarButton:true}}}}
    paginationMode="server" paginationModel={{page,pageSize}} pageSizeOptions={[10,25,50]} hideFooter disableColumnFilter disableRowSelectionOnClick
    getRowHeight={()=>"auto"} sx={{flex:1,minHeight:0,border:0,fontSize:12,"& .MuiDataGrid-cell":{display:"flex",alignItems:"center",py:1}}}/></Box>;
}
