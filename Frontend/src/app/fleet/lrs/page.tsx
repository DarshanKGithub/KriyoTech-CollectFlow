"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControl, InputAdornment, InputLabel, MenuItem, Select, TextField, Typography } from "@mui/material";
import { FilePlus2, Printer, Search, Truck } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Order = { id: string; order_number: string; customer: { id: string; name: string }; origin: string; destination: string; cargo_description: string; agreed_amount: string | null; status: string };
type LorryReceipt = {
  id: string; lr_number: string; lr_date: string; status: "ISSUED" | "CANCELLED"; order_id: string; order_number: string;
  customer: string; origin: string; destination: string; trip_number: string | null; vehicle: string | null; driver: string | null;
  consignor_name: string; consignor_address: string; consignee_name: string; consignee_address: string;
  goods_description: string; package_count: number; weight_kg: string | null; freight_amount: string;
  payment_type: string; eway_bill_number: string; invoice_reference: string; delivery_instructions: string; cancellation_reason: string;
};

const inputSx = { "& .MuiInputBase-root": { borderRadius: 1.5 }, "& .MuiFormLabel-root": { fontSize: 14 } };
const paymentLabels: Record<string, string> = { TO_PAY: "To Pay", PAID: "Paid", TO_BE_BILLED: "To Be Billed" };

export default function LorryReceiptsPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [receipts, setReceipts] = useState<LorryReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [preview, setPreview] = useState<LorryReceipt | null>(null);
  const [cancelTarget, setCancelTarget] = useState<LorryReceipt | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [orderResponse, lrResponse] = await Promise.all([apiFetch("/fleet/orders"), apiFetch("/fleet/lorry-receipts")]);
      const [orderData, lrData] = await Promise.all([orderResponse.json(), lrResponse.json()]);
      if (!orderResponse.ok || !lrResponse.ok) throw new Error(lrData?.error || orderData?.error || "Could not load lorry receipts.");
      setOrders(Array.isArray(orderData) ? orderData : []);
      setReceipts(Array.isArray(lrData) ? lrData : []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load lorry receipts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return receipts;
    return receipts.filter(item => [item.lr_number, item.order_number, item.customer, item.consignor_name, item.consignee_name, item.eway_bill_number].some(value => value.toLowerCase().includes(needle)));
  }, [receipts, search]);

  async function createReceipt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(""); setNotice("");
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries());
    for (const key of ["consignor_address", "consignee_address", "weight_kg", "eway_bill_number", "invoice_reference", "delivery_instructions"])
      if (!values[key]) delete values[key];
    try {
      const response = await apiFetch("/fleet/lorry-receipts", { method: "POST", body: JSON.stringify(values) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data?.error === "string" ? data.error : Object.values(data || {}).flat().join(" ") || "Could not issue the lorry receipt.");
      setReceipts(current => [data as LorryReceipt, ...current]);
      setPreview(data as LorryReceipt);
      setNotice(`Lorry receipt ${data.lr_number} issued.`);
      form.reset(); setShowForm(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not issue the lorry receipt.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelReceipt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!cancelTarget) return;
    setBusy(true); setError("");
    const reason = String(new FormData(event.currentTarget).get("reason") || "").trim();
    try {
      const response = await apiFetch(`/fleet/lorry-receipts/${cancelTarget.id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error || "Could not cancel the lorry receipt.");
      setReceipts(current => current.map(item => item.id === cancelTarget.id ? { ...item, status: "CANCELLED", cancellation_reason: reason } : item));
      if (preview?.id === cancelTarget.id) setPreview({ ...preview, status: "CANCELLED", cancellation_reason: reason });
      setNotice(`Lorry receipt ${cancelTarget.lr_number} cancelled and recorded in the audit log.`);
      setCancelTarget(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not cancel the lorry receipt.");
    } finally {
      setBusy(false);
    }
  }

  return <Box component="main" sx={{ width: "100%", minWidth: 0, px: { xs: 2, sm: 3, lg: 4 }, py: { xs: 2.5, sm: 3.5 } }}>
    <Box sx={{ maxWidth: 1500, mx: "auto" }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 2, mb: 3 }}>
        <Box><Typography variant="overline" color="primary.main" sx={{ fontWeight: 700, letterSpacing: ".12em" }}>Transport operations</Typography><Typography component="h1" sx={{ fontSize: { xs: 25, sm: 30 }, lineHeight: 1.2, fontWeight: 700, letterSpacing: "-.035em" }}>Lorry receipts</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .6 }}>Issue, review, and print consignment documents linked to transport orders.</Typography></Box>
        <Button disableElevation={false} variant="contained" startIcon={<FilePlus2 size={16}/>} onClick={() => setShowForm(value => !value)}>{showForm ? "Close form" : "Issue lorry receipt"}</Button>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError("")}>{error}</Alert>}
      {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice("")}>{notice}</Alert>}

      {showForm && <Box component="form" onSubmit={createReceipt} sx={{ mb: 3, p: { xs: 2, sm: 3 }, border: "1px solid", borderColor: "divider", borderRadius: 2.5, bgcolor: "background.paper" }}>
        <Typography component="h2" variant="h6" sx={{ fontWeight: 650 }}>Receipt details</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .4, mb: 2.5 }}>A receipt number is assigned when you issue this form.</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))", xl: "repeat(3,minmax(0,1fr))" }, gap: 2 }}>
          <FormControl required size="small" sx={inputSx}><InputLabel id="lr-order">Transport order</InputLabel><Select labelId="lr-order" name="order_id" label="Transport order" defaultValue=""><MenuItem value="" disabled>Select an order</MenuItem>{orders.filter(order => order.status !== "CANCELLED").map(order => <MenuItem key={order.id} value={order.id}>{order.order_number} · {order.customer.name} · {order.origin} → {order.destination}</MenuItem>)}</Select></FormControl>
          <TextField required size="small" type="date" name="lr_date" label="Receipt date" defaultValue={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)} slotProps={{ inputLabel: { shrink: true } }} sx={inputSx}/>
          <TextField required size="small" name="consignor_name" label="Consignor name" sx={inputSx}/>
          <TextField size="small" name="consignor_address" label="Consignor address" sx={inputSx}/>
          <TextField required size="small" name="consignee_name" label="Consignee name" sx={inputSx}/>
          <TextField size="small" name="consignee_address" label="Consignee address" sx={inputSx}/>
          <TextField required size="small" name="goods_description" label="Goods description" sx={inputSx}/>
          <TextField required size="small" name="package_count" label="Packages" type="number" defaultValue="1" slotProps={{ htmlInput: { min: 1, step: 1 } }} sx={inputSx}/>
          <TextField size="small" name="weight_kg" label="Weight (kg), optional" type="number" slotProps={{ htmlInput: { min: 0, step: "0.001" } }} sx={inputSx}/>
          <TextField required size="small" name="freight_amount" label="Freight amount (₹)" type="number" slotProps={{ htmlInput: { min: 0, step: "0.01" } }} sx={inputSx}/>
          <FormControl size="small" sx={inputSx}><InputLabel id="lr-payment">Freight payment</InputLabel><Select labelId="lr-payment" name="payment_type" label="Freight payment" defaultValue="TO_BE_BILLED"><MenuItem value="TO_PAY">To Pay</MenuItem><MenuItem value="PAID">Paid</MenuItem><MenuItem value="TO_BE_BILLED">To Be Billed</MenuItem></Select></FormControl>
          <TextField size="small" name="eway_bill_number" label="E-way bill number, optional" sx={inputSx}/>
          <TextField size="small" name="invoice_reference" label="Invoice reference, optional" sx={inputSx}/>
          <TextField size="small" name="delivery_instructions" label="Delivery instructions, optional" sx={{ ...inputSx, gridColumn: { sm: "1 / -1" } }}/>
        </Box>
        <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 2.5 }}><Button disableElevation={false} type="submit" variant="contained" disabled={busy || orders.length === 0}>{busy ? "Issuing…" : "Issue receipt"}</Button></Box>
        {!orders.length && <Typography variant="caption" color="warning.main">Create a transport order before issuing a lorry receipt.</Typography>}
      </Box>}

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(3,minmax(0,1fr))" }, gap: 1.5, mb: 2 }}>
        {[["Total receipts", receipts.length], ["Issued", receipts.filter(item => item.status === "ISSUED").length], ["Cancelled", receipts.filter(item => item.status === "CANCELLED").length]].map(([label, value]) => <Box key={String(label)} sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2, bgcolor: "background.paper" }}><Typography variant="body2" color="text.secondary">{label}</Typography><Typography sx={{ mt: .5, fontSize: 24, fontWeight: 650, fontVariantNumeric: "tabular-nums" }}>{loading ? "—" : value}</Typography></Box>)}
      </Box>

      <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2.5, bgcolor: "background.paper", overflow: "hidden" }}>
        <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 1.5, p: 2, borderBottom: "1px solid", borderColor: "divider" }}><Box><Typography variant="subtitle1" sx={{ fontWeight: 650 }}>Receipt register</Typography><Typography variant="caption" color="text.secondary">Most recent first · up to 500 records</Typography></Box><TextField size="small" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search receipts" aria-label="Search lorry receipts" slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16}/></InputAdornment> } }} sx={{ width: { xs: "100%", sm: 280 }, ...inputSx }}/></Box>
        {loading ? <Typography sx={{ p: 3 }} color="text.secondary">Loading receipts…</Typography> : filtered.length === 0 ? <Box sx={{ p: 6, textAlign: "center" }}><Truck size={24}/><Typography sx={{ mt: 1, fontWeight: 600 }}>{receipts.length ? "No matching receipts" : "No lorry receipts yet"}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>{receipts.length ? "Try another search term." : "Issue a receipt from a transport order to get started."}</Typography></Box> : <Box>
          <Box sx={{ display: { xs: "none", md: "grid" }, gridTemplateColumns: "minmax(140px,.8fr) minmax(190px,1.2fr) minmax(190px,1.2fr) minmax(140px,.8fr) 120px 180px", gap: 2, px: 2.5, py: 1.25, bgcolor: "action.hover" }}>{["LR number", "Customer and route", "Consignor → consignee", "Freight", "Status", ""].map((label, i) => <Typography key={i} variant="caption" color="text.secondary" sx={{ fontWeight: 650, textTransform: "uppercase", letterSpacing: ".04em" }}>{label}</Typography>)}</Box>
          {filtered.map((item, index) => <Box key={item.id} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(140px,.8fr) minmax(190px,1.2fr) minmax(190px,1.2fr) minmax(140px,.8fr) 120px 180px" }, alignItems: "center", gap: { xs: 1, md: 2 }, px: { xs: 2, sm: 2.5 }, py: 1.75, borderTop: index ? "1px solid" : "none", borderColor: "divider" }}>
            <Box><Typography variant="body2" sx={{ fontWeight: 650 }}>{item.lr_number}</Typography><Typography variant="caption" color="text.secondary">{new Date(`${item.lr_date}T12:00:00`).toLocaleDateString("en-IN", { dateStyle: "medium" })}</Typography></Box>
            <Box><Typography variant="body2" sx={{ fontWeight: 550 }}>{item.customer}</Typography><Typography variant="caption" color="text.secondary">{item.origin} → {item.destination}</Typography></Box>
            <Typography variant="body2" color="text.secondary" noWrap>{item.consignor_name} → {item.consignee_name}</Typography>
            <Box><Typography variant="body2" sx={{ fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>₹{Number(item.freight_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</Typography><Typography variant="caption" color="text.secondary">{paymentLabels[item.payment_type]}</Typography></Box>
            <Chip size="small" variant="outlined" color={item.status === "ISSUED" ? "success" : "default"} label={item.status === "ISSUED" ? "Issued" : "Cancelled"} sx={{ justifySelf: "start" }}/>
            <Box sx={{ display: "flex", justifyContent: { md: "flex-end" }, gap: .5 }}><Button size="small" onClick={() => setPreview(item)}>View / print</Button>{item.status === "ISSUED" && <Button size="small" color="error" onClick={() => setCancelTarget(item)}>Cancel</Button>}</Box>
          </Box>)}
        </Box>}
      </Box>
    </Box>

    <Dialog open={Boolean(preview)} onClose={() => setPreview(null)} fullWidth maxWidth="md">
      {preview && <>
        <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2 }}>Lorry receipt preview <Button disableElevation={false} startIcon={<Printer size={15}/>} onClick={() => window.print()}>Print</Button></DialogTitle>
        <DialogContent dividers>
          <Box className="lr-print-root" sx={{ p: { xs: 1, sm: 3 }, color: "#16231c", bgcolor: "#fff" }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, borderBottom: "2px solid #16734A", pb: 2 }}><Box><Typography variant="overline" sx={{ color: "#16734A", fontWeight: 700, letterSpacing: ".12em" }}>KriyoPay · Transport document</Typography><Typography component="h2" sx={{ mt: .5, fontSize: 25, fontWeight: 700 }}>Lorry Receipt</Typography></Box><Box sx={{ textAlign: "right" }}><Typography variant="body2" sx={{ fontWeight: 650 }}>{preview.lr_number}</Typography><Typography variant="body2" color="text.secondary">{new Date(`${preview.lr_date}T12:00:00`).toLocaleDateString("en-IN", { dateStyle: "long" })}</Typography><Chip size="small" label={preview.status} color={preview.status === "ISSUED" ? "success" : "default"} sx={{ mt: 1 }}/></Box></Box>
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2, py: 2 }}><Box><Typography variant="caption" color="text.secondary">CONSIGNOR</Typography><Typography sx={{ mt: .5, fontWeight: 650 }}>{preview.consignor_name}</Typography><Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{preview.consignor_address || "—"}</Typography></Box><Box><Typography variant="caption" color="text.secondary">CONSIGNEE</Typography><Typography sx={{ mt: .5, fontWeight: 650 }}>{preview.consignee_name}</Typography><Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{preview.consignee_address || "—"}</Typography></Box></Box>
            <Divider/>
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2, py: 2 }}><Box><Typography variant="caption" color="text.secondary">ORIGIN</Typography><Typography variant="body2">{preview.origin}</Typography></Box><Box><Typography variant="caption" color="text.secondary">DESTINATION</Typography><Typography variant="body2">{preview.destination}</Typography></Box><Box><Typography variant="caption" color="text.secondary">TRANSPORT ORDER</Typography><Typography variant="body2">{preview.order_number} · {preview.customer}</Typography></Box><Box><Typography variant="caption" color="text.secondary">VEHICLE / DRIVER</Typography><Typography variant="body2">{preview.vehicle || "Not assigned"} · {preview.driver || "Not assigned"}</Typography></Box></Box>
            <Divider/>
            <Box sx={{ py: 2 }}><Typography variant="caption" color="text.secondary">GOODS</Typography><Typography variant="body2" sx={{ mt: .5 }}>{preview.goods_description}</Typography><Typography variant="body2" color="text.secondary">{preview.package_count} packages{preview.weight_kg ? ` · ${preview.weight_kg} kg` : ""}</Typography></Box>
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2, p: 2, borderRadius: 1.5, bgcolor: "#f4f7f5" }}><Box><Typography variant="caption" color="text.secondary">FREIGHT</Typography><Typography sx={{ fontWeight: 650 }}>₹{Number(preview.freight_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</Typography></Box><Box><Typography variant="caption" color="text.secondary">PAYMENT TERMS</Typography><Typography sx={{ fontWeight: 650 }}>{paymentLabels[preview.payment_type]}</Typography></Box></Box>
            {(preview.eway_bill_number || preview.invoice_reference || preview.delivery_instructions) && <Box sx={{ pt: 2 }}><Typography variant="caption" color="text.secondary">REFERENCES AND INSTRUCTIONS</Typography>{preview.eway_bill_number && <Typography variant="body2">E-way bill: {preview.eway_bill_number}</Typography>}{preview.invoice_reference && <Typography variant="body2">Invoice: {preview.invoice_reference}</Typography>}{preview.delivery_instructions && <Typography variant="body2" sx={{ mt: .5 }}>{preview.delivery_instructions}</Typography>}</Box>}
            {preview.status === "CANCELLED" && <Alert severity="error" sx={{ mt: 2 }}>Cancelled: {preview.cancellation_reason}</Alert>}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 5, mt: 8 }}><Box sx={{ borderTop: "1px solid #9aa79f", pt: 1 }}><Typography variant="caption">Consignor signature</Typography></Box><Box sx={{ borderTop: "1px solid #9aa79f", pt: 1 }}><Typography variant="caption">Receiver signature and date</Typography></Box></Box>
          </Box>
        </DialogContent>
        <DialogActions><Button onClick={() => setPreview(null)}>Close</Button></DialogActions>
      </>}
    </Dialog>

    <Dialog open={Boolean(cancelTarget)} onClose={() => !busy && setCancelTarget(null)} fullWidth maxWidth="xs">
      <Box component="form" onSubmit={cancelReceipt}><DialogTitle>Cancel lorry receipt</DialogTitle><DialogContent><Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>This action is permanent and will be recorded in the audit log.</Typography><TextField name="reason" required fullWidth multiline minRows={2} label="Cancellation reason" slotProps={{ htmlInput: { minLength: 3, maxLength: 300 } }} sx={inputSx}/></DialogContent><DialogActions><Button disableElevation={false} onClick={() => setCancelTarget(null)} disabled={busy}>Keep receipt</Button><Button disableElevation={false} type="submit" color="error" variant="contained" disabled={busy}>{busy ? "Cancelling…" : "Cancel receipt"}</Button></DialogActions></Box>
    </Dialog>
  </Box>;
}
