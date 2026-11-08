"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, Paper, Stack, TextField, Typography } from "@mui/material";
import { BellRing, CheckCircle2, Mail, MessageCircle, RefreshCw, Route, TriangleAlert } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Notice = { id: string; channel: string; status: string; event: string; attempts: number; last_error: string; provider_reference: string };
type NotificationState = { email_configured: boolean; whatsapp_configured: boolean; google_routes_configured: boolean; notice: string; notices: Notice[] };
const statusColor = (status: string): "success" | "warning" | "default" | "error" => status === "SENT" || status === "DELIVERED" ? "success" : status === "FAILED" ? "error" : status === "UNKNOWN" ? "warning" : "default";

export default function CustomerNotifications() {
  const [data, setData] = useState<NotificationState | null>(null);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/fleet/customer-notifications");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not load notification status.");
      setData(result); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load notification status."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  async function retry(id: string) {
    setBusy(true);
    try {
      const response = await apiFetch("/fleet/customer-notifications", { method: "POST", body: JSON.stringify({ notice_id: id, reason, provider_checked: checked }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Retry was not authorized.");
      await load(); setReason(""); setChecked(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Retry failed."); }
    finally { setBusy(false); }
  }
  const pending = data?.notices.filter(notice => ["FAILED", "UNKNOWN"].includes(notice.status)).length || 0;
  const services = [
    { label: "Email delivery", configured: data?.email_configured, Icon: Mail, detail: "SMTP configuration" },
    { label: "WhatsApp Business", configured: data?.whatsapp_configured, Icon: MessageCircle, detail: "WhatsApp provider configuration" },
    { label: "Google Maps Routes", configured: data?.google_routes_configured, Icon: Route, detail: "Routing service configuration" },
  ];
  return <Box component="main" sx={{ width: "100%", maxWidth: 1760, mx: "auto", p: { xs: 2, sm: 3, lg: 4 } }}>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "flex-end" } }}>
      <Box><Typography variant="overline" color="primary" sx={{ fontWeight: 700, letterSpacing: ".14em" }}>CUSTOMER EXPERIENCE</Typography><Typography variant="h4">Notification delivery</Typography><Typography color="text.secondary" sx={{ mt: .75, maxWidth: 760 }}>Review delivery provider configuration and shipment messages that may need an operator decision.</Typography></Box>
      <Button variant="outlined" startIcon={<RefreshCw size={16}/>} onClick={() => void load()} disabled={loading}>Refresh delivery queue</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }} action={<Button color="inherit" size="small" onClick={() => void load()}>Retry</Button>}>{error}</Alert>}
    <Alert severity="info" sx={{ mt: 2, alignItems: "center" }}>{data?.notice || "Provider configuration does not confirm connectivity or message delivery. Customer consent is recorded when creating a shipment link."}</Alert>
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(3, minmax(0,1fr))" }, gap: 1.5, mt: 2 }}>
      {services.map(service => <Paper key={service.label} variant="outlined" sx={{ p: 2 }}><Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}><Box sx={{ display: "grid", placeItems: "center", width: 38, height: 38, borderRadius: 2, bgcolor: "action.hover", color: "primary.main" }}><service.Icon size={17}/></Box><Box sx={{ minWidth: 0, flex: 1 }}><Typography variant="subtitle2">{service.label}</Typography><Typography variant="caption" color="text.secondary">{service.detail}</Typography></Box><Chip size="small" color={service.configured ? "success" : "warning"} label={loading ? "Checking" : service.configured ? "Configured" : "Needs setup"}/></Stack></Paper>)}
    </Box>
    <Paper variant="outlined" sx={{ mt: 2.5, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" }, p: 2, borderBottom: 1, borderColor: "divider" }}><Box><Typography variant="subtitle1">Shipment message queue</Typography><Typography variant="caption" color="text.secondary">{loading ? "Loading delivery records…" : `${data?.notices.length || 0} records · ${pending} need review`}</Typography></Box>{pending > 0 && <Chip size="small" color="warning" icon={<TriangleAlert size={14}/>} label={`${pending} attention needed`}/>}</Stack>
      <Stack>
        {data?.notices.map(notice => <Box key={notice.id} sx={{ p: { xs: 2, sm: 2.5 }, borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 } }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", md: "flex-start" } }}>
            <Box sx={{ minWidth: 0, flex: 1 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}><Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{notice.event.replaceAll("_", " ")}</Typography><Chip size="small" label={notice.status.replaceAll("_", " ")} color={statusColor(notice.status)}/><Chip size="small" variant="outlined" label={notice.channel}/></Stack><Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Attempts: {notice.attempts}{notice.provider_reference ? ` · Provider ref: ${notice.provider_reference}` : ""}</Typography><Typography variant="caption" color={notice.status === "FAILED" ? "error.main" : "text.secondary"} sx={{ display: "block", mt: .5 }}>{notice.last_error || (notice.provider_reference ? "Provider reference recorded" : "No delivery detail recorded yet")}</Typography></Box>
            {(["FAILED", "UNKNOWN"].includes(notice.status)) && <Stack spacing={1} sx={{ width: { xs: "100%", md: 390 }, flexShrink: 0 }}><TextField size="small" label="Reason for another attempt" value={reason} onChange={event => setReason(event.target.value)} placeholder="Explain what you verified"/><FormControlLabel control={<Checkbox checked={checked} onChange={event => setChecked(event.target.checked)}/>} label={<Typography variant="caption">I checked provider logs and confirmed this message was not sent.</Typography>}/><Button variant="outlined" color="warning" disabled={busy || !checked || !reason.trim()} onClick={() => void retry(notice.id)}>Authorize retry</Button></Stack>}
            {(notice.status === "SENT" || notice.status === "DELIVERED") && <CheckCircle2 size={18} color="#16734A" aria-label="Message sent"/>}
          </Stack>
        </Box>)}
        {!loading && data?.notices.length === 0 && <Box sx={{ p: 5, textAlign: "center" }}><BellRing size={24} color="#9C9D89"/><Typography variant="subtitle2" sx={{ mt: 1 }}>No shipment messages queued</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>Consented email and WhatsApp updates will appear here when shipment links are created.</Typography></Box>}
        {loading && <Typography variant="body2" color="text.secondary" sx={{ p: 3 }}>Loading delivery records…</Typography>}
      </Stack>
    </Paper>
  </Box>;
}
