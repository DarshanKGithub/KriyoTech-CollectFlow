"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { RefreshCw } from "lucide-react";
import { AppLink } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";

type LeakageItem = {
  id: string; issue: string; severity: string; message: string; next_action: string;
  trip_id: string; trip_number: string; vehicle: string; customer: string; order_number: string;
  expected_amount?: string | null; approved_trip_revenue?: string; invoice_number?: string | null;
  invoice_amount?: string; paid_amount?: string; outstanding_amount?: string; collection_amount?: string;
  due_date?: string; reasons: string[];
};
type Report = { as_of: string; delivered_trip_count: number; exception_count: number; potential_exposure: string; counts: Record<string, number>; items: LeakageItem[]; note: string };
const money = (value?: string | null) => value == null ? "—" : `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function FleetRevenueLeakagePage() {
  const [report, setReport] = useState<Report | null>(null); const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false); const [error, setError] = useState("");
  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const response = await apiFetch("/fleet/revenue-leakage"); const data = await response.json();
      if (!response.ok) throw new Error(data.error || data.detail || "Could not load revenue leakage review.");
      setReport(data); setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load revenue leakage review."); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return <main className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" }, gap: 2 }}>
      <div><Typography variant="overline" color="primary">Fleet · Finance controls</Typography><Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>Revenue leakage review</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 1, maxWidth: 760 }}>Find delivered trips without invoices, freight amount variances, overdue customer balances, and bank collections that still need reconciliation.</Typography></div>
      <Button variant="outlined" onClick={() => void load()} disabled={refreshing} startIcon={<RefreshCw size={16}/>}>Refresh</Button>
    </Stack>
    {error && <Alert severity="error" action={<Button color="inherit" onClick={() => void load()}>Retry</Button>}>{error}</Alert>}
    {loading && <LinearProgress aria-label="Loading revenue leakage report"/>}
    {report && <>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        {[ ["Delivered trips reviewed", String(report.delivered_trip_count)], ["Items for review", String(report.exception_count)], ["Unbilled / overdue exposure", money(report.potential_exposure)] ].map(([label, value]) => <Paper key={label} variant="outlined" sx={{ p: 2.5, flex: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h5" sx={{ mt: 1, fontWeight: 700 }}>{value}</Typography></Paper>)}
      </Stack>
      <Alert severity="info">{report.note} · As of {report.as_of}</Alert>
      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        <Stack direction="row" spacing={1} sx={{ p: 2, flexWrap: "wrap", borderBottom: "1px solid", borderColor: "divider" }}>
          {Object.entries(report.counts).map(([kind, count]) => <Chip key={kind} size="small" variant="outlined" label={`${kind.replaceAll("_", " ").toLowerCase()} · ${count}`}/>)}
          {!Object.keys(report.counts).length && <Typography variant="body2" color="text.secondary">No revenue exceptions found for delivered trips.</Typography>}
        </Stack>
        {report.items.length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[1050px] text-left text-sm"><thead><tr className="bg-slate-50 text-xs text-slate-500">{["Issue", "Customer / order", "Trip / truck", "Expected", "Recorded", "Evidence & next step"].map(label => <th key={label} className="p-3 font-semibold">{label}</th>)}</tr></thead><tbody>{report.items.map(item => <tr key={item.id} className="border-t border-line align-top"><td className="p-3"><Chip size="small" color={item.severity === "HIGH" ? "error" : "warning"} variant="outlined" label={item.issue.replaceAll("_", " ").toLowerCase()}/></td><td className="p-3"><div className="font-semibold">{item.customer}</div><div className="text-xs text-slate-500">{item.order_number}{item.invoice_number ? ` · ${item.invoice_number}` : ""}</div></td><td className="p-3"><div className="font-semibold">{item.trip_number}</div><div className="text-xs text-slate-500">{item.vehicle}</div></td><td className="p-3">{money(item.expected_amount)}</td><td className="p-3">{item.outstanding_amount ? <><div>Outstanding {money(item.outstanding_amount)}</div><div className="text-xs text-slate-500">Paid {money(item.paid_amount)}</div></> : item.approved_trip_revenue ? money(item.approved_trip_revenue) : item.invoice_amount ? money(item.invoice_amount) : money(item.collection_amount)}</td><td className="max-w-[390px] p-3"><div>{item.message}</div>{item.due_date && <div className="mt-1 text-xs text-rose-700">Due {item.due_date}</div>}{item.reasons?.map(reason => <div key={reason} className="mt-1 text-xs text-slate-500">• {reason}</div>)}<div className="mt-2 text-xs font-semibold text-forest">{item.next_action}</div></td></tr>)}</tbody></table></div>}
        {report.items.length === 0 && <div className="p-8 text-center"><Typography variant="body2" color="text.secondary">No delivered freight issues need review right now.</Typography></div>}
      </Paper>
    </>}
    <Stack direction="row" spacing={2}><AppLink href="/fleet/customer-invoices" className="text-sm font-semibold text-forest">Customer invoices</AppLink><AppLink href="/bank-reconciliation" className="text-sm font-semibold text-forest">Bank reconciliation</AppLink></Stack>
  </main>;
}
