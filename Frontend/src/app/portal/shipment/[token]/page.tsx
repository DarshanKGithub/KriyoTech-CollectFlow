"use client";

import { partnerHeaders } from "@/lib/partner";
import { API_URL } from "@/lib/api";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Alert, Box, Button, Chip, Container, Paper, Stack, TextField, Typography } from "@mui/material";
import { ArrowDown, Check, CircleCheck, CircleDashed, CircleDot, FileText, MapPin, PackageCheck, RefreshCw, ShieldCheck, Truck } from "lucide-react";

type Shipment = { order_number: string; customer: string; origin: string; destination: string; status: string; eta: string | null; eta_source: string; pickup_at: string | null; loaded_at: string | null; delivery_at: string | null; delivery_proof_available: boolean; invoice_available: boolean; issues: { reference: string; status: string; description: string; resolution: string }[] };
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Not recorded yet";

export default function ShipmentPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [data, setData] = useState<Shipment | null>(null);
  const [error, setError] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const endpoint = `${API_URL}/fleet/public/shipment/${encodeURIComponent(token)}`;

  const load = useCallback(async () => {
    const response = await fetch(endpoint, { cache: "no-store", headers: partnerHeaders(), credentials: "omit", referrerPolicy: "no-referrer" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.detail || "Shipment unavailable.");
    setData(result); setError("");
  }, [endpoint]);
  useEffect(() => { void load().catch(cause => setError(cause.message)).finally(() => setLoading(false)); }, [load]);

  async function report(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(endpoint, { method: "POST", credentials: "omit", referrerPolicy: "no-referrer", headers: { "Content-Type": "application/json", ...partnerHeaders() }, body: JSON.stringify({ description }) });
      const result = await response.json(); if (!response.ok) throw new Error(result.error || "Could not report issue.");
      setDescription(""); await load(); setNotice("Your message was sent to the delivery team.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not report issue."); }
    finally { setBusy(false); }
  }
  async function unsubscribe() {
    setBusy(true); setError("");
    try {
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json", ...partnerHeaders() }, referrerPolicy: "no-referrer", body: JSON.stringify({ action: "unsubscribe" }) });
      if (!response.ok) throw new Error("Could not stop notifications.");
      setNotice("Shipment notifications have been stopped for this link.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not stop notifications."); }
    finally { setBusy(false); }
  }

  const steps = data ? [{ label: "Picked up", time: data.pickup_at, icon: PackageCheck }, { label: "On the way", time: data.loaded_at, icon: Truck }, { label: "Delivered", time: data.delivery_at, icon: Check }] : [];
  const currentStep = data?.delivery_at ? 2 : data?.loaded_at ? 1 : data?.pickup_at ? 0 : -1;

  if (loading) return <Container maxWidth="md" sx={{ py: { xs: 5, sm: 8 } }}><Paper variant="outlined" sx={{ p: { xs: 3, sm: 5 }, borderRadius: 4, textAlign: "center" }}><Truck size={28} color="#16734A"/><Typography variant="h6" sx={{ mt: 2 }}>Opening shipment tracking</Typography><Typography color="text.secondary" variant="body2" sx={{ mt: 1 }}>Please wait while we check your private link.</Typography></Paper></Container>;
  if (!data) return <Container maxWidth="md" sx={{ py: { xs: 5, sm: 8 } }}><Paper variant="outlined" sx={{ p: { xs: 3, sm: 5 }, borderRadius: 4, textAlign: "center" }}><ShieldCheck size={28} color="#64748b"/><Typography variant="h5" sx={{ mt: 2, fontWeight: 700 }}>Shipment link unavailable</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>This link may have expired or been turned off. Please contact the company that shared it with you.</Typography>{error && <Alert severity="info" sx={{ mt: 3, textAlign: "left" }}>{error}</Alert>}<Button startIcon={<RefreshCw size={15}/>} onClick={() => { setLoading(true); void load().catch(cause => setError(cause.message)).finally(() => setLoading(false)); }} sx={{ mt: 2 }}>Try again</Button></Paper></Container>;

  return <Box component="main" sx={{ minHeight: "100vh", bgcolor: "#f6f8f7", py: { xs: 3, sm: 5 } }}><Container maxWidth="md">
    <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 3 }}><Box sx={{ display: "grid", placeItems: "center", width: 38, height: 38, borderRadius: 2, bgcolor: "#e7f4ed", color: "#16734A" }}><Truck size={19}/></Box><Box><Typography variant="subtitle2" sx={{ fontWeight: 800, color: "#145c3d", lineHeight: 1.1 }}>KriyoPay</Typography><Typography variant="caption" color="text.secondary">Shipment updates</Typography></Box></Stack>
    {error && <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={() => void load()}>Retry</Button>}>{error}</Alert>}{notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
    <Paper variant="outlined" sx={{ overflow: "hidden", borderRadius: 4, borderColor: "#e1e8e4", boxShadow: "0 10px 35px rgba(20,50,35,.05)" }}>
      <Box sx={{ p: { xs: 3, sm: 4 }, color: "white", bgcolor: "#123d2c", backgroundImage: "linear-gradient(120deg,#123d2c,#1d6948)" }}>
        <Stack direction="row" spacing={2} sx={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap" }}><Box><Typography variant="overline" sx={{ color: "#b9dec9", fontWeight: 700, letterSpacing: ".12em" }}>SHIPMENT TRACKING</Typography><Typography variant="h4" sx={{ mt: .5, fontWeight: 800, letterSpacing: "-.03em" }}>{data.order_number}</Typography><Typography sx={{ mt: .5, color: "#e2eee7" }}>{data.customer}</Typography></Box><Chip label={data.status.replaceAll("_", " ")} sx={{ color: "white", bgcolor: "rgba(255,255,255,.15)", fontWeight: 700, border: "1px solid rgba(255,255,255,.22)" }}/></Stack>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr auto 1fr" }, alignItems: "center", gap: 2, mt: 4, p: 2.5, borderRadius: 3, bgcolor: "rgba(255,255,255,.09)" }}><Box><Typography variant="caption" sx={{ color: "#b9dec9", fontWeight: 700 }}>PICKUP</Typography><Typography sx={{ mt: .5, fontWeight: 700 }}>{data.origin}</Typography></Box><ArrowDown size={17} style={{ color: "#b9dec9", transform: "rotate(-90deg)" }}/><Box><Typography variant="caption" sx={{ color: "#b9dec9", fontWeight: 700 }}>DELIVERY</Typography><Typography sx={{ mt: .5, fontWeight: 700 }}>{data.destination}</Typography></Box></Box>
      </Box>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2, p: { xs: 2, sm: 3 }, borderBottom: "1px solid", borderColor: "divider" }}>
        <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, bgcolor: "#f8faf9" }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><MapPin size={17} color="#16734A"/><Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>ESTIMATED ARRIVAL</Typography></Stack><Typography variant="h6" sx={{ mt: 1, fontWeight: 750 }}>{data.eta ? new Date(data.eta).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "We’ll update this when available"}</Typography>{data.eta && <Typography variant="caption" color="text.secondary">{data.eta_source === "GOOGLE_TRAFFIC" ? "Road and traffic estimate" : "Estimate based on past trips"} · may change during travel</Typography>}</Paper>
        <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><CircleDot size={17} color="#16734A"/><Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>DELIVERY PROGRESS</Typography></Stack><Stack direction="row" spacing={1} sx={{ mt: 2, alignItems: "flex-start" }}>{steps.map((step, index) => { const complete = Boolean(step.time); const active = currentStep === index; const Icon = complete ? CircleCheck : active ? CircleDot : CircleDashed; return <Box key={step.label} sx={{ display: "flex", flex: 1, minWidth: 0, alignItems: "flex-start", gap: .7 }}><Box sx={{ display: "grid", justifyItems: "center", gap: .5 }}><Icon size={18} color={complete ? "#168253" : active ? "#b7791f" : "#94a3b8"}/><Typography variant="caption" sx={{ fontWeight: active ? 700 : 600, color: complete ? "#166342" : active ? "#8a5a12" : "#64748b", lineHeight: 1.2 }}>{step.label}</Typography><Typography variant="caption" color="text.secondary" sx={{ fontSize: 10, textAlign: "center" }}>{step.time ? new Date(step.time).toLocaleDateString() : "Waiting"}</Typography></Box>{index < steps.length - 1 && <Box sx={{ height: 1, flex: 1, mt: 1, bgcolor: complete ? "#8bc5a6" : "#e2e8f0" }}/>}</Box>; })}</Stack><Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>Pickup: {dateLabel(data.pickup_at)} · Loaded: {dateLabel(data.loaded_at)} · Delivered: {dateLabel(data.delivery_at)}</Typography></Paper>
      </Box>
      {(data.delivery_proof_available || data.invoice_available) && <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, px: { xs: 2, sm: 3 }, py: 2, borderBottom: "1px solid", borderColor: "divider" }}>{data.delivery_proof_available && <Button component="a" href={`${endpoint}/pod`} rel="noreferrer" referrerPolicy="no-referrer" variant="outlined" startIcon={<FileText size={15}/>}>Download delivery proof</Button>}{data.invoice_available && <Button component="a" href={`${endpoint}/invoice`} rel="noreferrer" variant="outlined" startIcon={<FileText size={15}/>}>Download invoice</Button>}</Box>}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 0 }}>
        <Box sx={{ p: { xs: 2.5, sm: 3 }, borderRight: { md: "1px solid" }, borderColor: "divider" }}><Typography variant="subtitle1" sx={{ fontWeight: 750 }}>Need help with this delivery?</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>Send a note to the delivery team and they’ll review it.</Typography><form onSubmit={event => void report(event)}><TextField fullWidth multiline minRows={3} sx={{ my: 2 }} label="What happened?" value={description} onChange={event => setDescription(event.target.value)} slotProps={{ htmlInput: { maxLength: 1000 } }}/><Button type="submit" variant="contained" disabled={busy || description.trim().length < 5}>{busy ? "Sending…" : "Send message"}</Button></form></Box>
        <Box sx={{ p: { xs: 2.5, sm: 3 }, bgcolor: "#fbfcfb" }}><Typography variant="subtitle1" sx={{ fontWeight: 750 }}>Messages and updates</Typography>{data.issues.length ? <Stack spacing={1.5} sx={{ mt: 1.5 }}>{data.issues.map(issue => <Paper key={issue.reference} variant="outlined" sx={{ p: 1.5, borderRadius: 2.5 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}><Typography variant="body2" sx={{ fontWeight: 650 }}>{issue.description}</Typography><Chip size="small" label={issue.status.replaceAll("_", " ")}/></Stack>{issue.resolution && <Typography variant="body2" color="primary" sx={{ mt: 1 }}>Response: {issue.resolution}</Typography>}<Typography variant="caption" color="text.secondary">Reference {issue.reference}</Typography></Paper>)}</Stack> : <Box sx={{ mt: 2, p: 2, borderRadius: 2.5, bgcolor: "#f1f5f3" }}><Typography variant="body2" color="text.secondary">No messages yet. Use the form to ask about this shipment.</Typography></Box>}<Button size="small" color="inherit" disabled={busy} onClick={() => void unsubscribe()} sx={{ mt: 2, textTransform: "none", color: "text.secondary" }}>Stop shipment notifications</Button></Box>
      </Box>
    </Paper>
    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2, textAlign: "center" }}><ShieldCheck size={13} style={{ verticalAlign: "middle", marginRight: 5 }}/>This private link only shows shipment progress and customer messages.</Typography>
  </Container></Box>;
}
