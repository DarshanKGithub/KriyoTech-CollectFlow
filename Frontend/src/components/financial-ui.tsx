"use client";

import React, { type ReactNode } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { CheckCircle2, Clock3, CircleAlert, Link2, Copy, CircleX, RotateCcw } from "lucide-react";
import { financialDate, formatMoney, reconciliationLabels } from "@/lib/finance";
import { showNotice } from "@/components/product-dialogs";

export { financeTokens } from "@/lib/finance-design";
export function Money({ value, large = false, currency = "INR" }: { value:string;large?:boolean;currency?:string }) { return <Typography component="span" sx={{fontVariantNumeric:"tabular-nums",fontWeight:700,fontSize:large?{xs:22,sm:28}:"inherit",whiteSpace:"normal",overflowWrap:"anywhere",letterSpacing:large?"-0.025em":undefined}}>{formatMoney(value,currency)}</Typography>; }
export function FinancialHeader({ eyebrow, title, description, action }: { eyebrow:string;title:string;description:string;action?:ReactNode }) {
  return <Stack direction={{xs:"column",sm:"row"}} spacing={2} sx={{justifyContent:"space-between",alignItems:{sm:"flex-start"},mb:3}}><Box sx={{maxWidth:720,minWidth:0,flex:1}}><Typography variant="overline" color="primary" sx={{fontSize:10,fontWeight:700,letterSpacing:1.4}}>{eyebrow}</Typography><Typography component="h1" variant="h4" sx={{mt:0.5,fontSize:{xs:24,sm:28}}}>{title}</Typography><Typography variant="body2" color="text.secondary" sx={{mt:1}}>{description}</Typography></Box>{action&&<Box sx={{flexShrink:0}}>{action}</Box>}</Stack>;
}
export function FinancialMetric({ label, value, detail, icon, tone="primary" }: { label:string;value:ReactNode;detail:string;icon?:ReactNode;tone?:"primary"|"warning"|"success" }) {
  return <Paper variant="outlined" sx={{p:{xs:2,md:2.5},minWidth:0,borderRadius:2,borderColor:"divider",bgcolor:"background.paper",color:"text.primary",boxShadow:"none",position:"relative",overflow:"hidden"}}>
    <Stack direction="row" sx={{alignItems:"center",justifyContent:"space-between",gap:1}}><Typography variant="body2" color="text.secondary" sx={{fontWeight:500}}>{label}</Typography>{icon&&<Box sx={{width:34,height:34,display:"grid",placeItems:"center",borderRadius:1.5,bgcolor:"action.hover",color:`${tone}.main`,flexShrink:0}}>{icon}</Box>}</Stack>
    <Typography component="div" sx={{mt:1.5,mb:0.75,fontSize:32,lineHeight:1.15,fontWeight:600,letterSpacing:"-0.04em",fontVariantNumeric:"tabular-nums",color:"text.primary"}}>{value}</Typography>
    <Typography variant="caption" color="text.secondary" sx={{display:"block",lineHeight:1.6}}>{detail}</Typography>
  </Paper>;
}
export function FinancialStatus({ status }: { status:string }) {
  const state:Record<string,{color:"success"|"warning"|"error"|"info"|"default";icon:typeof Clock3;label?:string}>={
    UNMATCHED:{color:"warning",icon:CircleAlert},MATCHED:{color:"info",icon:Link2},RECONCILED:{color:"success",icon:CheckCircle2},DUPLICATE:{color:"error",icon:Copy},
    RECORDED:{color:"info",icon:CheckCircle2,label:"Payment recorded"},PENDING:{color:"warning",icon:Clock3},PROCESSING:{color:"info",icon:Clock3},COMPLETED:{color:"success",icon:CheckCircle2},FAILED:{color:"error",icon:CircleX},REFUNDED:{color:"default",icon:RotateCcw},REVERSED:{color:"default",icon:RotateCcw},
  };
  const info=state[status]||{color:"default" as const,icon:Clock3};const Icon=info.icon;
  return <Chip size="small" variant="outlined" color={info.color} icon={<Icon size={14}/>} label={reconciliationLabels[status]||info.label||status.replaceAll("_"," ").toLowerCase()} sx={{maxWidth:"100%",height:"auto",minHeight:26,"& .MuiChip-label":{whiteSpace:"normal",py:0.4}}}/>;
}
export function CopyReference({ value, label="Reference" }: { value?:string|null;label?:string }) { return <Stack direction="row" spacing={0.5} sx={{alignItems:"center",minWidth:0}}><Typography component="span" variant="body2" sx={{fontFamily:"monospace",overflowWrap:"anywhere",minWidth:0}}>{value||"Not provided"}</Typography>{value&&<Tooltip title={`Copy ${label}`}><IconButton size="small" aria-label={`Copy ${label}`} onClick={async()=>{try{await navigator.clipboard.writeText(value);showNotice(`${label} copied.`,"success");}catch{showNotice("Could not copy. Select the reference and copy it manually.");}}}><Copy size={14}/></IconButton></Tooltip>}</Stack>; }
export function DetailGroup({ title, fields }: { title:string;fields:Record<string,ReactNode> }) { return <Box component="section" sx={{py:2,borderTop:"1px solid",borderColor:"divider"}}><Typography component="h3" variant="subtitle2" sx={{mb:2}}>{title}</Typography><Box component="dl" sx={{m:0,display:"grid",gap:1.5,gridTemplateColumns:{xs:"1fr",sm:"minmax(100px,0.8fr) minmax(0,1.2fr)"}}}>{Object.entries(fields).map(([key,value])=><React.Fragment key={key}><Typography component="dt" variant="caption" color="text.secondary">{key}</Typography><Box component="dd" sx={{m:0,overflowWrap:"anywhere",fontSize:13}}>{value??"Not provided"}</Box></React.Fragment>)}</Box></Box>; }
export { financialDate };

