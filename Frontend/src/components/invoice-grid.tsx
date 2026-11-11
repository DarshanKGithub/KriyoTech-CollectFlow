"use client";
import { GridDensityControl } from "@/components/grid-density-control";

import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useGridPreferences } from "@/components/grid-preferences";
import { ProcessingStatus } from "@/components/processing-status";

type InvoiceRow = {id:string;invoice_number:string;vendor_name?:string;supplier_name?:string;invoice_date?:string;invoice_total:string;status:string;extraction_error?:string;automation?:{status?:string;message?:string}};
export const invoiceStatusLabels: Record<string, string> = {
  UPLOADED: "Uploaded", EXTRACTING: "Reading invoice", EXTRACTION_FAILED: "Could not read invoice",
  REVIEW_REQUIRED: "Needs review", MATCHED: "Matched", EXCEPTION: "Issue found",
  APPROVAL_PENDING: "Awaiting approval", APPROVED: "Approved", REJECTED: "Rejected",
  PAYMENT_READY: "Ready for payment", EXPORTED: "Exported",
};
const label = (value: string) => invoiceStatusLabels[value] || value.replaceAll("_", " ").toLowerCase();
const money = (value: string | number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value || 0));
function InvoiceState({ row }: { row: InvoiceRow }) {
  return <Box sx={{ py: 1, minWidth: 0, overflowWrap: "anywhere" }}>
    <ProcessingStatus status={row.status} label={label(row.status)}/>
    {row.automation?.status && <Typography variant="caption" color={["NEEDS_ATTENTION", "FAILED"].includes(row.automation.status) ? "warning.main" : "text.secondary"}
      sx={{ display: "block", whiteSpace: "normal", mt: .5 }}>{label(row.automation.status)}{row.automation.message ? ` · ${row.automation.message}` : ""}</Typography>}
    {row.extraction_error && <Typography variant="caption" color="error" sx={{ display: "block", whiteSpace: "normal", mt: .5 }}>{row.extraction_error}</Typography>}
  </Box>;
}
export function InvoiceGrid<T extends InvoiceRow>({rows,total,page,pageSize,actions,busy,onOrderingChange}: {
  rows:T[];total:number;page:number;pageSize:number;actions:(invoice:T)=>ReactNode;busy:string;onOrderingChange?:(value:string)=>void;
}) {
  const preferences=useGridPreferences("invoices");
  const mobile = useMediaQuery("(max-width:767px)");
  const {ready,columnVisibilityModel,onColumnVisibilityModelChange,density,onDensityChange,sortModel,onSortModelChange}=preferences;
  useEffect(()=>{if(!ready)return;const item=sortModel[0];onOrderingChange?.(item&&["invoice_date","invoice_total"].includes(item.field)?`${item.sort==="desc"?"-":""}${item.field}`:"-created_at");},[ready,sortModel,onOrderingChange]);
  const actionRef=useRef(actions);actionRef.current=actions;
  const columns=useMemo<GridColDef<T>[]>(()=>[
    {field:"supplier",headerName:"Supplier",minWidth:180,flex:1.2,sortable:false,valueGetter:(_,row)=>row.vendor_name||row.supplier_name||"Supplier to review"},
    {field:"invoice_number",headerName:"Invoice number",minWidth:135,flex:.9,sortable:false,valueFormatter:value=>value||"Not recorded"},
    {field:"status",headerName:"Status",minWidth:185,flex:1.2,sortable:false,renderCell:({row})=><InvoiceState row={row}/>},
    {field:"invoice_total",headerName:"Amount",type:"number",minWidth:125,sortable:true,valueGetter:value=>Number(value),valueFormatter:money},
    {field:"invoice_date",headerName:"Date",minWidth:105,sortable:true},
    {field:"actions",headerName:"Next actions",minWidth:185,flex:1.2,sortable:false,filterable:false,renderCell:({row})=><Box aria-busy={busy===row.id} sx={{display:"flex",flexWrap:"wrap",gap:.5,py:1}}>{actionRef.current(row)}</Box>},
  ],[busy]);
  if (mobile) return <Box sx={{ "& > article + article": { borderTop: 1, borderColor: "divider" } }}>
    {rows.map(row => <Box component="article" key={row.id} sx={{ p: 2, overflowWrap: "anywhere" }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 1 }}>
        <Box>
          <Typography component="h3" variant="subtitle2">{row.vendor_name || row.supplier_name || "Supplier to review"}</Typography>
          <Typography variant="caption" color="text.secondary">{row.invoice_number || "Invoice number not recorded"}{row.invoice_date && ` · ${row.invoice_date}`}</Typography>
        </Box>
        <Typography variant="subtitle2" sx={{ fontVariantNumeric: "tabular-nums" }}>{money(row.invoice_total)}</Typography>
      </Box>
      <InvoiceState row={row}/>
      <Box aria-busy={busy === row.id} sx={{ display: "flex", flexWrap: "wrap", gap: .5 }}>{actions(row)}</Box>
    </Box>)}
  </Box>;
  return <Box sx={{height:620,width:"100%",minWidth:0,display:"flex",flexDirection:"column"}}><GridDensityControl value={density} onChange={onDensityChange}/><DataGrid rows={rows} columns={columns} rowCount={total} sortingMode="server" sortModel={sortModel} onSortModelChange={onSortModelChange} columnVisibilityModel={columnVisibilityModel} onColumnVisibilityModelChange={onColumnVisibilityModelChange} density={density} onDensityChange={onDensityChange} showToolbar slotProps={{toolbar:{showQuickFilter:false,csvOptions:{disableToolbarButton:true},printOptions:{disableToolbarButton:true}}}}
    paginationMode="server" paginationModel={{page,pageSize}} pageSizeOptions={[10,25,50]} hideFooter disableColumnFilter disableRowSelectionOnClick
    getRowHeight={()=>"auto"} sx={{flex:1,minHeight:0,border:0,fontSize:12,"& .MuiDataGrid-cell":{display:"flex",alignItems:"center",py:1}}}/></Box>;
}
