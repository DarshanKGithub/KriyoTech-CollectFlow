"use client";

import { useEffect, useRef, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Snackbar from "@mui/material/Snackbar";
import Alert from "@mui/material/Alert";

type Request = { kind: "confirm" | "input"; message: string; initial: string; resolve: (value: string | boolean | null) => void };
const pending: Request[] = [];
let wake: (() => void) | undefined;
type Notice = { message: string; severity: "success" | "error" | "info" | "warning" };
let notify: ((notice: Notice) => void) | undefined;

export function requestConfirmation(message: string): Promise<boolean> {
  return new Promise(resolve => { pending.push({kind:"confirm",message,initial:"",resolve:value=>resolve(value===true)});wake?.(); });
}
export function requestInput(message: string, initial = ""): Promise<string | null> {
  return new Promise(resolve => { pending.push({kind:"input",message,initial,resolve:value=>resolve(typeof value === "string" ? value : null)});wake?.(); });
}
export function showNotice(message: string, severity: Notice["severity"] = "error") { notify?.({ message, severity }); }

export function ProductDialogs({children}: {children: React.ReactNode}) {
  const [request,setRequest] = useState<Request | null>(null);
  const [value,setValue] = useState("");
  const [notice,setNotice] = useState<Notice | null>(null);
  const activeRequest = useRef<Request | null>(null);
  useEffect(() => {
    wake = () => {
      if(activeRequest.current)return;
      const next=pending.shift() || null;
      activeRequest.current=next;
      setRequest(next);
    };
    notify = setNotice;
    wake();
    return () => { wake=undefined;notify=undefined; };
  }, []);
  useEffect(() => { setValue(request?.initial || ""); },[request]);
  function finish(result: string | boolean | null) {
    if(!request || activeRequest.current!==request)return;
    activeRequest.current=null;
    request.resolve(result);
    const next=pending.shift() || null;
    activeRequest.current=next;
    setValue(next?.initial || "");setRequest(next);
  }
  return <>{children}<Dialog open={Boolean(request)} onClose={()=>finish(request?.kind==="confirm"?false:null)} fullWidth maxWidth="sm" aria-labelledby="product-dialog-title" aria-describedby="product-dialog-description">
    <form onSubmit={event=>{event.preventDefault();finish(request?.kind==="confirm"?true:value);}}>
      <DialogTitle id="product-dialog-title">{request?.kind==="input"?"Enter details":"Confirm action"}</DialogTitle>
      <DialogContent><DialogContentText id="product-dialog-description">{request?.message}</DialogContentText>{request?.kind==="input"&&<TextField autoFocus fullWidth size="small" value={value} onChange={event=>setValue(event.target.value)} sx={{mt:2}} slotProps={{htmlInput:{"aria-label":request.message}}}/>}</DialogContent>
      <DialogActions><Button type="button" onClick={()=>finish(request?.kind==="confirm"?false:null)}>Cancel</Button><Button type="submit" variant="contained">{request?.kind==="input"?"Continue":"Confirm"}</Button></DialogActions>
    </form>
  </Dialog><Snackbar open={Boolean(notice)} autoHideDuration={8000} onClose={(_, reason)=>{if(reason!=="clickaway")setNotice(null);}} anchorOrigin={{vertical:"bottom",horizontal:"right"}}><Alert severity={notice?.severity || "info"} variant="filled" onClose={()=>setNotice(null)}>{notice?.message}</Alert></Snackbar></>;
}
