"use client";
import { GridDensityControl } from "@/components/grid-density-control";

import { useMemo, useRef } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { useGridPreferences } from "@/components/grid-preferences";
import { GridNoRows, GridNoResults } from "@/components/grid-overlays";
import { QuickDetails } from "@/components/quick-details";

type Row = {id:string;record:Record<string,unknown>};
export function RecordDataGrid({rows,columns,onOpenRecord,format = value => value == null ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value)}: {
  rows:Record<string,unknown>[];columns:string[];format?:(value:unknown)=>string;onOpenRecord?:(id:string)=>void;
}) {
  const formatter=useRef(format);formatter.current=format;
  const openRecord=useRef(onOpenRecord);openRecord.current=onOpenRecord;
  const hasOpenRecord=Boolean(onOpenRecord);
  const signature=columns.join("\u0000");
  const {ready:_ready,...preferences}=useGridPreferences(signature);
  const gridColumns=useMemo<GridColDef<Row>[]>(()=>[...signature.split("\u0000").filter(Boolean).map(field=>({field,headerName:field.replaceAll("_"," "),minWidth:150,flex:1,
    valueGetter:(_: unknown,row: Row)=>typeof row.record[field]==="number"?row.record[field]:formatter.current(row.record[field]),
    valueFormatter:(value: unknown)=>typeof value==="number"?formatter.current(value):String(value??"—"),
  })), {field:"recordDetails",headerName:"Details",width:hasOpenRecord?230:110,sortable:false,filterable:false,disableExport:true,renderCell:({row})=><><QuickDetails title="Record details" fields={Object.fromEntries(signature.split("\u0000").filter(Boolean).map(field=>[field,formatter.current(row.record[field])]))}/>{openRecord.current&&<Button size="small" onClick={()=>openRecord.current?.(row.id)}>Open workflow</Button>}</>}],[signature,hasOpenRecord]);
  const data=useMemo(()=>rows.map((record,index)=>({id:String(record.id??index),record})),[rows]);
  return <Box sx={{height:540,width:"100%",minWidth:0,display:"flex",flexDirection:"column"}}><GridDensityControl value={preferences.density} onChange={preferences.onDensityChange}/><DataGrid {...preferences} rows={data} columns={gridColumns} showToolbar disableRowSelectionOnClick slots={{noRowsOverlay:GridNoRows,noResultsOverlay:GridNoResults}}
    slotProps={{toolbar:{csvOptions:{disableToolbarButton:true},printOptions:{disableToolbarButton:true}}}}
    pageSizeOptions={[10,25,50]} initialState={{pagination:{paginationModel:{page:0,pageSize:10}}}} localeText={{noRowsLabel:"No records yet"}}
    sx={{flex:1,minHeight:0,border:0,fontSize:12}}/></Box>;
}
