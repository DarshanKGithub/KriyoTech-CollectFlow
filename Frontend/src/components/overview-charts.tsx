"use client";

import NextLink from "next/link";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import { BarChart } from "@mui/x-charts/BarChart";
import { LineChart } from "@mui/x-charts/LineChart";
import { PieChart } from "@mui/x-charts/PieChart";
import { UiDetails, UiSummary } from "@/components/product-ui";
import { EmptyState } from "@/components/empty-state";
import type { ReactNode } from "react";

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
const issueColors = ["#c24145", "#d97706", "#7c5cad", "#256e93", "#438b79", "#64748b"];
const agingLabels: Record<string,string> = { NOT_OVERDUE: "Not overdue", DAYS_1_7: "1–7 days overdue", DAYS_8_30: "8–30 days overdue", DAYS_31_PLUS: "31+ days overdue", NO_DUE_DATE: "Due date missing" };

function ChartCard({ title, subtitle, metric, detail, href, children, data }: { title: string; subtitle: string; metric: ReactNode; detail: string; href?: string; children: ReactNode; data: { label: string; value: string }[] }) {
  return <Card variant="outlined" sx={{ minWidth: 0, height: "100%", borderRadius: 2 }}>
    <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack direction="row" spacing={2} sx={{ justifyContent: "space-between", alignItems: "flex-start" }}><Box><Typography component="h2" variant="subtitle1">{title}</Typography><Typography variant="caption" color="text.secondary">{subtitle}</Typography></Box>{href&&<Link component={NextLink} href={href} variant="caption" sx={{ whiteSpace: "nowrap" }}>Open workspace →</Link>}</Stack>
      <Box sx={{ mt: 2, mb: 1 }}><Typography component="div" variant="h4">{metric}</Typography><Typography variant="caption" color="text.secondary">{detail}</Typography></Box>
      {children}
      {data.length > 0 && <UiDetails><UiSummary>View chart data</UiSummary><Box sx={{ maxHeight: 240, overflow: "auto" }}><Table size="small" aria-label={`${title} data`}><TableHead><TableRow><TableCell>Category / date</TableCell><TableCell align="right">Value</TableCell></TableRow></TableHead><TableBody>{data.map(row => <TableRow key={row.label}><TableCell>{row.label}</TableCell><TableCell align="right">{row.value}</TableCell></TableRow>)}</TableBody></Table></Box></UiDetails>}
    </CardContent>
  </Card>;
}

export function OverviewCharts({ byStatus, exceptions, analytics, allowedPaths }: { byStatus: Record<string,number>; exceptions: { code: string; count: number }[]; analytics?: DashboardAnalytics; allowedPaths?: string[] }) {
  const link=(path:string)=>!allowedPaths || allowedPaths.includes(path) ? path : undefined;
  const stages = [
    { label: "Processing", statuses: ["UPLOADED", "EXTRACTING"], color: "#32889b" },
    { label: "Needs review", statuses: ["REVIEW_REQUIRED"], color: "#d28b20" },
    { label: "Blocked", statuses: ["EXTRACTION_FAILED", "EXCEPTION"], color: "#c24145" },
    { label: "Matching / approval", statuses: ["MATCHED", "APPROVAL_PENDING", "APPROVED"], color: "#7761a7" },
    { label: "Payment ready", statuses: ["PAYMENT_READY"], color: "#17634f" },
    { label: "Exported", statuses: ["EXPORTED"], color: "#47876e" },
    { label: "Rejected", statuses: ["REJECTED"], color: "#64748b" },
  ].map(stage => ({ ...stage, count: stage.statuses.reduce((sum,status) => sum + (byStatus[status] || 0), 0) }));
  const total = Object.values(byStatus).reduce((sum,count) => sum + count, 0);
  const issues = exceptions.filter(item => item.count > 0).sort((a,b) => b.count-a.count);
  const issueTotal = issues.reduce((sum,item) => sum + item.count, 0);
  const uploads = analytics?.daily_uploads || [];
  const uploadTotal = uploads.reduce((sum,item) => sum + item.count, 0);
  const previous = analytics?.previous_uploads || 0;
  const change = previous > 0 ? `${uploadTotal >= previous ? "+" : ""}${Math.round((uploadTotal-previous)/previous*100)}% vs previous ${analytics?.days} days` : "No uploads in the previous comparison period";
  const aging = analytics?.payable_aging;
  const outstanding = aging?.reduce((sum,item) => sum + Number(item.amount), 0) || 0;
  const overdue = aging?.filter(item=>!["NOT_OVERDUE","NO_DUE_DATE"].includes(item.bucket)).reduce((sum,item)=>sum+Number(item.amount),0) || 0;
  const snapshot = analytics ? `Snapshot as of ${new Date(analytics.as_of).toLocaleString("en-IN")}` : "Current workspace snapshot";
  return <Box component="section" aria-label="Workspace analytics" sx={{ mt: 3 }}>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: 2 }}><Typography variant="caption" color="text.secondary">Real workspace activity and current workloads</Typography><Typography variant="caption" color="text.secondary">{snapshot}</Typography></Stack>
    <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "minmax(0,1fr)", xl: "repeat(2,minmax(0,1fr))" } }}>
      <ChartCard title="Daily invoice uploads" subtitle={analytics ? `${date(analytics.start_date)} – ${date(analytics.end_date)} · ${analytics.days} calendar days` : "Upload history"} metric={`${number(uploadTotal)} invoices`} detail="Invoices received during the selected period" href={link("/invoices")} data={uploads.map(item=>({label:item.date,value:`${item.count} invoices`}))}>
        {analytics && uploadTotal > 0 ? <><Chip size="small" label={change} variant="outlined" sx={{ my: 1 }} /><Box role="img" aria-label={`${uploadTotal} invoices uploaded over ${analytics.days} days. Exact daily counts are in the chart data table.`}><LineChart height={280} xAxis={[{ scaleType:"point", data:uploads.map(item=>item.date), valueFormatter:(value:string)=>date(value), tickLabelInterval:(_,index)=>index % Math.max(1,Math.floor(uploads.length/6)) === 0 }]} yAxis={[{ min:0, tickMinStep:1, label:"Invoices" }]} series={[{ data:uploads.map(item=>item.count), label:"Invoices uploaded", color:"#17634f", area:true, showMark:uploads.length<=7, curve:"linear", valueFormatter:value=>`${value || 0} invoices` }]} grid={{horizontal:true}} hideLegend skipAnimation margin={{left:8,right:20,top:15,bottom:12}} /></Box></> : <EmptyState title={analytics ? "No uploads in this period" : "Upload history unavailable"} description={analytics ? "Choose a wider period or upload an invoice to start tracking daily activity." : "Refresh the dashboard to request current analytics."} />}
      </ChartCard>
      <ChartCard title="Current invoice workflow" subtitle="All invoices · current status" metric={`${number(total)} invoices`} detail="Invoices grouped by their current processing stage" href={link("/invoices")} data={stages.map(stage=>({label:stage.label,value:`${stage.count} invoices`}))}>
        {total > 0 ? <Box role="img" aria-label={`Workflow: ${stages.map(stage=>`${stage.label}: ${stage.count}`).join(", ")}`}><BarChart layout="horizontal" height={330} yAxis={[{scaleType:"band",data:stages.map(stage=>stage.label),width:145,colorMap:{type:"ordinal",colors:stages.map(stage=>stage.color)}}]} xAxis={[{tickMinStep:1,label:"Invoices",min:0}]} series={[{data:stages.map(stage=>stage.count),label:"Invoices",color:"#17634f",valueFormatter:value=>`${value || 0} invoices`}]} borderRadius={5} grid={{vertical:true}} hideLegend skipAnimation margin={{top:12,right:24,bottom:8}}/></Box> : <EmptyState description="Upload an invoice to see where work is waiting." />}
      </ChartCard>
      {aging && <ChartCard title="Approved balances by due date" subtitle="Current outstanding amounts · INR" metric={compactMoney(outstanding)} detail={`${money(overdue)} overdue · excludes cancelled and fully paid invoices`} href={link("/payments")} data={aging.map(item=>({label:agingLabels[item.bucket] || item.bucket,value:`${money(Number(item.amount))} · ${item.count} invoices`}))}>
        {outstanding > 0 ? <Box role="img" aria-label={`Approved invoice balances: ${aging.map(item=>`${agingLabels[item.bucket]}: ${money(Number(item.amount))}`).join(", ")}`}><BarChart height={330} layout="horizontal" yAxis={[{scaleType:"band",data:aging.map(item=>agingLabels[item.bucket]),width:145,colorMap:{type:"ordinal",colors:["#47876e","#d28b20","#d36c35","#c24145","#64748b"]}}]} xAxis={[{min:0,valueFormatter:(value:number)=>compactMoney(value)}]} series={[{data:aging.map(item=>Number(item.amount)),label:"Outstanding balance",valueFormatter:value=>money(value || 0)}]} borderRadius={5} grid={{vertical:true}} hideLegend skipAnimation margin={{top:16,right:24,bottom:8}} /></Box> : <EmptyState title="No approved balance outstanding" description="Approved invoices with unpaid balances appear here, grouped by their due dates." />}
        <Typography variant="caption" color="text.secondary" sx={{display:"block",mb:2}}>Remaining balance = recorded invoice total minus payment allocations. Due today is not overdue. Missing due dates are shown separately.</Typography>
      </ChartCard>}
      <ChartCard title="What is blocking invoices?" subtitle="Open or assigned exceptions · current snapshot" metric={`${number(issueTotal)} open issues`} detail={issues[0] ? `Most frequent: ${title(issues[0].code)} (${issues[0].count})` : "No unresolved exceptions"} href={link("/exceptions")} data={issues.map(item=>({label:title(item.code),value:`${item.count} issues`}))}>
        {issueTotal > 0 ? <><Box sx={{position:"relative"}} role="img" aria-label={`Exception types: ${issues.map(item=>`${title(item.code)}: ${item.count}`).join(", ")}`}><PieChart height={245} series={[{innerRadius:68,outerRadius:100,paddingAngle:3,cornerRadius:4,data:issues.map((item,index)=>({id:item.code,value:item.count,label:title(item.code),color:issueColors[index%issueColors.length]})),valueFormatter:item=>`${item.value} issues (${Math.round(item.value/issueTotal*100)}%)`}]} hideLegend skipAnimation margin={{left:12,right:12,top:12,bottom:12}}/><Box sx={{position:"absolute",inset:0,display:"flex",alignItems:"center",justifyContent:"center",flexDirection:"column",pointerEvents:"none"}}><Typography variant="h4">{issueTotal}</Typography><Typography variant="caption" color="text.secondary">Open issues</Typography></Box></Box><Box sx={{display:"grid",gap:1,mb:2,gridTemplateColumns:{xs:"1fr",sm:"1fr 1fr"}}}>{issues.map((item,index)=><Stack key={item.code} direction="row" spacing={1} sx={{alignItems:"center",minWidth:0}}><Box sx={{width:9,height:9,borderRadius:"50%",bgcolor:issueColors[index%issueColors.length],flexShrink:0}}/><Typography variant="caption" sx={{flex:1}}>{title(item.code)}</Typography><Typography variant="caption" sx={{fontWeight:700}}>{item.count}</Typography></Stack>)}</Box></> : <EmptyState title="No open exceptions" description="Matching and extraction issues will appear here when they need review." />}
      </ChartCard>
    </Box>
  </Box>;
}
