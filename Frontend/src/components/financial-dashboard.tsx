"use client";

import { useCallback, useEffect, useState } from "react";
import NextLink from "next/link";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Alert from "@mui/material/Alert";
import LinearProgress from "@mui/material/LinearProgress";
import { FinancialMetric, Money, FinancialStatus } from "@/components/financial-ui";
import { TransactionDetails } from "@/components/transaction-details";
import { ContentSkeleton } from "@/components/content-skeleton";
import { EmptyState } from "@/components/empty-state";
import { LiveData } from "@/components/live-data";
import { apiFetch } from "@/lib/api";
import { apiError, financialErrorMessage, decimalAmount, minorUnits, financialDate, type LedgerPayment } from "@/lib/finance";
import type { DashboardAnalytics } from "@/components/overview-charts";

export function FinancialDashboard({ analytics }: {analytics?:DashboardAnalytics}) {
  const [payments,setPayments]=useState<LedgerPayment[]|null>(null),[vendors,setVendors]=useState<{id:string;name:string}[]>([]);
  const [counts,setCounts]=useState<Record<string,number>|null>(null),[error,setError]=useState("");
  const [loading,setLoading]=useState(true),[refreshing,setRefreshing]=useState(false),[loadedAt,setLoadedAt]=useState("");
  const [selected,setSelected]=useState<LedgerPayment|null>(null);
  const load=useCallback(async(silent=false)=>{
    setRefreshing(true);
    try {
      const [paymentResponse,bankResponse,vendorResponse]=await Promise.all([apiFetch("/payments?paginated=1&page_size=5"),apiFetch("/bank-reconciliation"),apiFetch("/vendors")]);
      const [paymentData,bankData]=await Promise.all([paymentResponse.json(),bankResponse.json()]);
      if(!paymentResponse.ok||!bankResponse.ok)throw new Error(apiError(!paymentResponse.ok?paymentData:bankData,"Could not load financial records."));
      if(!Array.isArray(paymentData.results)||!Array.isArray(bankData.transactions)||!bankData.counts||typeof bankData.counts!=="object")throw new Error("Financial records could not be read. Please refresh.");
      setPayments(paymentData.results);setCounts(bankData.counts||{});if(vendorResponse.ok)setVendors(await vendorResponse.json());setLoadedAt(new Date().toISOString());setError("");
    }catch(e){setError(financialErrorMessage(e,"Financial records are unavailable."));if(silent)throw e;}
    finally{setLoading(false);setRefreshing(false);}
  },[]);
  useEffect(()=>{void load();},[load]);
  const balance=analytics?.payable_aging?decimalAmount(analytics.payable_aging.reduce((sum,item)=>sum+minorUnits(item.amount),0n)):null;
  const overdue=analytics?.payable_aging?decimalAmount(analytics.payable_aging.filter(item=>!["NOT_OVERDUE","NO_DUE_DATE"].includes(item.bucket)).reduce((sum,item)=>sum+minorUnits(item.amount),0n)):null;
  return <Box component="section" aria-label="Financial position" sx={{mt:3}}>
    {error&&<Alert severity="error" sx={{mb:2}} action={<Button color="inherit" disabled={refreshing} onClick={()=>void load()}>Retry</Button>}>{error} {payments&&"Previously loaded payment information may be out of date."}</Alert>}
    {loading?<ContentSkeleton variant="cards" rows={3} label="Loading financial position"/>:<>
      <Box sx={{display:"grid",gap:2,gridTemplateColumns:{xs:"1fr",md:"repeat(3,minmax(0,1fr))"}}}>
        <FinancialMetric label="Approved invoice balance" value={balance!==null?<Money value={balance}/>:"Unavailable"} detail="Outstanding in the invoice ledger · not a bank balance"/>
        <FinancialMetric label="Overdue approved invoices" value={overdue!==null?<Money value={overdue}/>:"Unavailable"} detail="Recorded totals minus allocated payments, past the due date"/>
        <FinancialMetric label="Bank rows needing attention" value={counts?(counts.UNMATCHED||0)+(counts.MATCHED||0)+(counts.DUPLICATE||0):"—"} detail={counts?`${counts.UNMATCHED||0} unmatched · ${counts.MATCHED||0} awaiting confirmation · ${counts.DUPLICATE||0} duplicates`:"Reconciliation information unavailable"}/>
      </Box>
      {counts && (counts.UNMATCHED||0)+(counts.MATCHED||0)+(counts.DUPLICATE||0)>0 ? <Paper variant="outlined" sx={{my:2,p:2,display:"flex",justifyContent:"space-between",alignItems:{sm:"center"},gap:2,flexDirection:{xs:"column",sm:"row"}}}><Typography variant="body2">Review unmatched statement rows first, then confirm checked matches.</Typography><Button component={NextLink} href="/bank-reconciliation?status=UNMATCHED" variant="contained">Review reconciliation</Button></Paper> : counts && <Typography variant="caption" color="text.secondary" sx={{display:"block",my:2}}>{Object.values(counts).some(count=>count>0)?"No reconciliation items are waiting for review.":"No bank statement rows have been imported. Open reconciliation to begin."}</Typography>}
      <Paper variant="outlined" sx={{overflow:"hidden"}}><Stack direction="row" sx={{p:2,justifyContent:"space-between",alignItems:"center"}}><Box><Typography component="h2" variant="subtitle1">Recent recorded payments</Typography><Typography variant="caption" color="text.secondary">Latest payment dates · internal records, not verified bank settlement</Typography></Box><Button component={NextLink} href="/payments">View register</Button></Stack>
        {refreshing&&<LinearProgress aria-label="Refreshing financial records"/>}
        {payments?.length?payments.slice(0,5).map(payment=><Box key={payment.id} sx={{px:2,py:1.5,borderTop:"1px solid",borderColor:"divider",display:"grid",alignItems:"center",gap:1.5,gridTemplateColumns:{xs:"minmax(0,1fr) auto",md:"minmax(0,1.5fr) minmax(0,1fr) 160px 140px auto"}}}><Box><Typography variant="body2" sx={{fontWeight:600}}>{payment.vendor_name||vendors.find(vendor=>vendor.id===payment.vendor)?.name||"Vendor payment"}</Typography><Typography variant="caption" color="text.secondary">{payment.reference_number||"Reference not provided"}</Typography></Box><Typography variant="caption" color="text.secondary">{financialDate(payment.paid_at)}</Typography><Money value={payment.amount}/><FinancialStatus status="RECORDED"/><Button size="small" onClick={()=>setSelected(payment)}>Details</Button></Box>):<EmptyState kind={error?"error":"empty"} title={error?"Payment history unavailable":"No payments recorded yet"} description={error||"Approved invoices and recorded payments will appear here as your team completes its finance workflow."}/>}
        <Typography variant="caption" color="text.secondary" sx={{display:"block",p:2,borderTop:"1px solid",borderColor:"divider"}}>Payment history shows the five most recent active records. Reconciliation counts cover all imported rows.{loadedAt&&` Last loaded ${financialDate(loadedAt,true)}.`}</Typography>
      </Paper>
    </>}
    <LiveData onRefresh={()=>load(true)} interval={30000} paused={loading||Boolean(selected)||refreshing}/>
    <TransactionDetails payment={selected} counterparty={vendors.find(vendor=>vendor.id===selected?.vendor)?.name||"Vendor payment"} onClose={()=>setSelected(null)}/>
  </Box>;
}
