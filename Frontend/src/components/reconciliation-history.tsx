"use client";
import { useEffect, useState } from "react";
import { Accordion, AccordionSummary, AccordionDetails, Alert, Button, LinearProgress, Stack, Typography } from "@mui/material";
import { apiFetch } from "@/lib/api";
import { CopyReference, Money } from "@/components/financial-ui";
import { apiError, financialDate } from "@/lib/finance";

function Evidence({value}:{value:Record<string,unknown>}) {
  const target=(value.target||value.candidate||value) as Record<string,unknown>;
  const before=value.before as Record<string,unknown>|undefined,after=value.after as Record<string,unknown>|undefined;
  const group=value.group as {evidence?:{bank_total:string;target_total:string};currency?:string}|undefined;
  return <Stack spacing={1}>
    {before&&after&&<Typography variant="body2">Status: {String(before.status)} → {String(after.status)}</Typography>}
    {Boolean(target.target_id)&&<CopyReference value={String(target.target_id)} label="reviewed internal record ID"/>}
    {Boolean(target.payment_reference)&&<Typography variant="body2">Transfer reference: {String(target.payment_reference)}</Typography>}
    {typeof target.amount==="string"&&<Typography variant="body2">Internal amount: <Money value={target.amount} currency={String(target.currency||"")}/></Typography>}
    {Array.isArray(target.reason_codes)&&<Typography variant="caption">{target.reason_codes.map(code=>String(code).replaceAll("_"," ").toLowerCase()).join(" · ")}</Typography>}
    {group?.evidence&&<Typography variant="body2">Bank total <Money value={group.evidence.bank_total} currency={group.currency||""}/> · Internal total <Money value={group.evidence.target_total} currency={group.currency||""}/></Typography>}
  </Stack>;
}

type Event={id:string;action:string;reason:string;actor:string;at:string;evidence:Record<string,unknown>};
export function ReconciliationHistory({bankId,version}:{bankId:string;version:number}) {
  const [open,setOpen]=useState(false),[page,setPage]=useState(1),[events,setEvents]=useState<Event[]>([]),[count,setCount]=useState(0);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[attempt,setAttempt]=useState(0);
  useEffect(()=>{setPage(1);setEvents([]);},[bankId,version]);
  useEffect(()=>{
    if(!open)return;let active=true;setBusy(true);setError("");
    apiFetch("/bank-reconciliation?history_for="+bankId+"&history_page="+page).then(async response=>{
      const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Could not read review history."));
      if(!Array.isArray(data.events))throw new Error("Review history is unavailable.");
      if(active){setEvents(data.events);setCount(data.count);}
    }).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[bankId,version,open,page,attempt]);
  return <Accordion disableGutters expanded={open} onChange={(_,value)=>setOpen(value)} sx={{my:2,boxShadow:"none",border:"1px solid",borderColor:"divider"}}>
    <AccordionSummary>Review history and matching evidence</AccordionSummary><AccordionDetails>
      {busy&&<LinearProgress aria-label="Reading review history"/>}
      {error?<Alert severity="error" action={<Button onClick={()=>setAttempt(value=>value+1)}>Retry</Button>}>{error}</Alert>:<>
        {!busy&&!events.length&&<Typography variant="body2">No saved review decisions yet. Earlier activity may be available in the workspace audit log.</Typography>}
        {events.map(item=><Stack key={item.id} spacing={0.5} sx={{py:1.5,borderBottom:"1px solid",borderColor:"divider"}}><Typography variant="subtitle2">{item.action.replaceAll("_"," ")}</Typography><Typography variant="caption">{item.actor} · {financialDate(item.at,true)}</Typography><Typography variant="body2">{item.reason}</Typography><Accordion disableGutters sx={{boxShadow:"none"}}><AccordionSummary>Recorded evidence</AccordionSummary><AccordionDetails><Evidence value={item.evidence}/></AccordionDetails></Accordion></Stack>)}
        <Stack direction="row" sx={{justifyContent:"space-between",mt:1}}><Button disabled={busy||page===1} onClick={()=>setPage(value=>value-1)}>Previous</Button><Typography variant="caption">{count} decisions · page {page}</Typography><Button disabled={busy||page*25>=count} onClick={()=>setPage(value=>value+1)}>Next</Button></Stack>
      </>}
    </AccordionDetails>
  </Accordion>;
}
