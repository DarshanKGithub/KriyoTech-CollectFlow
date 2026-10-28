"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, LinearProgress, MenuItem, Paper, Stack, Tab, Table, TableBody, TableCell,
  TableContainer, TableHead, TablePagination, TableRow, Tabs, TextField, Typography } from "@mui/material";
import { apiFetch } from "@/lib/api";
import { formatMoney } from "@/lib/finance";
import { ContentSkeleton } from "@/components/content-skeleton";
import { showNotice } from "@/components/product-dialogs";

type Account = { id:string;name:string;scope:string;kind:string;provider:string;external_reference:string;currency:string;active:boolean };
type Notice = { row:number;message:string };
type Batch = { id:string;account_id:string;filename:string;status:string;row_count:number;errors:Notice[];warnings:Notice[];review_note:string };
type DataRow = Record<string, unknown>;
type Result = { count:number;results:DataRow[] };
const currencies=["INR","USD","EUR","GBP","AED","SGD","AUD","CAD"];
const pretty=(key:string)=>key.replaceAll("_"," ").replace(/\b\w/g,letter=>letter.toUpperCase());
const amountFields=["gross","fees","fee_tax","refunds","adjustments","net","amount"];
function failure(data:unknown) {
  if(data&&typeof data==="object") {
    const body=data as Record<string,unknown>;
    if(typeof body.error==="string")return body.error;
    if(typeof body.detail==="string")return body.detail;
    return Object.entries(body).slice(0,4).map(([key,value])=>pretty(key)+": "+(Array.isArray(value)?value.join(" "):String(value))).join(" · ");
  }
  return "The request could not be completed.";
}
async function json(path:string,init?:RequestInit) {
  const response=await apiFetch(path,init);
  let data;
  try { data=await response.json(); } catch { throw new Error("The service returned an unreadable response. Retry shortly."); }
  if(!response.ok)throw new Error(failure(data));
  return data;
}

export function SettlementSources({ platform=false }:{platform?:boolean}) {
  const base=platform?"/admin/settlements":"/settlements";
  const [accounts,setAccounts]=useState<Account[]>([]),[accountId,setAccountId]=useState("");
  const [tab,setTab]=useState("imports"),[role,setRole]=useState(""),[ready,setReady]=useState(false);
  const [data,setData]=useState<Result>({count:0,results:[]}),[page,setPage]=useState(0);
  const [loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [accountOpen,setAccountOpen]=useState(false),[kind,setKind]=useState("GATEWAY");
  const [uploadOpen,setUploadOpen]=useState(false),[file,setFile]=useState<File|null>(null);
  const [batch,setBatch]=useState<Batch|null>(null),[batchRows,setBatchRows]=useState<Result>({count:0,results:[]}),[rowPage,setRowPage]=useState(0);
  const [decision,setDecision]=useState(""),[note,setNote]=useState(""),[ack,setAck]=useState(false);
  const [recordType,setRecordType]=useState("BANK_STATEMENT"),[recordId,setRecordId]=useState("");
  const sequence=useRef(0),writing=useRef(false);
  const [bootAttempt,setBootAttempt]=useState(0);
  const selected=accounts.find(item=>item.id===accountId);
  const canWrite=platform?["SUPER_ADMIN","BILLING_ADMIN"].includes(role):["OWNER","FINANCE"].includes(role);
  const reloadAccounts=useCallback(async()=>{const result=await json(base+"/accounts");setAccounts(result.accounts);},[base]);
  useEffect(()=>{
    let active=true;setError("");
    Promise.all([json(base+"/accounts"),json(platform?"/admin/auth/me":"/auth/me")]).then(([sources,profile])=>{
      if(!active)return;setAccounts(sources.accounts);setRole(profile.role);setReady(true);
    }).catch(e=>{if(active)setError(e.message);});
    if(!platform) {
      const query=new URLSearchParams(window.location.search);
      if(query.get("record_id")){setRecordId(query.get("record_id")||"");setRecordType(query.get("record_type")||"BANK_STATEMENT");setTab("provenance");}
    }
    return()=>{active=false;};
  },[base,platform,bootAttempt]);
  const refresh=useCallback(async()=>{
    if(!ready||!["imports","records"].includes(tab))return;
    const request=++sequence.current;setLoading(true);setError("");
    try{
      const result=await json(base+"/"+tab+"?page="+(page+1)+(accountId?"&account_id="+accountId:""));
      if(request===sequence.current)setData(result);
    }catch(e){if(request===sequence.current){setData({count:0,results:[]});setError((e as Error).message);}}
    finally{if(request===sequence.current)setLoading(false);}
  },[ready,tab,page,accountId,base]);
  useEffect(()=>{void refresh();},[refresh]);
  async function run(action:()=>Promise<void>) {
    if(writing.current)return;
    writing.current=true;
    setBusy(true);setError("");
    try{await action();}catch(e){setError(e instanceof Error?e.message:"Could not complete the request.");}
    finally{writing.current=false;setBusy(false);}
  }
  async function download(path:string,name:string) {
    await run(async()=>{
      const response=await apiFetch(path);
      if(!response.ok)throw new Error("Source download is unavailable or not permitted.");
      const url=URL.createObjectURL(await response.blob()),link=document.createElement("a");
      link.href=url;link.download=name;link.click();URL.revokeObjectURL(url);
    });
  }
  async function createAccount(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();const form=new FormData(event.currentTarget);
    await run(async()=>{
      const result=await json(base+"/accounts",{method:"POST",body:JSON.stringify(Object.fromEntries(form))});
      await reloadAccounts();setAccountId(result.id);setPage(0);setAccountOpen(false);showNotice("Source account created. Live provider sync is disabled.","success");
    });
  }
  async function openBatch(value:Batch,requestedPage=0) {
    await run(async()=>{
      const [info,rows]=await Promise.all([json(base+"/imports/"+value.id),json(base+"/imports/"+value.id+"?rows=1&page="+(requestedPage+1))]);
      setBatch(info);setBatchRows(rows);setRowPage(requestedPage);
    });
  }
  async function importFile(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if(!file||!selected)return;
    if(file.size>10*1024*1024){setError("Choose a CSV/XLSX report up to 10 MB.");return;}
    await run(async()=>{
      const form=new FormData();form.set("account_id",selected.id);form.set("file",file);
      const result=await json(base+"/imports",{method:"POST",body:form});
      setUploadOpen(false);setFile(null);
      const rows=await json(base+"/imports/"+result.id+"?rows=1");setBatch(result);setBatchRows(rows);setRowPage(0);
      showNotice(result.duplicate_import?"This file is already retained; no new batch was created.":"Report staged. Review it before approving source observations.",result.duplicate_import?"info":"success");
      await refresh();
    });
  }
  async function decide() {
    if(!batch)return;
    await run(async()=>{
      const result=await json(base+"/imports/"+batch.id,{method:"POST",body:JSON.stringify({decision,note,acknowledge_warnings:ack})});
      setBatch(result);setDecision("");setNote("");setAck(false);await refresh();
      showNotice(decision==="APPROVED"?"Source observations approved. No bank match or payment was posted.":"Import rejected; original evidence retained.","success");
    });
  }
  async function verifyProvenance(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();const form=new FormData(event.currentTarget),element=event.currentTarget;
    await run(async()=>{
      await json(base+"/provenance",{method:"POST",body:JSON.stringify({record_type:recordType,record_id:recordId,account_id:accountId,evidence:form.get("evidence")})});
      showNotice("Source account and currency verified with an audit entry.","success");element.reset();
    });
  }
  const columns=tab==="records"?["record_type","external_id","currency","gross","fees","fee_tax","refunds","adjustments","net","amount","expected_date","settled_date"]:["filename","status","row_count"];
  function cell(row:DataRow,key:string) {
    const value=row[key];if(value===null||value===undefined||value==="")return "—";
    return amountFields.includes(key)?formatMoney(String(value),String(row.currency||selected?.currency||"")):String(value);
  }
  return <Box sx={{p:platform?0:{xs:2,md:3},minWidth:0}}>
    <Stack direction={{xs:"column",sm:"row"}} spacing={2} sx={{justifyContent:"space-between",mb:2}}>
      <Box><Typography component="h1" variant="h4">{platform?"Platform settlement sources":"Settlement sources"}</Typography><Typography variant="body2" color="text.secondary" sx={{mt:1}}>{platform?"KriyoPay subscription revenue accounts. Client merchant accounts are managed in their own workspaces.":"Your company's bank and merchant accounts. Platform billing accounts are kept separate."}</Typography></Box>
      <Stack direction="row" spacing={1} sx={{alignSelf:"flex-start"}}><Button onClick={()=>void download(base+"/template","settlement-template.csv")} disabled={busy}>CSV template</Button>{canWrite&&<Button variant="contained" onClick={()=>setAccountOpen(true)}>Add account</Button>}</Stack>
    </Stack>
    <Alert severity="info" sx={{mb:2}}>Import and review only. Approved observations are not confirmed bank credits. Live provider sync, credentials and automatic posting are disabled.</Alert>
    {error&&<Alert severity="error" sx={{mb:2}} onClose={ready?()=>setError(""):undefined}>{error}</Alert>}
    {!ready&&!error?<ContentSkeleton variant="table" label="Loading financial sources"/>:<>
      <Stack direction={{xs:"column",sm:"row"}} spacing={2} sx={{mb:2,alignItems:{sm:"center"}}}>
        <TextField select label="Source account" value={accountId} sx={{minWidth:260}} onChange={event=>{setAccountId(event.target.value);setPage(0);}}><MenuItem value="">All source accounts</MenuItem>{accounts.map(item=><MenuItem key={item.id} value={item.id}>{item.name+" · "+item.currency+" · "+item.kind+(item.active?"":" · disabled")}</MenuItem>)}</TextField>
        {canWrite&&<Button variant="outlined" disabled={!selected?.active||selected.kind!=="GATEWAY"||busy} onClick={()=>setUploadOpen(true)}>Import settlement report</Button>}
        <Button disabled={busy||loading} onClick={()=>{if(!ready)setBootAttempt(value=>value+1);else if(tab==="accounts"||tab==="provenance")void run(reloadAccounts);else void refresh();}}>Refresh list</Button>
      </Stack>
      <Tabs value={tab} onChange={(_,value)=>{sequence.current++;setLoading(false);setTab(value);setPage(0);setData({count:0,results:[]});}} variant="scrollable" sx={{mb:2}}><Tab value="imports" label="Import review"/><Tab value="records" label="Approved observations"/><Tab value="accounts" label="Accounts"/>{!platform&&<Tab value="provenance" label="Verify legacy sources"/>}</Tabs>
      {(loading||busy)&&<LinearProgress aria-label="Working with settlement sources" sx={{mb:1}}/>}
      {["imports","records"].includes(tab)&&<Paper variant="outlined"><TableContainer><Table size="small" aria-label={tab==="records"?"Approved settlement observations":"Settlement import batches"}><TableHead><TableRow>{columns.map(key=><TableCell key={key}>{pretty(key)}</TableCell>)}{tab==="imports"&&<TableCell>Review</TableCell>}</TableRow></TableHead><TableBody>{data.results.map(row=><TableRow key={String(row.id)}>{columns.map(key=><TableCell key={key} sx={{whiteSpace:"nowrap"}}>{key==="status"?<Chip size="small" label={String(row[key])}/>:cell(row,key)}</TableCell>)}{tab==="imports"&&<TableCell><Button disabled={busy} onClick={()=>void openBatch(row as unknown as Batch)}>Open import</Button></TableCell>}</TableRow>)}{!loading&&!data.results.length&&<TableRow><TableCell colSpan={columns.length+1}>{tab==="records"?"No approved source observations in this scope.":"No import batches yet. Select a gateway account to stage a report."}</TableCell></TableRow>}</TableBody></Table></TableContainer><TablePagination component="div" count={data.count} page={page} rowsPerPage={25} rowsPerPageOptions={[25]} onPageChange={(_,next)=>setPage(next)}/></Paper>}
      {tab==="accounts"&&<Paper variant="outlined"><TableContainer><Table size="small" aria-label="Source accounts"><TableHead><TableRow>{["Name","Kind","Provider","Reference","Currency","State",""].map((label,i)=><TableCell key={i}>{label}</TableCell>)}</TableRow></TableHead><TableBody>{accounts.map(item=><TableRow key={item.id}><TableCell>{item.name}</TableCell><TableCell>{item.kind}</TableCell><TableCell>{item.provider}</TableCell><TableCell>{item.external_reference}</TableCell><TableCell>{item.currency}</TableCell><TableCell>{item.active?"Active":"Disabled"}</TableCell><TableCell>{canWrite&&<Button disabled={busy} onClick={()=>void run(async()=>{await json(base+"/accounts/"+item.id,{method:"PATCH",body:JSON.stringify({active:!item.active})});await reloadAccounts();})}>{item.active?"Disable":"Enable"}</Button>}</TableCell></TableRow>)}</TableBody></Table></TableContainer><Typography variant="caption" sx={{display:"block",p:2}} color="text.secondary">Showing up to 200 accounts. Ownership, identity and currency cannot be overwritten after creation.</Typography></Paper>}
      {tab==="provenance"&&!platform&&<Paper variant="outlined" sx={{p:3,maxWidth:760}}><Typography component="h2" variant="h6">Verify a historical source</Typography><Typography variant="body2" color="text.secondary" sx={{my:2}}>Choose the bank account, enter the existing record UUID and describe the evidence. Previously unknown account/currency stays unknown until verified. Linked bank rows must be explicitly unmatched first. Existing operational payments support INR only.</Typography><Box component="form" onSubmit={verifyProvenance}><Stack spacing={2}><TextField select label="Record type" value={recordType} onChange={event=>setRecordType(event.target.value)}>{["BANK_STATEMENT","VENDOR_PAYMENT","CUSTOMER_COLLECTION","DRIVER_SALARY_PAYMENT"].map(value=><MenuItem key={value} value={value}>{pretty(value)}</MenuItem>)}</TextField><TextField label="Record UUID" required value={recordId} onChange={event=>setRecordId(event.target.value)}/><TextField label="Source evidence" name="evidence" required multiline minRows={2} slotProps={{htmlInput:{maxLength:500}}}/><Button type="submit" variant="contained" disabled={busy||!canWrite||!selected?.active||selected.kind!=="BANK"}>Verify account and currency</Button></Stack></Box></Paper>}
    </>}
    <Dialog open={accountOpen} onClose={()=>{if(!busy)setAccountOpen(false);}} fullWidth maxWidth="sm"><Box component="form" onSubmit={createAccount}><DialogTitle>Add {platform?"platform":"workspace"} source account</DialogTitle><DialogContent>{error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}<Stack spacing={2} sx={{pt:1}}><TextField label="Account name" name="name" required slotProps={{htmlInput:{maxLength:100}}}/><TextField select label="Account kind" name="kind" value={kind} onChange={event=>setKind(event.target.value)}><MenuItem value="GATEWAY">Merchant gateway</MenuItem><MenuItem value="BANK">Bank account</MenuItem></TextField><TextField key={kind} select label="Provider" name="provider" defaultValue={kind==="BANK"?"BANK":"RAZORPAY"}>{(kind==="BANK"?["BANK"]:["RAZORPAY","OTHER"]).map(value=><MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField><TextField label="Merchant ID or masked bank reference" name="external_reference" required slotProps={{htmlInput:{maxLength:100}}}/><TextField select label="Source currency" name="currency" defaultValue="INR">{currencies.map(value=><MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField><Typography variant="caption" color="text.secondary">No API keys or passwords are collected. This account is for reviewed imports.</Typography></Stack></DialogContent><DialogActions><Button disabled={busy} onClick={()=>setAccountOpen(false)}>Cancel</Button><Button type="submit" variant="contained" disabled={busy}>Create account</Button></DialogActions></Box></Dialog>
    <Dialog open={uploadOpen} onClose={()=>{if(!busy)setUploadOpen(false);}} fullWidth maxWidth="sm"><Box component="form" onSubmit={importFile}><DialogTitle>Stage settlement report</DialogTitle><DialogContent>{error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}<Typography variant="body2" sx={{mb:2}}>{selected?.name+" · "+selected?.currency} — exact template headers, CSV or values-only XLSX, up to 10 MB and 10,000 rows. Blank components remain unknown; enter zero only when the source says zero.</Typography><TextField type="file" fullWidth required slotProps={{htmlInput:{accept:".csv,.xlsx","aria-label":"Settlement report file"}}} onChange={event=>setFile((event.target as HTMLInputElement).files?.[0]||null)}/></DialogContent><DialogActions><Button disabled={busy} onClick={()=>setUploadOpen(false)}>Cancel</Button><Button type="submit" disabled={busy||!file} variant="contained">Upload for review</Button></DialogActions></Box></Dialog>
    <Dialog open={Boolean(batch)} onClose={()=>{if(!busy)setBatch(null);}} fullWidth maxWidth="lg"><DialogTitle>Import review · {batch?.filename}</DialogTitle><DialogContent>{error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}{batch&&<><Stack direction="row" spacing={2} sx={{alignItems:"center",mb:2}}><Chip label={batch.status}/><Typography variant="body2">{batch.row_count} source rows</Typography><Button disabled={busy} onClick={()=>void download(base+"/imports/"+batch.id+"/source",batch.filename)}>Download original</Button></Stack>{batch.errors.map((item,index)=><Alert key={index} severity="error" sx={{mb:1}}>Row {item.row}: {item.message}</Alert>)}{batch.warnings.map((item,index)=><Alert key={index} severity="warning" sx={{mb:1}}>Row {item.row}: {item.message}</Alert>)}<TableContainer><Table size="small" aria-label="Staged source rows"><TableHead><TableRow>{["Row","Type","Provider ID","Currency","Gross","Fees","Tax","Refunds","Adjustments","Net","Amount"].map(label=><TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>{batchRows.results.map(item=>{const row=item.data as DataRow;return <TableRow key={String(item.row_number)}><TableCell>{String(item.row_number)}</TableCell>{["record_type","external_id","currency","gross","fees","fee_tax","refunds","adjustments","net","amount"].map(key=><TableCell key={key} sx={{whiteSpace:"nowrap"}}>{cell(row,key)}</TableCell>)}</TableRow>;})}</TableBody></Table></TableContainer><TablePagination component="div" count={batchRows.count} page={rowPage} rowsPerPage={25} rowsPerPageOptions={[25]} onPageChange={(_,next)=>void openBatch(batch,next)}/><Typography variant="caption" color="text.secondary">Approval records source observations only. It does not confirm a bank credit, activate a plan or initiate a refund. Original files and review history are retained.</Typography></>}</DialogContent><DialogActions><Button disabled={busy} onClick={()=>setBatch(null)}>Close</Button>{canWrite&&batch&&["NEEDS_REVIEW","INVALID"].includes(batch.status)&&<><Button disabled={busy} color="error" onClick={()=>{setDecision("REJECTED");setNote("");setAck(false);}}>Reject import</Button><Button disabled={busy||batch.status==="INVALID"} variant="contained" onClick={()=>{setDecision("APPROVED");setNote("");setAck(false);}}>Approve observations</Button></>}</DialogActions></Dialog>
    <Dialog open={Boolean(decision)} onClose={()=>{if(!busy)setDecision("");}} fullWidth maxWidth="sm"><DialogTitle>{decision==="APPROVED"?"Approve source observations":"Reject import"}</DialogTitle><DialogContent>{error&&<Alert severity="error" sx={{mb:2}}>{error}</Alert>}<Typography variant="body2" sx={{mb:2}}>Confirm the source account, currency and report evidence before recording this decision.</Typography><TextField label="Review note" value={note} fullWidth required multiline minRows={2} slotProps={{htmlInput:{maxLength:500}}} onChange={event=>setNote(event.target.value)}/>{Boolean(batch?.warnings.length)&&<FormControlLabel control={<Checkbox checked={ack} onChange={event=>setAck(event.target.checked)}/>} label="I reviewed the missing evidence warnings; unknown components remain unknown."/>}</DialogContent><DialogActions><Button disabled={busy} onClick={()=>setDecision("")}>Cancel</Button><Button variant="contained" disabled={busy||!note.trim()||decision==="APPROVED"&&Boolean(batch?.warnings.length)&&!ack} onClick={()=>void decide()}>Confirm decision</Button></DialogActions></Dialog>
  </Box>;
}
