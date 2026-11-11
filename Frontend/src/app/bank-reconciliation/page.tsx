"use client";

import NextLink from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import TablePagination from "@mui/material/TablePagination";
import { ReconciliationGroups } from "@/components/reconciliation-groups";
import { ReconciliationHistory } from "@/components/reconciliation-history";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Radio from "@mui/material/Radio";
import LinearProgress from "@mui/material/LinearProgress";
import useMediaQuery from "@mui/material/useMediaQuery";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { Upload, RefreshCw, X, ChevronDown, ArrowDownLeft, ArrowUpRight, FileSpreadsheet, Link2, CheckCircle2, CircleAlert, FlaskConical } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { apiError, financialErrorMessage, absoluteAmount, compareCandidate, financialDate, moneyDirection, type BankRow, type MatchCandidate } from "@/lib/finance";
import { FinancialHeader, Money, FinancialStatus, DetailGroup, CopyReference } from "@/components/financial-ui";
import { ContentSkeleton } from "@/components/content-skeleton";
import { EmptyState } from "@/components/empty-state";
import { UiForm } from "@/components/product-ui";
import { useGridPreferences } from "@/components/grid-preferences";
import { GridDensityControl } from "@/components/grid-density-control";
import { showNotice } from "@/components/product-dialogs";

type Action = { action:"match"|"reconcile"|"unmatch"; candidate?:MatchCandidate; manual?:{target_type:MatchCandidate["target_type"];target_id:string} };
const targetLabels={VENDOR_PAYMENT:"Vendor payment",CUSTOMER_COLLECTION:"Customer collection",DRIVER_SALARY_PAYMENT:"Driver salary payment"};
const statusLabels = {
  REVIEW: "Needs review", MATCHED: "Matched", RECONCILED: "Reconciled",
  ALL: "All transactions", UNMATCHED: "Unmatched only", DUPLICATE: "Duplicates only",
} as const;
type StatusFilter = keyof typeof statusLabels;
const queues = [
  { value: "REVIEW", label: "Needs review", detail: "Unmatched transactions and duplicates", icon: CircleAlert, tone: "warning.main" },
  { value: "MATCHED", label: "Matched", detail: "Linked, awaiting confirmation", icon: Link2, tone: "info.main" },
  { value: "RECONCILED", label: "Reconciled", detail: "Matches confirmed", icon: CheckCircle2, tone: "success.main" },
  { value: "ALL", label: "All transactions", detail: "Every imported bank transaction", icon: FileSpreadsheet, tone: "text.secondary" },
] as const;
function reviewAction(row: BankRow, canReview: boolean) {
  if (row.status === "DUPLICATE") return "Review duplicate";
  if (!canReview || row.source_verified === false) return "View details";
  if (row.status === "UNMATCHED") return "Find a match";
  if (row.status === "MATCHED") return "Review match";
  return "View details";
}
const validId=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function BankReconciliationPage() {
  const [rows,setRows]=useState<BankRow[]>([]),[counts,setCounts]=useState<Record<string,number>|null>(null);
  const [loading,setLoading]=useState(true),[refreshing,setRefreshing]=useState(false),[error,setError]=useState("");
  const [canReview,setCanReview]=useState(false),[loadedAt,setLoadedAt]=useState("");
  const [status,setStatus]=useState<StatusFilter>("REVIEW"),[search,setSearch]=useState(""),[direction,setDirection]=useState("ALL");
  const [paginationModel,setPaginationModel]=useState({page:0,pageSize:25}),[rowCount,setRowCount]=useState(0);
  const [querySearch,setQuerySearch]=useState("");
  const [reason,setReason]=useState(""),[requestKey,setRequestKey]=useState("");
  const [historyVersion,setHistoryVersion]=useState(0);
  const [feedback,setFeedback]=useState<MatchCandidate|null>(null),[feedbackReason,setFeedbackReason]=useState(""),[feedbackKey,setFeedbackKey]=useState("");
  const [from,setFrom]=useState(""),[to,setTo]=useState("");
  const [selectedId,setSelectedId]=useState("");const selected=rows.find(row=>row.id===selectedId)||null;
  const [suggestions,setSuggestions]=useState<Record<string,MatchCandidate[]>>({}),[suggesting,setSuggesting]=useState("");
  const [candidateMeta,setCandidateMeta]=useState<Record<string,{ambiguous:boolean;limited:boolean;at?:string}>>({});
  const [candidate,setCandidate]=useState<MatchCandidate|null>(null),[candidateError,setCandidateError]=useState("");
  const [manualId,setManualId]=useState(""),[manualType,setManualType]=useState<MatchCandidate["target_type"]>("VENDOR_PAYMENT");
  const [review,setReview]=useState<Action|null>(null),[acknowledged,setAcknowledged]=useState(false),[mutationError,setMutationError]=useState("");
  const [busy,setBusy]=useState(false);const writing=useRef(false);const loadSequence=useRef({value:0});
  const [sourceAccounts,setSourceAccounts]=useState<{id:string;name:string;currency:string}[]>([]),[sourceAccountId,setSourceAccountId]=useState("");
  const [importOpen,setImportOpen]=useState(false),[file,setFile]=useState<File|null>(null),[importError,setImportError]=useState("");
  async function downloadSource(row:BankRow) {
    if(writing.current||!row.statement_id)return;
    writing.current=true;setBusy(true);setCandidateError("");
    try {
      const response=await apiFetch("/bank-reconciliation?source_for="+row.statement_id);
      if(!response.ok)throw new Error(apiError(await response.json(),"Original statement unavailable."));
      const url=URL.createObjectURL(await response.blob()),link=document.createElement("a");
      link.href=url;link.download=row.statement;link.click();URL.revokeObjectURL(url);
    } catch(e) {setCandidateError(financialErrorMessage(e,"Could not download statement."));}
    finally {writing.current=false;setBusy(false);}
  }
  const [columns,setColumns]=useState({date:"date",description:"description",amount:"amount",reference:"reference"});
  const [online,setOnline]=useState(true);const mobile=useMediaQuery("(max-width:767px)");
  const {ready:_ready,...preferences}=useGridPreferences("bank-reconciliation",[{field:"date",sort:"desc"}]);
  const sort=preferences.sortModel[0];
  const sortKey=(sort?.sort==="asc"?"":"-")+(["date","description","reference","amount","status"].includes(sort?.field||"")?sort.field:"date");
  useEffect(()=>{const timer=setTimeout(()=>setQuerySearch(search),300);return()=>clearTimeout(timer);},[search]);
  useEffect(()=>{setPaginationModel(current=>({...current,page:0}));},[status,querySearch,direction,from,to,sortKey]);
  const load=useCallback(async()=>{
    const request=++loadSequence.current.value;setRefreshing(true);
    try {
      if(from&&to&&from>to){setRows([]);setRowCount(0);return;}
      const query=new URLSearchParams({page:String(paginationModel.page+1),page_size:String(paginationModel.pageSize),status,direction,search:querySearch,sort:sortKey});
      if(from)query.set("from",from);if(to)query.set("to",to);
      const [response,profileResponse]=await Promise.all([apiFetch("/bank-reconciliation?"+query),apiFetch("/auth/me")]);
      const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Could not load reconciliation records."));
      if(!Array.isArray(data.transactions)||!data.counts||typeof data.counts!=="object")throw new Error("Reconciliation records could not be read. Please refresh.");
      if(request!==loadSequence.current.value)return;
      setRows((data.transactions||[]).map((row:BankRow)=>({...row,amount:String(row.amount)})));setCounts(data.counts||{});setRowCount(data.count??data.transactions.length);if(data.count>0&&paginationModel.page*paginationModel.pageSize>=data.count)setPaginationModel(current=>({...current,page:Math.ceil(data.count/current.pageSize)-1}));setLoadedAt(new Date().toISOString());setError("");
      setCanReview(profileResponse.ok&&["OWNER","FINANCE"].includes((await profileResponse.json()).role));
    } catch(e){if(request===loadSequence.current.value)setError(financialErrorMessage(e,"Could not load reconciliation records."));}
    finally {if(request===loadSequence.current.value){setLoading(false);setRefreshing(false);}}
  },[paginationModel.page,paginationModel.pageSize,status,direction,querySearch,sortKey,from,to]);
  useEffect(()=>{const query=new URLSearchParams(window.location.search).get("status");if(query&&Object.prototype.hasOwnProperty.call(statusLabels,query))setStatus(query as StatusFilter);},[]);
  useEffect(()=>{const tracker=loadSequence.current;void load();const update=()=>setOnline(navigator.onLine);update();window.addEventListener("online",update);window.addEventListener("offline",update);return()=>{tracker.value++;window.removeEventListener("online",update);window.removeEventListener("offline",update);};},[load]);
  const selectedAmount=selected?.amount||"";
  useEffect(()=>{setCandidate(null);setCandidateError("");setManualId("");setManualType(moneyDirection(selectedAmount)==="IN"?"CUSTOMER_COLLECTION":"VENDOR_PAYMENT");},[selectedId,selectedAmount]);
  const dateError=Boolean(from&&to&&from>to);
  useEffect(()=>{
    if(!importOpen)return;
    let active=true;
    apiFetch("/settlements/accounts").then(async response=>{
      if(!response.ok)throw new Error("Could not load bank source accounts. Open Settlement sources to check your access.");
      const data=await response.json();if(active)setSourceAccounts((data.accounts||[]).filter((item:{kind:string;active:boolean})=>item.kind==="BANK"&&item.active));
    }).catch(error=>{if(active)setImportError(error.message);});
    return()=>{active=false;};
  },[importOpen]);
  const filtered=rows;
  const total=counts?Object.values(counts).reduce((sum,count)=>sum+count,0):0;
  const reviewCount = (counts?.UNMATCHED ?? 0) + (counts?.DUPLICATE ?? 0);
  const currentQueue = status === "UNMATCHED" || status === "DUPLICATE" ? "REVIEW" : status;
  const visibleCounts = { REVIEW: reviewCount, MATCHED: counts?.MATCHED ?? 0, RECONCILED: counts?.RECONCILED ?? 0, ALL: total };
  useEffect(() => {
    if (selectedId && !selected && !loading && !refreshing) setSelectedId("");
  }, [selectedId, selected, loading, refreshing]);
  function rejectCandidate(item:MatchCandidate) {setFeedback(item);setFeedbackReason("");setFeedbackKey(crypto.randomUUID());setCandidateError("");}
  async function submitFeedback() {
    if(!selected||!feedback?.candidate_id||!feedbackReason.trim()||writing.current)return;
    writing.current=true;setBusy(true);setCandidateError("");
    try{const response=await apiFetch("/bank-reconciliation",{method:"PATCH",body:JSON.stringify({action:"reject_candidate",transaction_id:selected.id,candidate_id:feedback.candidate_id,reason:feedbackReason.trim(),request_key:feedbackKey,expected_revision:selected.revision})});if(!response.ok)throw new Error(apiError(await response.json(),"Could not reject candidate."));setFeedback(null);setCandidate(null);setHistoryVersion(value=>value+1);await findCandidates(selected);}catch(e){setCandidateError(financialErrorMessage(e,"Could not save feedback."));}finally{writing.current=false;setBusy(false);}
  }
  function openRow(row:BankRow){setSelectedId(row.id);setMutationError("");}
  async function findCandidates(row:BankRow){
    if(suggesting)return;setSuggesting(row.id);setCandidateError("");
    try{const response=await apiFetch(`/bank-reconciliation?suggestions_for=${row.id}`);const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Could not load candidates."));setSuggestions(current=>({...current,[row.id]:(data.suggestions||[]).map((item:MatchCandidate)=>({...item,amount:String(item.amount)}))}));setCandidateMeta(current=>({...current,[row.id]:{ambiguous:Boolean(data.ambiguous),limited:Boolean(data.candidate_limit_reached),at:data.generated_at}}));}
    catch(e){setCandidateError(financialErrorMessage(e,"Could not load candidates."));}finally{setSuggesting("");}
  }
  function begin(action:Action){if(busy)return;setAcknowledged(false);setMutationError("");setReason("");setRequestKey(crypto.randomUUID());setReview(action);}
  async function confirm(){
    if(!selected||!review||!acknowledged||writing.current)return;
    const bankId=selected.id;const intent=review;writing.current=true;setBusy(true);setMutationError("");
    try{
      const target=intent.candidate?{candidate_id:intent.candidate.candidate_id,target_id:intent.candidate.target_id,target_type:intent.candidate.target_type}:intent.manual||{};
      const response=await apiFetch("/bank-reconciliation",{method:"PATCH",body:JSON.stringify({transaction_id:bankId,action:intent.action,...target,reason,request_key:requestKey,expected_revision:selected.revision})});
      const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Could not complete this action. Refresh before retrying."));
      setRows(current=>current.map(row=>row.id===bankId?{...row,status:data.status,payment_id:data.payment_id||null,transport_collection_id:data.target_type==="CUSTOMER_COLLECTION"?data.target_id:null,driver_salary_payment_id:data.target_type==="DRIVER_SALARY_PAYMENT"?data.target_id:null}:row));setReview(null);setCandidate(null);setSuggestions(current=>{const next={...current};delete next[bankId];return next;});
      showNotice(intent.action==="match"?"Match recorded. Review and confirm reconciliation next.":intent.action==="reconcile"?"Reconciliation confirmed.":"Match cleared. The bank row needs matching again.","success");
      setHistoryVersion(value=>value+1);await load();
    }catch(e){setMutationError(financialErrorMessage(e,"Could not complete this action."));}finally{writing.current=false;setBusy(false);}
  }
  async function importStatement(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();if(!file||writing.current)return;
    if(!sourceAccountId){setImportError("Select the statement bank source account.");return;}
    if(!/\.(csv|xlsx)$/i.test(file.name)||file.size>10*1024*1024){setImportError("Choose a CSV or XLSX statement up to 10 MB.");return;}
    if(Object.values(columns).some(value=>!value.trim())){setImportError("Enter a column header for each field in Statement column mapping.");return;}
    writing.current=true;setBusy(true);setImportError("");
    try{const form=new FormData();form.set("file",file);form.set("account_id",sourceAccountId);Object.entries(columns).forEach(([key,value])=>form.set(`${key}_column`,value.trim()));const response=await apiFetch("/bank-reconciliation",{method:"POST",body:form});const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Statement import failed."));showNotice(data.duplicate_import?"This statement was already imported. No new rows were added.":`${data.imported_rows} statement rows imported. Review them before matching.`,data.duplicate_import?"info":"success");setFile(null);setImportOpen(false);await load();}
    catch(e){setImportError(financialErrorMessage(e,"Import failed. Please retry with the same statement."));}finally{writing.current=false;setBusy(false);}
  }
  async function generateTestFeed(){
    if(writing.current||busy)return;
    writing.current=true;setBusy(true);setError("");
    try{const response=await apiFetch("/bank-reconciliation",{method:"POST",body:JSON.stringify({action:"generate_test_feed"})});const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Could not generate test bank feed."));showNotice(data.message||`${data.imported_rows} simulated bank rows added.`,data.duplicate_import?"info":"success");await load();}
    catch(e){showNotice(financialErrorMessage(e,"Could not generate test bank feed."),"error");}
    finally{writing.current=false;setBusy(false);}
  }
  const gridColumns=useMemo<GridColDef<BankRow>[]>(()=>[
    {field:"status",headerName:"Status",width:200,hideable:false,renderCell:({row})=><FinancialStatus status={row.status}/>},
    {field:"description",headerName:"Bank transaction",minWidth:195,flex:1,
      renderCell:({row})=><Stack direction="row" spacing={1} sx={{ alignItems: "center", minWidth: 0, width: "100%" }}>
        {row.is_test_data && <Chip size="small" color="warning" variant="outlined" label="Test data"/>}
        <Typography variant="body2" noWrap title={row.description}>{row.description}</Typography>
      </Stack>},
    {field:"amount",headerName:"Amount",type:"number",width:145,valueGetter:value=>Number(value),renderCell:({row})=><Money value={row.amount} currency={row.currency||""}/>},
    {field:"date",headerName:"Bank date",width:112,valueFormatter:value=>financialDate(String(value))},
    {field:"reference",headerName:"Bank reference",minWidth:120,flex:.6},
    {field:"actions",headerName:"Next step",width:145,sortable:false,filterable:false,disableExport:true,renderCell:({row})=><Button type="button" size="small" onClick={()=>openRow(row)}>{reviewAction(row,canReview)}</Button>},
  ],[canReview]);
  const comparison=selected&&review?.candidate?compareCandidate(selected,review.candidate):null;
  return <Box component="main" sx={{p:{xs:2,md:3},width:"100%",minWidth:0}}>
    <FinancialHeader eyebrow="Financial operations" title="Bank reconciliation" description="See which bank transactions need review, which are matched, and which matches are confirmed." action={<Stack direction="row" spacing={1} sx={{flexWrap:"wrap"}}><Button variant="outlined" disabled={refreshing||busy} startIcon={<RefreshCw size={16}/>} onClick={()=>void load()}>Refresh</Button>{canReview&&<><Button variant="outlined" color="warning" disabled={!online||busy} startIcon={<FlaskConical size={16}/>} onClick={()=>void generateTestFeed()}>Generate test bank feed</Button><Button variant="contained" disabled={!online||busy} startIcon={<Upload size={16}/>} onClick={()=>{setImportError("");setFile(null);setImportOpen(true);}}>Import statement</Button></>}</Stack>}/>
    {!online&&<Alert severity="warning" sx={{mb:2}}>You are offline. Previously loaded records remain visible. Matching and import actions are paused.</Alert>}
    {error&&<Alert severity="error" action={<Button color="inherit" disabled={refreshing} onClick={()=>void load()}>Retry</Button>} sx={{mb:2}}>{error} {rows.length>0&&"Previously loaded records may be out of date."}</Alert>}
    {loading?<ContentSkeleton variant="cards" rows={3} label="Loading reconciliation workspace"/>:<>
      {!canReview&&<Alert severity="info" sx={{mb:2}}>Read-only view. Only workspace owners and finance users can import, match or confirm records.</Alert>}
      <Box role="group" aria-label="Bank transaction queues" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {queues.map(({ value, label, detail, icon: Icon, tone }) => (
          <Button key={value} variant="outlined" aria-pressed={currentQueue === value} onClick={() => setStatus(value)}
            sx={{
              p: 1.75, textAlign: "left", justifyContent: "flex-start", gap: 1.25,
              bgcolor: currentQueue === value ? "action.selected" : "background.paper",
              borderColor: currentQueue === value ? "primary.main" : "divider",
            }}>
            <Box component="span" sx={{ display: "grid", placeItems: "center", width: 34, height: 34, flexShrink: 0, borderRadius: 2, bgcolor: "action.hover", color: tone }}>
              <Icon size={18} aria-hidden="true"/>
            </Box>
            <Box component="span" sx={{ flex: 1, minWidth: 0 }}>
              <Typography component="span" variant="subtitle2" sx={{ display: "block" }}>{label}</Typography>
              <Typography component="span" variant="caption" color="text.secondary" sx={{ display: "block" }}>{detail}</Typography>
            </Box>
            <Typography component="span" variant="h6" sx={{ fontVariantNumeric: "tabular-nums", fontWeight: 750 }}>{counts ? visibleCounts[value] : "—"}</Typography>
          </Button>
        ))}
      </Box>

      <Paper component="section" variant="outlined" sx={{ mt: 2.5, overflow: "hidden", borderRadius: 3 }}>
        <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between" }}>
            <Box>
              <Typography component="h2" variant="h6">{statusLabels[status]}</Typography>
              <Typography variant="body2" color="text.secondary" aria-live="polite">
                {refreshing ? "Loading transactions…" : `${rowCount} matching ${rowCount === 1 ? "transaction" : "transactions"}`}
              </Typography>
            </Box>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField size="small" label="Search transactions" placeholder="Description, reference, or statement" value={search}
                slotProps={{ htmlInput: { maxLength: 120 } }} onChange={event => setSearch(event.target.value)} sx={{ minWidth: { sm: 245 } }}/>
              <TextField select size="small" label="Status" value={status} onChange={event => setStatus(event.target.value as StatusFilter)} sx={{ minWidth: 165 }}>
                {Object.entries(statusLabels).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
              </TextField>
            </Stack>
          </Stack>
          <Box component="details" sx={{ mt: 1.5 }}>
            <Typography component="summary" variant="body2" sx={{ cursor: "pointer", fontWeight: 600 }}>
              Date and direction filters{(from || to || direction !== "ALL") && " · Active"}
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={1.5} sx={{ mt: 1.5, flexWrap: "wrap" }}>
              <TextField select size="small" label="Direction" value={direction} onChange={event => setDirection(event.target.value)} sx={{ minWidth: 155 }}>
                <MenuItem value="ALL">All directions</MenuItem><MenuItem value="IN">Money in</MenuItem><MenuItem value="OUT">Money out</MenuItem>
              </TextField>
              <TextField size="small" label="From date" type="date" value={from} onChange={event => setFrom(event.target.value)} slotProps={{ inputLabel: { shrink: true } }}/>
              <TextField size="small" label="To date" type="date" value={to} error={dateError} helperText={dateError ? "End date must follow start date." : undefined}
                onChange={event => setTo(event.target.value)} slotProps={{ inputLabel: { shrink: true } }}/>
            </Stack>
          </Box>
          {(search || from || to || direction !== "ALL") && <Button size="small" sx={{ mt: 1 }} onClick={() => { setSearch(""); setFrom(""); setTo(""); setDirection("ALL"); }}>Clear search and filters</Button>}
        </Box>
        {refreshing && <LinearProgress aria-label="Refreshing bank records"/>}
        {dateError ? <EmptyState kind="search" title="Check the date range" description="The end date must be on or after the start date."/> :
          !filtered.length ? !refreshing && <EmptyState
            kind={error ? "error" : total ? "search" : "empty"}
            title={error ? "Reconciliation records unavailable" : !total ? "No statements imported" : !search && !from && !to && direction === "ALL" && status === "REVIEW" ? "No transactions need matching or duplicate review" : "No transactions in this view"}
            description={error || (total ? "Choose another status or adjust your filters." : "Import a CSV or XLSX bank statement to get started.")}
            actionLabel={error ? "Retry" : total ? "Show all transactions" : canReview ? "Import statement" : undefined}
            onAction={error ? () => void load() : total ? () => { setStatus("ALL"); setSearch(""); setFrom(""); setTo(""); setDirection("ALL"); } :
              canReview ? () => { setFile(null); setImportError(""); setImportOpen(true); } : undefined}/> :
          mobile ? <Box sx={{ px: 2 }}>
            {filtered.map(row => <Box key={row.id} sx={{ py: 2, borderBottom: 1, borderColor: "divider" }}>
              <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <FinancialStatus status={row.status}/>
                <Money value={row.amount} currency={row.currency || ""}/>
              </Stack>
              <Typography variant="subtitle2" sx={{ mt: 1, overflowWrap: "anywhere" }}>{row.description}</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>
                {financialDate(row.date)}{row.reference ? ` · Ref ${row.reference}` : ""}{row.is_test_data ? " · Test data" : ""}
              </Typography>
              <Button size="small" sx={{ mt: .75 }} onClick={() => openRow(row)}>{reviewAction(row, canReview)}</Button>
            </Box>)}
            <TablePagination component="div" count={rowCount} page={paginationModel.page} rowsPerPage={paginationModel.pageSize}
              rowsPerPageOptions={[10, 25, 50, 100]} onPageChange={(_, page) => setPaginationModel(current => ({ ...current, page }))}
              onRowsPerPageChange={event => setPaginationModel({ page: 0, pageSize: Number(event.target.value) })}/>
          </Box> :
          <Box sx={{ height: 580, display: "flex", flexDirection: "column" }}>
            <GridDensityControl value={preferences.density} onChange={preferences.onDensityChange}/>
            <DataGrid {...preferences} columnVisibilityModel={{ ...preferences.columnVisibilityModel, status: true }}
              showToolbar slotProps={{ toolbar: { showQuickFilter: false, csvOptions: { disableToolbarButton: true }, printOptions: { disableToolbarButton: true } } }}
              rows={filtered} columns={gridColumns} rowCount={rowCount} paginationMode="server" sortingMode="server"
              disableColumnFilter paginationModel={paginationModel} onPaginationModelChange={setPaginationModel} disableRowSelectionOnClick
              pageSizeOptions={[10, 25, 50, 100]} sx={{ border: 0, minHeight: 0, flex: 1, fontSize: 13 }}/>
          </Box>}
        {loadedAt && <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 2, py: 1 }}>Updated {financialDate(loadedAt, true)} · Queue counts cover the workspace</Typography>}
      </Paper>
    </>}
    <Drawer open={Boolean(selected)} anchor="right" onClose={()=>{if(!busy)setSelectedId("");}} slotProps={{paper:{role:"dialog","aria-modal":true,"aria-label":"Review bank transaction",sx:{width:{xs:"100%",sm:620},maxWidth:"100%",p:{xs:2,sm:3}}}}}>
      {selected&&<>{candidateError&&<Alert severity="error" sx={{my:2}}>{candidateError}</Alert>}{selected.statement_id&&<Button disabled={busy} onClick={()=>void downloadSource(selected)}>Download original statement</Button>}{selected.source_verified===false&&<Alert severity="warning" sx={{mb:2}} action={<Button component={NextLink} href={"/settlements?record_type=BANK_STATEMENT&record_id="+selected.statement_id}>Verify source</Button>}>This statement has unknown account/currency provenance. Verify the bank statement and internal payment before matching.</Alert>}<Stack direction="row" spacing={2} sx={{justifyContent:"space-between",mb:2}}><Box><Typography variant="overline" color="text.secondary">Bank statement transaction</Typography><Typography component="h2" variant="h6">{selected.description}</Typography><Box sx={{my:1}}><Money value={selected.amount} currency={selected.currency||""} large/></Box><Stack direction="row" spacing={1} sx={{alignItems:"center"}}>{moneyDirection(selected.amount)==="IN"?<ArrowDownLeft size={16}/>:<ArrowUpRight size={16}/>}<Typography variant="caption">{moneyDirection(selected.amount)==="IN"?"Money in":"Money out"}</Typography></Stack><Box sx={{mt:1}}><FinancialStatus status={selected.status}/></Box></Box><IconButton aria-label="Close transaction review" disabled={busy} onClick={()=>setSelectedId("")}><X size={20}/></IconButton></Stack>
        <DetailGroup title="Statement information" fields={{"Transaction date":financialDate(selected.date),"Bank reference":<CopyReference value={selected.reference} label="bank reference"/>,"Statement file":selected.statement,"Bank row ID":<CopyReference value={selected.id} label="bank row ID"/>}}/>
        {selected.status==="DUPLICATE"&&<Alert severity="warning">The importer flagged this row as a duplicate. Compare the source statement with the original row before taking any action. Duplicates require a separate review; no dismissal action is available here.</Alert>}
        {(selected.payment_id||selected.transport_collection_id||selected.driver_salary_payment_id)&&<DetailGroup title="Linked internal record" fields={{"Record type":selected.payment_id?"Vendor payment":selected.transport_collection_id?"Customer collection":"Driver salary payment","Record ID":<CopyReference value={selected.payment_id||selected.transport_collection_id||selected.driver_salary_payment_id} label="linked record ID"/>}}/>}
        {selected.status==="UNMATCHED"&&canReview&&selected.source_verified!==false&&<Box component="section"><Typography component="h3" variant="subtitle2">Find an internal record</Typography><Typography variant="body2" color="text.secondary" sx={{my:1}}>Saved candidates require the same account, currency, amount and direction, with dates within seven days. Multiple options remain ambiguous. A rule score is an evidence hint, not a verified match.</Typography><Button variant="outlined" disabled={!online||Boolean(suggesting)||busy} onClick={()=>void findCandidates(selected)}>{suggesting===selected.id?"Finding candidates…":"Find candidates"}</Button>
          {suggesting===selected.id&&<ContentSkeleton variant="cards" rows={1} label="Finding matching records"/>}
          {candidateMeta[selected.id]?.ambiguous&&<Alert severity="warning" sx={{my:1}}>Several eligible records remain ambiguous. Verify the source reference before choosing; the first result is not an automatic match.</Alert>}{candidateMeta[selected.id]?.limited&&<Alert severity="info" sx={{my:1}}>Candidate search or display reached its limit. Use the full payment register and manual record link if the correct record is missing.</Alert>}{candidateMeta[selected.id]?.at&&<Typography variant="caption">Evidence saved {financialDate(candidateMeta[selected.id].at,true)}</Typography>}{suggestions[selected.id]?.map(item=><Paper key={`${item.target_type}:${item.target_id}`} variant="outlined" sx={{p:2,my:1.5,borderColor:candidate?.target_id===item.target_id?"primary.main":"divider"}}><FormControlLabel sx={{m:0,alignItems:"flex-start"}} control={<Radio name="match-candidate" disabled={item.rejected||busy} checked={candidate?.target_id===item.target_id&&candidate.target_type===item.target_type} onChange={()=>setCandidate(item)}/>} label={<Box><Typography component="div" variant="subtitle2">{item.vendor}</Typography><Typography variant="body2"><Money value={item.amount} currency={item.currency||selected.currency||""}/> · {financialDate(item.paid_at)}</Typography><Typography variant="caption" color="text.secondary">{targetLabels[item.target_type]} · Rule score {item.score}/100</Typography></Box>}/><CopyReference value={item.payment_reference} label="candidate reference"/><Typography variant="caption" color="text.secondary">{item.reasons.join(" · ")}</Typography>{item.rejected?<Chip size="small" label="Rejected by reviewer"/>:item.candidate_id&&<Button color="warning" disabled={busy} onClick={()=>void rejectCandidate(item)}>Reject candidate</Button>}</Paper>)}
          {suggestions[selected.id]?.length===0&&<EmptyState title="No candidates in the suggestion window" description="Check the transaction date, reference and internal payment records. You can link a known record using its ID below."/>}
          {candidate&&<Button variant="contained" disabled={busy||!online} onClick={()=>begin({action:"match",candidate})}>Review selected match</Button>}
          <Accordion disableGutters sx={{mt:2,boxShadow:"none",border:"1px solid",borderColor:"divider"}}><AccordionSummary expandIcon={<ChevronDown size={16}/>}>Link a known record by ID</AccordionSummary><AccordionDetails><Typography variant="caption" color="text.secondary">Use an ID copied from the payment or fleet record. Matching checks its account, currency, amount, direction, workspace and existing links.</Typography><UiForm onSubmit={event=>{event.preventDefault();if(validId.test(manualId.trim()))begin({action:"match",manual:{target_type:manualType,target_id:manualId.trim()}});}}><TextField select label="Internal record type" fullWidth value={manualType} onChange={event=>setManualType(event.target.value as MatchCandidate["target_type"])} slotProps={{select:{native:true}}} sx={{my:2}}>{Object.entries(targetLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</TextField><TextField label="Internal record ID" fullWidth required value={manualId} onChange={event=>setManualId(event.target.value)} error={Boolean(manualId&&!validId.test(manualId.trim()))} helperText="Paste the record UUID, not its bank reference."/><Button type="submit" disabled={!validId.test(manualId.trim())||busy||!online} sx={{mt:1}}>Review manual link</Button></UiForm></AccordionDetails></Accordion>
        </Box>}
        {canReview&&selected.status==="MATCHED"&&<Alert severity="info" sx={{mb:2}}>An internal record is linked. Confirm reconciliation only after checking it against the bank statement.</Alert>}
        <ReconciliationGroups selected={selected} canReview={canReview&&online} onChanged={async()=>{setHistoryVersion(value=>value+1);await load();}}/>
        {canReview&&!selected.group_id&&["MATCHED","RECONCILED"].includes(selected.status)&&<Stack direction="row" spacing={1} sx={{flexWrap:"wrap",gap:1}}>{selected.status==="MATCHED"&&<Button variant="contained" disabled={busy||!online||selected.source_verified===false} onClick={()=>begin({action:"reconcile"})}>Review & confirm reconciliation</Button>}<Button color="warning" variant="outlined" disabled={busy||!online} onClick={()=>begin({action:"unmatch"})}>Clear match</Button></Stack>}
        <ReconciliationHistory bankId={selected.id} version={historyVersion}/>
        <DetailGroup title="Other financial information" fields={{"Gateway reference":"Not supplied with this statement","Settlement date / fees":"Not supplied","Review history":"Open Review history and matching evidence above"}}/>
      </>}
    </Drawer>
    <Dialog open={Boolean(review&&selected)} onClose={()=>{if(!busy)setReview(null);}} fullWidth maxWidth="sm" aria-labelledby="reconciliation-confirm-title"><DialogTitle id="reconciliation-confirm-title">{review?.action==="match"?"Review match":review?.action==="reconcile"?"Confirm reconciliation":"Clear this match?"}</DialogTitle><DialogContent>{selected&&review&&<>
      <Typography variant="body2" sx={{mb:2}}>{review.action==="match"?"This links an internal record to the statement row. Final reconciliation still requires a separate confirmation.":review.action==="reconcile"?"This marks the existing match as reconciled and records the action in the audit log.":"This removes the internal link and returns the bank row to needs matching. Payment records are unchanged."}</Typography>
      <DetailGroup title="Compare before confirming" fields={{"Bank reference":<CopyReference value={selected.reference} label="bank reference"/>,"Bank date":financialDate(selected.date),"Bank amount (absolute)":<Money value={absoluteAmount(selected.amount)} currency={selected.currency||""}/>,"Internal record":<CopyReference value={review.candidate?.target_id||review.manual?.target_id||selected.payment_id||selected.transport_collection_id||selected.driver_salary_payment_id} label="internal record ID"/>,"Expected amount":review.candidate?<Money value={review.candidate.amount} currency={review.candidate.currency||selected.currency||""}/>:"Not loaded here; the amount is checked when the record is linked","Amount difference":comparison?<Money value={comparison.difference} currency={selected.currency||""}/>:"Not available","Internal payment date":review.candidate?financialDate(review.candidate.paid_at):"Not retrieved"}}/>
      {comparison&&(!comparison.amountMatches||!comparison.directionMatches)&&<Alert severity="error">Amount or direction differs. This candidate cannot be linked.</Alert>}
      {mutationError&&<Alert severity="error" sx={{my:2}}>{mutationError}</Alert>}
      <TextField label="Review / correction reason" value={reason} onChange={event=>setReason(event.target.value)} required={review?.action==="unmatch"} fullWidth multiline minRows={2} slotProps={{htmlInput:{maxLength:500}}} sx={{my:2}}/>
      <FormControlLabel control={<Checkbox checked={acknowledged} disabled={busy} onChange={event=>setAcknowledged(event.target.checked)}/>} label="I checked the statement, record reference, amount and direction."/>
      <Typography variant="caption" color="text.secondary" sx={{display:"block",mt:1}}>This action does not transfer funds or initiate a refund.</Typography>
    </>}</DialogContent><DialogActions><Button disabled={busy} onClick={()=>setReview(null)}>Cancel</Button><Button variant="contained" disabled={!acknowledged||busy||!online||Boolean(review?.action==="unmatch"&&!reason.trim())||Boolean(selected&&moneyDirection(selected.amount)==="UNKNOWN")||Boolean(comparison&&(!comparison.amountMatches||!comparison.directionMatches))} onClick={()=>void confirm()}>{busy?"Saving…":review?.action==="match"?"Record match":review?.action==="reconcile"?"Confirm reconciliation":"Clear match"}</Button></DialogActions>{busy&&<LinearProgress aria-label="Saving reconciliation action"/>}</Dialog>
    <Dialog open={Boolean(feedback)} onClose={()=>{if(!busy)setFeedback(null);}} fullWidth maxWidth="sm"><DialogTitle>Reject this candidate</DialogTitle><DialogContent><Typography variant="body2" sx={{mb:2}}>The payment is unchanged. Your reason is retained with the saved matching evidence.</Typography>{candidateError&&<Alert severity="error" sx={{mb:2}}>{candidateError}</Alert>}<TextField label="Rejection reason" value={feedbackReason} onChange={event=>setFeedbackReason(event.target.value)} multiline minRows={2} fullWidth required slotProps={{htmlInput:{maxLength:500}}}/></DialogContent><DialogActions><Button disabled={busy} onClick={()=>setFeedback(null)}>Cancel</Button><Button color="warning" disabled={busy||!feedbackReason.trim()||!online} onClick={()=>void submitFeedback()}>Save rejection</Button></DialogActions></Dialog>
    <Dialog open={importOpen} onClose={()=>{if(!busy)setImportOpen(false);}} fullWidth maxWidth="sm" aria-labelledby="import-statement-title"><UiForm onSubmit={importStatement}><DialogTitle id="import-statement-title">Import bank statement</DialogTitle><DialogContent><Typography variant="body2" color="text.secondary" sx={{mb:2}}>CSV or XLSX, up to 10 MB. Positive amounts are money in; negative amounts are money out. Importing does not automatically match or reconcile rows.</Typography><TextField select fullWidth label="Bank source account" required disabled={busy} value={sourceAccountId} onChange={event=>setSourceAccountId(event.target.value)} sx={{mb:2}}>{sourceAccounts.map(account=><MenuItem key={account.id} value={account.id}>{account.name+" · "+account.currency}</MenuItem>)}</TextField><Button component={NextLink} href="/settlements" sx={{mb:2}}>Manage source accounts</Button><TextField type="file" fullWidth required disabled={busy} slotProps={{htmlInput:{accept:".csv,.xlsx","aria-label":"Bank statement file"}}} onChange={event=>setFile((event.target as HTMLInputElement).files?.[0]||null)}/><Accordion disableGutters sx={{mt:2,boxShadow:"none",border:"1px solid",borderColor:"divider"}}><AccordionSummary expandIcon={<ChevronDown size={16}/>}>Statement column mapping</AccordionSummary><AccordionDetails><Stack spacing={2}>{Object.entries(columns).map(([key,value])=><TextField key={key} label={`${key[0].toUpperCase()+key.slice(1)} column header`} value={value} disabled={busy} onChange={event=>setColumns(current=>({...current,[key]:event.target.value}))}/>)}</Stack></AccordionDetails></Accordion>{importError&&<Alert severity="error" sx={{mt:2}}>{importError}</Alert>}</DialogContent><DialogActions><Button disabled={busy} onClick={()=>setImportOpen(false)}>Cancel</Button><Button type="submit" variant="contained" disabled={!file||!sourceAccountId||busy||!online}>{busy?"Importing…":"Import statement"}</Button></DialogActions>{busy&&<LinearProgress aria-label="Importing bank statement"/>}</UiForm></Dialog>
  </Box>;
}
