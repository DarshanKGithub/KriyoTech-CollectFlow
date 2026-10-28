"use client";
import { useEffect, useRef, useState } from "react";
import { Accordion, AccordionSummary, AccordionDetails, Alert, Button, Checkbox, Chip, FormControlLabel, LinearProgress, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { apiFetch } from "@/lib/api";
import { apiError, type BankRow } from "@/lib/finance";
import { Money, CopyReference } from "@/components/financial-ui";

type Evidence={bank_ids:string[];banks:{id:string;amount:string;reference:string;date:string}[];targets:{target_id:string;target_type:string;amount:string;payment_reference:string}[];bank_total:string;target_total:string;components:Record<string,string>};
type Group={id:string;revision:number;status:string;currency:string;evidence:Evidence};
const split=(value:string)=>value.split(/[\s,]+/).filter(Boolean);
export function ReconciliationGroups({selected,canReview,onChanged}:{selected:BankRow;canReview:boolean;onChanged:()=>Promise<void>}) {
  const [bankIds,setBankIds]=useState(selected.id),[targetIds,setTargetIds]=useState(""),[kind,setKind]=useState("VENDOR_PAYMENT");
  const [zero,setZero]=useState(false),[ack,setAck]=useState(false),[reason,setReason]=useState("");
  const [preview,setPreview]=useState<{preview:Evidence;evidence_hash:string;currency:string}|null>(null),[group,setGroup]=useState<Group|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[attempt,setAttempt]=useState(0);
  const writing=useRef(false),key=useRef("");
  useEffect(()=>{setBankIds(selected.id);setTargetIds("");setKind(selected.amount.startsWith("-")?"VENDOR_PAYMENT":"CUSTOMER_COLLECTION");setPreview(null);setGroup(null);setError("");setReason("");setAck(false);setZero(false);key.current="";},[selected.id,selected.group_id,selected.amount]);
  useEffect(()=>{
    if(!selected.group_id)return;let active=true;setBusy(true);setError("");
    apiFetch("/bank-reconciliation?group_for="+selected.group_id).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Could not load allocation group."));if(active)setGroup(data);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[selected.group_id,attempt]);
  function changed(){setPreview(null);setAck(false);key.current="";}
  async function act(action:string) {
    if(writing.current)return;writing.current=true;setBusy(true);setError("");
    if(!key.current)key.current=crypto.randomUUID();
    const data=group?{action,group_id:group.id,expected_revision:group.revision,reason,request_key:key.current}:{action,bank_ids:split(bankIds),targets:split(targetIds).map(target_id=>({target_type:kind,target_id})),components:{fees:"0.00",fee_tax:"0.00",refunds:"0.00",adjustments:"0.00"},reason,request_key:key.current,...(action==="group_match"?{expected_evidence_hash:preview?.evidence_hash}:{})};
    try{
      const response=await apiFetch("/bank-reconciliation",{method:"PATCH",body:JSON.stringify(data)});const result=await response.json();
      if(!response.ok)throw new Error(apiError(result,"Could not complete group review. Refresh and verify the evidence."));
      if(action==="group_preview"){setPreview(result);setAck(false);key.current="";}
      else {key.current="";setPreview(null);setAck(false);setReason("");await onChanged();}
    }catch(e){setError((e as Error).message);}finally{writing.current=false;setBusy(false);}
  }
  if(!selected.group_id&&(!canReview||selected.status!=="UNMATCHED"||selected.source_verified===false))return null;
  const evidence=group?.evidence||preview?.preview,currency=group?.currency||preview?.currency||selected.currency||"";
  return <Accordion defaultExpanded={Boolean(selected.group_id)} disableGutters sx={{my:2,boxShadow:"none",border:"1px solid",borderColor:"divider"}}><AccordionSummary>{selected.group_id?"Allocation group":"Match split or combined payments"}</AccordionSummary><AccordionDetails><Stack spacing={2}>
    {busy&&<LinearProgress aria-label="Reviewing allocation group"/>}
    {error&&<Alert severity="error" action={selected.group_id?<Button onClick={()=>{key.current="";setAttempt(value=>value+1);}}>Refresh</Button>:undefined}>{error}</Alert>}
    {group&&<Stack spacing={1}><Chip label={group.status}/><CopyReference value={group.id} label="allocation group ID"/></Stack>}
    {!selected.group_id&&<>
      <Typography variant="body2">Combine one bank row with several full payments, or several bank rows with one full payment. Maximum ten records per side. Every record must share the same account, currency, transfer reference and direction, with dates within seven days.</Typography>
      <TextField label="Bank row UUIDs" multiline minRows={2} value={bankIds} disabled={busy} onChange={event=>{setBankIds(event.target.value);changed();}} helperText="Separate UUIDs with commas or new lines."/>
      <TextField select label="Internal record type" value={kind} disabled={busy} onChange={event=>{setKind(event.target.value);changed();}}>{["VENDOR_PAYMENT","CUSTOMER_COLLECTION","DRIVER_SALARY_PAYMENT"].map(value=><MenuItem key={value} value={value}>{value.replaceAll("_"," ")}</MenuItem>)}</TextField>
      <TextField label="Internal record UUIDs" multiline minRows={2} value={targetIds} disabled={busy} onChange={event=>{setTargetIds(event.target.value);changed();}} helperText="Each record is allocated in full. Both sides cannot contain multiple records."/>
      <FormControlLabel control={<Checkbox checked={zero} disabled={busy} onChange={event=>{setZero(event.target.checked);changed();}}/>} label="I verified fees, fee tax, refunds and adjustments are each zero for this internal cash transfer."/>
    </>}
    {evidence&&<><Typography variant="subtitle2">Exact group comparison</Typography><Typography variant="body2">Bank total <Money value={evidence.bank_total} currency={currency}/> · Internal total <Money value={evidence.target_total} currency={currency}/></Typography>{evidence.banks.map(row=><Stack key={row.id}><CopyReference value={row.id} label="bank member ID"/><Typography variant="caption">{row.date} · {row.reference} · <Money value={row.amount} currency={currency}/></Typography></Stack>)}{evidence.targets.map(item=><Stack key={item.target_type+item.target_id}><CopyReference value={item.target_id} label="internal member ID"/><Typography variant="caption">{item.target_type.replaceAll("_"," ")} · {item.payment_reference} · <Money value={item.amount} currency={currency}/></Typography></Stack>)}<Typography variant="caption">Fees 0.00 · fee tax 0.00 · refunds 0.00 · adjustments 0.00. This group does not transfer money or post gateway settlement.</Typography></>}
    {canReview&&<><TextField label="Group review / correction reason" value={reason} disabled={busy} multiline minRows={2} slotProps={{htmlInput:{maxLength:500}}} onChange={event=>{setReason(event.target.value);key.current="";}} required/>
      {(group||preview)&&<FormControlLabel control={<Checkbox checked={ack} disabled={busy} onChange={event=>setAck(event.target.checked)}/>} label="I reviewed every member and the exact total against source evidence."/>}
      {selected.group_id?group&&<Stack direction="row" spacing={1}>{group.status==="MATCHED"&&<Button variant="contained" disabled={busy||!ack||!reason.trim()} onClick={()=>void act("group_confirm")}>Confirm complete group</Button>}<Button color="warning" disabled={busy||!ack||!reason.trim()} onClick={()=>void act("group_clear")}>Clear complete group</Button></Stack>:<Stack direction="row" spacing={1}><Button disabled={busy||!zero||!reason.trim()||!targetIds.trim()} onClick={()=>void act("group_preview")}>Preview group</Button>{preview&&<Button variant="contained" disabled={busy||!zero||!ack||!reason.trim()} onClick={()=>void act("group_match")}>Record reviewed group</Button>}</Stack>}
    </>}
  </Stack></AccordionDetails></Accordion>;
}
