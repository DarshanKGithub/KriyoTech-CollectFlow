"use client";

import NextLink from "next/link";
import { useTheme } from "@mui/material/styles";
import useMediaQuery from "@mui/material/useMediaQuery";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import Link from "@mui/material/Link";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import { BarChart } from "@mui/x-charts/BarChart";


import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import { useId, useState } from "react";

import type { ReactNode } from "react";
import { decimalAmount, formatMoney, minorUnits } from "@/lib/finance";

export type DashboardAnalytics = {
  days: number; start_date: string; end_date: string; as_of: string;
  daily_uploads: { date: string; count: number }[]; previous_uploads: number;
  payable_aging?: { bucket: string; amount: string; count: number }[];
};
const title = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase());
const number = (value: number) => new Intl.NumberFormat("en-IN").format(value);
const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(value);
const compactMoney = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1 }).format(value);
const date = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const issueLabels: Record<string, string> = { MANUAL_REVIEW: "Manual review needed", VENDOR_NOT_APPROVED: "Supplier needs approval", QTY_OVER_INVOICE: "Quantity mismatch", MISSING_GRN: "Goods receipt missing" };
const agingLabels: Record<string,string> = { NOT_OVERDUE: "Not overdue", DAYS_1_7: "1–7 days overdue", DAYS_8_30: "8–30 days overdue", DAYS_31_PLUS: "31+ days overdue", NO_DUE_DATE: "Due date missing" };

function ChartCard({ title, subtitle, metric, detail, href, children, data, wide = false, control, compact = false }: { title: string; subtitle?: string; metric?: ReactNode; detail?: string; href?: string; wide?: boolean; compact?: boolean; control?: ReactNode; children: ReactNode; data: { label: string; value: string }[] }) {
  const [open, setOpen] = useState(false);
  const titleId = useId();
  return <Card variant="outlined" sx={{ minWidth: 0, height: "100%", ...(compact && { flex: 1, minHeight: 0 }), borderRadius: 2, gridColumn: wide ? "1 / -1" : undefined }}>
    <CardContent sx={{ p: 1.75, height: "100%", display: "flex", flexDirection: "column", "&:last-child": { pb: 1.75 } }}>
      <Stack direction="row" useFlexGap sx={{ minHeight: 29, justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: .75 }}><Box><Typography component="h2" variant="body2" sx={{ fontWeight: 700, fontSize: compact ? 14 : 16 }}>{title}</Typography>{subtitle && <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.3, fontSize: compact ? 12 : 13 }}>{subtitle}</Typography>}</Box>{control}</Stack>
      {(metric || detail) && <Box sx={{ mt: .25, mb: .25, textAlign: "left" }}><Typography component="div" sx={{ fontSize: compact ? 19 : 25, lineHeight: 1.15, fontWeight: 700 }}>{metric}</Typography>{detail && <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.3, fontSize: compact ? 12 : 13 }}>{detail}</Typography>}</Box>}
      {children}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mt: "auto" }}>
      {data.length > 0 && <Button size="small" aria-label={`View ${title.toLowerCase()} data`} onClick={() => setOpen(true)} sx={{ py: 0, minHeight: 22 }}>View data</Button>}
      {href&&<Link component={NextLink} href={href} variant="caption" aria-label={`Open workspace for ${title.toLowerCase()}`} sx={{ whiteSpace: "nowrap" }}>{href === "/payments" ? "Go to payments" : href === "/exceptions" ? "Go to exceptions" : "Go to invoices"} →</Link>}
      </Stack>
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm" aria-labelledby={titleId}>
        <DialogTitle id={titleId}>{title}</DialogTitle>
        <DialogContent dividers>
          <Table size="small" aria-label={`${title} data`}>
            <TableHead><TableRow><TableCell>Category / date</TableCell><TableCell align="right">Value</TableCell></TableRow></TableHead>
            <TableBody>{data.map(row => <TableRow key={row.label}><TableCell>{row.label}</TableCell><TableCell align="right">{row.value}</TableCell></TableRow>)}</TableBody>
          </Table>
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>Close</Button></DialogActions>
      </Dialog>
    </CardContent>
  </Card>;
}

export function OverviewCharts({ byStatus, exceptions, analytics, allowedPaths, statusCards, uploadRange, fillWindow }: { byStatus: Record<string,number>; exceptions: { code: string; count: number }[]; analytics?: DashboardAnalytics; allowedPaths?: string[]; statusCards: ReactNode; uploadRange: ReactNode; fillWindow: boolean }) {
  const theme = useTheme();
  const roomy = useMediaQuery("(min-width: 1200px) and (min-height: 850px)");

  const tickLabelStyle = { fontSize: roomy ? 14 : 12 };
  const plotSize = fillWindow ? { flex: 1, minHeight: 0, minWidth: 0 } : { height: 118, minWidth: 0 };


  const primary = theme.palette.primary.main;
  const link=(path:string)=>!allowedPaths || allowedPaths.includes(path) ? path : undefined;
  const stages = [
    { label: "Processing", statuses: ["UPLOADED", "EXTRACTING"], color: "#607D57" },
    { label: "Needs review", statuses: ["REVIEW_REQUIRED"], color: "#d28b20" },
    { label: "Blocked", statuses: ["EXTRACTION_FAILED", "EXCEPTION"], color: "#c24145" },
    { label: "Match or approve", statuses: ["MATCHED", "APPROVAL_PENDING", "APPROVED"], color: "#786B45" },
    { label: "Ready to pay", statuses: ["PAYMENT_READY"], color: primary },
    { label: "Exported", statuses: ["EXPORTED"], color: "#607D57" },
    { label: "Rejected", statuses: ["REJECTED"], color: "#64705F" },
  ].map(stage => ({ ...stage, count: stage.statuses.reduce((sum,status) => sum + (byStatus[status] || 0), 0) }));
  const total = Object.values(byStatus).reduce((sum,count) => sum + count, 0);
  const issues = exceptions.filter(item => item.count > 0).sort((a,b) => b.count-a.count);
  const issueTotal = issues.reduce((sum,item) => sum + item.count, 0);
  const uploads = analytics?.daily_uploads || [];
  const uploadTotal = uploads.reduce((sum,item) => sum + item.count, 0);
  const previous = analytics?.previous_uploads || 0;
  const change = previous > 0 ? `${uploadTotal >= previous ? "+" : ""}${Math.round((uploadTotal-previous)/previous*100)}% vs previous ${analytics?.days} days` : undefined;
  const aging = analytics?.payable_aging;
  const outstanding = aging?.reduce((sum, item) => sum + minorUnits(item.amount), 0n) ?? 0n;
  const overdue = aging?.filter(item => !["NOT_OVERDUE", "NO_DUE_DATE"].includes(item.bucket)).reduce((sum, item) => sum + minorUnits(item.amount), 0n) ?? 0n;
  return <>
    <Stack spacing={1.25} sx={{ minWidth: 0, minHeight: 0, alignSelf: fillWindow ? "stretch" : "start", "& > :not(:last-child)": { flexShrink: 0 } }}>
      {statusCards}
      <ChartCard compact title="Top invoice issues" metric={`${issueTotal} open issues`} href={link("/exceptions")} data={issues.map(item => ({ label: issueLabels[item.code] ?? title(item.code), value: String(item.count) }))}>
        {issueTotal > 0 ? <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, mt: 1, flex: fillWindow ? 1 : undefined, minHeight: 0, overflowY: fillWindow ? "auto" : "visible" }}>
          {(fillWindow ? issues : issues.slice(0, 3)).map(item => <Box component="li" key={item.code} sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, py: .65, borderBottom: "1px solid", borderColor: "divider" }}>
            <Typography variant="body2">{issueLabels[item.code] ?? title(item.code)}</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>{item.count}</Typography>
          </Box>)}
          {!fillWindow && issues.length > 3 && <Typography component="li" variant="caption" color="text.secondary" sx={{ mt: .75 }}>More issue types in View data</Typography>}
        </Box> : <Typography variant="body2" color="text.secondary">No open invoice issues.</Typography>}
      </ChartCard>
    </Stack>
    <Box sx={{ minWidth: 0, minHeight: 0, display: "grid", gap: 1.25,
      gridTemplateColumns: { xs: "minmax(0,1fr)", sm: aging ? "minmax(0, 1fr) minmax(0, 1.35fr)" : "minmax(0,1fr)" },
      ...(fillWindow ? { gridTemplateRows: "minmax(0, 1fr) minmax(0, 1fr)" } : {}),
    }}>
      <ChartCard title="Invoices received" control={uploadRange} wide subtitle={analytics ? `${date(analytics.start_date)} – ${date(analytics.end_date)} · ${analytics.days} calendar days` : "Upload history"} metric={`${number(uploadTotal)} invoices`} detail={analytics ? change : ""} href={link("/invoices")} data={uploads.map(item=>({label:item.date,value:`${item.count} invoices`}))}>
        {analytics && uploadTotal > 0 ? <><Box sx={plotSize} role="img" aria-label={`${uploadTotal} invoices uploaded over ${analytics.days} days. Exact daily counts are in the chart data table.`}><BarChart borderRadius={3} xAxis={[{ scaleType:"band", tickLabelStyle, height: 32, data:uploads.map(item=>item.date), valueFormatter:(value:string)=>date(value), tickInterval:uploads.filter((_,index)=>index % Math.max(1,Math.floor(uploads.length/4)) === 0).map(item=>item.date) }]} yAxis={[{ min:0, tickMinStep:1, tickLabelStyle, width:34 }]} series={[{ data:uploads.map(item=>item.count), label:"Invoices uploaded", color:primary, valueFormatter:value=>`${value || 0} invoices` }]} grid={{horizontal:true}} hideLegend skipAnimation margin={{left:8,right:20,top:5,bottom:2}} /></Box></> : <Typography variant="caption" color="text.secondary">{analytics ? "No uploads in this period" : "Upload history unavailable"}</Typography>}
      </ChartCard>
      <ChartCard title="Invoices by status" metric={`${number(total)} invoices`} href={link("/invoices")} data={stages.map(stage=>({label:stage.label,value:`${stage.count} invoices`}))}>
        {total > 0 ? <Box sx={plotSize} role="img" aria-label={`Workflow: ${stages.map(stage=>`${stage.label}: ${stage.count}`).join(", ")}`}><BarChart layout="horizontal" yAxis={[{scaleType:"band",data:stages.map(stage=>stage.label),width:roomy ? 136 : 116,tickLabelStyle,colorMap:{type:"ordinal",colors:stages.map(stage=>stage.color)}}]} xAxis={[{tickMinStep:1,min:0,tickLabelStyle,height:32}]} series={[{data:stages.map(stage=>stage.count),label:"Invoices",color:primary,valueFormatter:value=>`${value || 0} invoices`}]} borderRadius={5} grid={{vertical:true}} hideLegend skipAnimation margin={{top:3,right:12,bottom:2}}/></Box> : <Typography variant="caption" color="text.secondary">No invoices yet.</Typography>}
      </ChartCard>
      {aging && <ChartCard title="Supplier balances" metric={formatMoney(decimalAmount(outstanding))} detail={`${formatMoney(decimalAmount(overdue))} overdue`} href={link("/payments")} data={aging.map(item=>({label:agingLabels[item.bucket] || item.bucket,value:`${formatMoney(item.amount)} · ${item.count} invoices`}))}>
        {outstanding > 0n ? <Box sx={plotSize} role="img" aria-label={`Approved invoice balances: ${aging.map(item=>`${agingLabels[item.bucket]}: ${formatMoney(item.amount)}`).join(", ")}`}><BarChart layout="horizontal" yAxis={[{scaleType:"band",data:aging.map(item=>agingLabels[item.bucket]),width:roomy ? 154 : 118,tickLabelStyle,valueFormatter:(label:string,context)=>context.location === "tick" && !roomy ? label.replace(" days overdue", "d overdue") : label,colorMap:{type:"ordinal",colors:["#607D57","#d28b20","#d36c35","#c24145","#64705F"]}}]} xAxis={[{min:0,tickNumber:5,tickLabelStyle,height:32,valueFormatter:(value:number)=>compactMoney(value)}]} series={[{data:aging.map(item=>Number(item.amount)),label:"Outstanding balance",valueFormatter:value=>money(value || 0)}]} borderRadius={5} grid={{vertical:true}} hideLegend skipAnimation margin={{top:3,right:42,bottom:2}} /></Box> : <Typography variant="caption" color="text.secondary">No outstanding balances.</Typography>}
      </ChartCard>}
    </Box>
  </>;
}
