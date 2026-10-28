"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import NextLink from "next/link";
import { X } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { apiError, financialErrorMessage, financialDate, type BankRow, type LedgerPayment } from "@/lib/finance";
import { Money, FinancialStatus, DetailGroup, CopyReference } from "@/components/financial-ui";
import { ContentSkeleton } from "@/components/content-skeleton";

export function TransactionDetails({ payment, counterparty, onClose }: { payment:LedgerPayment|null;counterparty:string;onClose:()=>void }) {
  const [bank,setBank]=useState<BankRow|null>(null),[linkedCount,setLinkedCount]=useState(0);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const sequence=useRef({value:0});
  const load=useCallback(async()=>{
    if(!payment)return;const request=++sequence.current.value;setLoading(true);setError("");
    try{const response=await apiFetch("/bank-reconciliation?target_type=VENDOR_PAYMENT&target_id="+payment.id+"&page_size=10");const data=await response.json();if(!response.ok)throw new Error(apiError(data,"Could not read reconciliation records."));if(!Array.isArray(data.transactions))throw new Error("Reconciliation records could not be read. Please retry.");if(request===sequence.current.value){const row=(data.transactions || [])[0];setLinkedCount(data.count??data.transactions.length);setBank(row?{...row,amount:String(row.amount)}:null);}}
    catch(e){if(request===sequence.current.value)setError(financialErrorMessage(e,"Could not read reconciliation records."));}
    finally{if(request===sequence.current.value)setLoading(false);}
  },[payment]);
  useEffect(()=>{const tracker=sequence.current;setBank(null);void load();return()=>{tracker.value++;};},[load]);
  return <Drawer open={Boolean(payment)} anchor="right" onClose={onClose} slotProps={{paper:{role:"dialog","aria-modal":true,"aria-label":"Transaction details",sx:{width:{xs:"100%",sm:580},maxWidth:"100%"}}}}>
    {payment&&<Box sx={{p:{xs:2,sm:3}}}><Stack direction="row" spacing={2} sx={{justifyContent:"space-between",alignItems:"flex-start",mb:2}}><Box><Typography variant="overline" color="text.secondary">Vendor payment · {payment.currency || "currency unverified"}</Typography><Typography component="h2" variant="h6">{counterparty || "Supplier not provided"}</Typography><Box sx={{my:1}}><Money value={payment.amount} currency={payment.currency||""} large/></Box><FinancialStatus status="RECORDED"/></Box><IconButton aria-label="Close transaction details" onClick={onClose}><X size={20}/></IconButton></Stack>
      <Alert severity="info" sx={{mb:2}}>This is an internal record of a payment. It does not confirm a gateway payment or bank settlement.</Alert>
      {!payment.source_account&&<Alert severity="warning" sx={{mb:2}} action={<Button component={NextLink} href={"/settlements?record_type=VENDOR_PAYMENT&record_id="+payment.id}>Verify source</Button>}>Bank account and source currency have not been verified.</Alert>}
      <DetailGroup title="Payment information" fields={{"Payment date":financialDate(payment.paid_at),"Method":payment.mode.replaceAll("_"," "),"Payment reference":<CopyReference value={payment.reference_number} label="payment reference"/>,"Internal payment ID":<CopyReference value={payment.id} label="payment ID"/>,"Record created":financialDate(payment.created_at,true),"Remarks":payment.remarks || "Not provided"}}/>
      <DetailGroup title="Invoice allocations" fields={Object.fromEntries(payment.allocations.map((allocation,index)=>[`Allocation ${index+1}`,<Stack key={allocation.invoice} spacing={0.5}><CopyReference value={allocation.invoice} label="invoice ID"/><Money value={allocation.amount}/></Stack>]))}/>
      <Box component="section" sx={{borderTop:"1px solid",borderColor:"divider",py:2}}><Typography component="h3" variant="subtitle2" sx={{mb:1}}>Bank reconciliation</Typography>
        {loading?<ContentSkeleton variant="form" rows={2} label="Reading reconciliation status"/>:error?<Alert severity="error" action={<Button color="inherit" onClick={()=>void load()}>Retry</Button>}>{error}</Alert>:bank?<><Typography variant="caption">{linkedCount} linked bank row(s){bank.group_id?" in a reviewed allocation group":""}.</Typography><FinancialStatus status={bank.status}/><DetailGroup title="Linked statement record" fields={{"Statement":bank.statement,"Statement date":financialDate(bank.date),"Bank reference":<CopyReference value={bank.reference} label="bank reference"/>,"Bank amount":<Money value={bank.amount} currency={bank.currency||""}/>,"Bank record ID":<CopyReference value={bank.id} label="bank record ID"/>}}/></>:<Typography variant="body2" color="text.secondary">No linked bank row was found for this payment across the imported statement records.</Typography>}
        <Link component={NextLink} href="/bank-reconciliation" sx={{display:"inline-block",mt:2}}>Open reconciliation center →</Link>
      </Box>
      <DetailGroup title="Gateway, settlement and adjustments" fields={{"Gateway identifier":"Not provided by the payment register","Settlement date":"Not provided","Gateway fees":"Not provided","Refund / reversal history":"Not available in this view"}}/>
    </Box>}
  </Drawer>;
}
