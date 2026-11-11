"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { BellRing, CheckCircle2, Clock3, Mail, MessageCircle, RefreshCw, TriangleAlert } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useListPagination } from "@/components/list-pagination";

type Notice = {
  id: string; channel: string; status: string; event: string; attempts: number;
  last_error: string; provider_reference: string; trip_number?: string; order_number?: string; updated_at?: string;
};
type NotificationState = { email_configured: boolean; whatsapp_configured: boolean; google_routes_configured: boolean; notice: string; notices: Notice[] };
const outcomes = [
  { label: "Sent", statuses: ["SENT", "DELIVERED", "READ"], color: "success", icon: CheckCircle2 },
  { label: "Failed", statuses: ["FAILED"], color: "error", icon: TriangleAlert },
  { label: "Provider accepted", statuses: ["ACCEPTED"], color: "info", icon: Mail },
  { label: "Other", statuses: ["PENDING", "PROCESSING", "UNKNOWN", "CANCELLED"], color: "default", icon: Clock3 },
] as const;
const outcomeFor = (status: string) => outcomes.find(outcome => outcome.statuses.some(value => value === status)) ?? outcomes[3];
const labels: Record<string, string> = {
  SENT: "Sent", DELIVERED: "Delivered", READ: "Read", FAILED: "Failed", ACCEPTED: "Provider accepted",
  PENDING: "Queued", PROCESSING: "Sending", UNKNOWN: "Needs verification", CANCELLED: "Cancelled",
};
const labelText = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/^./, first => first.toUpperCase());
const eventLabel = (event: string) => event.startsWith("delay:") ? "Possible delivery delay" : labelText(event.replace(/^status:/, ""));
const channelLabel = (channel: string) => channel === "WHATSAPP" ? "WhatsApp" : labelText(channel);

export default function CustomerNotifications() {
  const [data, setData] = useState<NotificationState | null>(null);
  const [error, setError] = useState("");
  const [noticeMessage, setNoticeMessage] = useState("");
  const [retryError, setRetryError] = useState("");
  const [target, setTarget] = useState<Notice | null>(null);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
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
    setRetryError("");
    setNoticeMessage("");
    try {
      const response = await apiFetch("/fleet/customer-notifications", { method: "POST", body: JSON.stringify({ notice_id: id, reason: reason.trim(), provider_checked: checked }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Retry was not authorized.");
      setData(current => current && { ...current, notices: current.notices.map(notice => notice.id === id ? { ...notice, status: result.status } : notice) });
      setTarget(null);
      setNoticeMessage("Another delivery attempt has been queued.");
      await load();
    } catch (cause) { setRetryError(cause instanceof Error ? cause.message : "Retry failed."); }
    finally { setBusy(false); }
  }

  const notices = data?.notices ?? [];
  const query = search.trim().toLowerCase();
  const filtered = notices.filter(notice =>
    (!filter || outcomeFor(notice.status).label === filter) &&
    [eventLabel(notice.event), channelLabel(notice.channel), notice.order_number, notice.trip_number, notice.provider_reference]
      .join(" ").toLowerCase().includes(query));
  const page = useListPagination(filtered, `${filter}:${search}`, "Shipment updates");
  const services = [
    { label: "Email", configured: data?.email_configured },
    { label: "WhatsApp", configured: data?.whatsapp_configured },
    { label: "Google Maps Routes", configured: data?.google_routes_configured },
  ];

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Customer experience</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Customer notifications</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Track delivery of email and WhatsApp shipment updates.</Typography>
      </Box>
      <Button variant="outlined" startIcon={<RefreshCw size={16}/>} onClick={() => void load()} disabled={loading || busy}>Refresh</Button>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {noticeMessage && <Alert severity="success">{noticeMessage}</Alert>}

    <Box role="group" aria-label="Filter shipment updates by outcome" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {outcomes.map(({ label, color, icon: Icon }) => <Button key={label} variant="outlined" color={color === "default" ? "inherit" : color}
        aria-pressed={filter === label} onClick={() => setFilter(filter === label ? "" : label)}
        sx={{ justifyContent: "space-between", gap: 1, p: 2, bgcolor: filter === label ? "action.selected" : "background.paper", borderColor: filter === label ? undefined : "divider" }}
        startIcon={<Icon size={17} aria-hidden="true"/>}>
        {label}
        <Typography component="span" sx={{ ml: "auto", fontWeight: 750, fontVariantNumeric: "tabular-nums" }}>
          {data ? notices.filter(notice => outcomeFor(notice.status).label === label).length : "—"}
        </Typography>
      </Button>)}
    </Box>

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box>
          <Typography component="h2" variant="h6">Shipment updates</Typography>
          <Typography variant="body2" color="text.secondary" aria-live="polite">{loading ? "Loading updates…" : `${filtered.length} shown · ${notices.length} recent updates`}</Typography>
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Search updates" placeholder="Order, trip, event, or channel" value={search} onChange={event => setSearch(event.target.value)} sx={{ minWidth: { sm: 240 } }}/>
          <TextField select size="small" label="Delivery outcome" value={filter} onChange={event => setFilter(event.target.value)} sx={{ minWidth: 175 }}>
            <MenuItem value="">All updates</MenuItem>
            {outcomes.map(outcome => <MenuItem key={outcome.label} value={outcome.label}>{outcome.label}</MenuItem>)}
          </TextField>
        </Stack>
      </Stack>
      {page.rows.map(notice => {
        const { color } = outcomeFor(notice.status);
        const canRetry = notice.status === "FAILED" || notice.status === "UNKNOWN";
        const ChannelIcon = notice.channel === "WHATSAPP" ? MessageCircle : Mail;
        return <Box component="article" key={notice.id} sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
            <Stack direction="row" spacing={1.5} sx={{ minWidth: 0 }}>
              <Box className="grid size-10 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-700"><ChannelIcon size={18} aria-hidden="true"/></Box>
              <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
                <Stack direction="row" useFlexGap spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                  <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 700 }}>{eventLabel(notice.event)}</Typography>
                  <Chip size="small" label={labels[notice.status] || labelText(notice.status)} color={notice.status === "UNKNOWN" ? "warning" : color}/>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {[channelLabel(notice.channel), notice.order_number && `Order ${notice.order_number}`, notice.trip_number && `Trip ${notice.trip_number}`].filter(Boolean).join(" · ")}
                </Typography>
                {notice.last_error && <Typography variant="body2" color={notice.status === "FAILED" ? "error.main" : "text.secondary"} sx={{ mt: .75 }}>
                  {canRetry ? notice.last_error : `Last attempt: ${notice.last_error}`}
                </Typography>}
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: .75 }}>
                  {notice.updated_at && `Updated ${new Date(notice.updated_at).toLocaleString()} · `}{notice.attempts} {notice.attempts === 1 ? "attempt" : "attempts"}
                </Typography>
                {notice.provider_reference && <Typography variant="caption" color="text.secondary">Provider reference {notice.provider_reference}</Typography>}
              </Box>
            </Stack>
            {canRetry && <Button variant="outlined" size="small" sx={{ alignSelf: { xs: "flex-start", md: "center" }, flexShrink: 0 }} disabled={busy || loading}
              onClick={() => { setReason(""); setChecked(false); setRetryError(""); setTarget(notice); }}>Review retry</Button>}
          </Stack>
        </Box>;
      })}
      {!loading && !error && !filtered.length && <Stack spacing={1} sx={{ p: 5, alignItems: "center", textAlign: "center" }}>
        <BellRing size={24} aria-hidden="true"/>
        <Typography variant="subtitle2">{notices.length ? "No matching updates" : "No shipment updates yet"}</Typography>
        <Typography variant="body2" color="text.secondary">{notices.length ? "Try a different search or delivery outcome." : "Email and WhatsApp updates appear here once they’re queued for a shipment."}</Typography>
        {notices.length > 0 && <Button onClick={() => { setFilter(""); setSearch(""); }}>Clear filters</Button>}
      </Stack>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <Paper component="details" variant="outlined" sx={{ borderRadius: 3, p: 2 }}>
      <Typography component="summary" variant="subtitle2" sx={{ cursor: "pointer" }}>Provider setup and delivery status</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>{data?.notice || "Provider acceptance confirms submission. Delivery confirmation appears when the provider reports it."}</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={1} sx={{ mt: 1.5, flexWrap: "wrap" }}>
        {services.map(service => <Chip key={service.label} variant="outlined" label={`${service.label} · ${service.configured === undefined ? "Status unavailable" : service.configured ? "Configured" : "Needs setup"}`}/>)}
      </Stack>
    </Paper>

    <Dialog open={Boolean(target)} onClose={() => { if (!busy) setTarget(null); }} fullWidth maxWidth="sm" aria-labelledby="notification-retry-title">
      <DialogTitle id="notification-retry-title">Review delivery retry</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {retryError && <Alert severity="error">{retryError}</Alert>}
          {target && <Box>
            <Typography sx={{ fontWeight: 700 }}>{eventLabel(target.event)} · {channelLabel(target.channel)}</Typography>
            {target.order_number && <Typography variant="body2">Order {target.order_number}</Typography>}
            {target.last_error && <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>{target.last_error}</Typography>}
            {target.provider_reference && <Typography variant="caption" sx={{ overflowWrap: "anywhere" }}>Provider reference {target.provider_reference}</Typography>}
          </Box>}
          <TextField multiline minRows={2} label="Reason for retry" value={reason} onChange={event => setReason(event.target.value)} slotProps={{ htmlInput: { maxLength: 500 } }}/>
          <FormControlLabel control={<Checkbox checked={checked} onChange={event => setChecked(event.target.checked)}/>} label="I checked the provider logs and confirmed this message was not sent."/>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setTarget(null)}>Cancel</Button>
        <Button variant="contained" disabled={busy || !target || !checked || !reason.trim()} onClick={() => { if (target) void retry(target.id); }}>{busy ? "Queuing…" : "Queue retry"}</Button>
      </DialogActions>
    </Dialog>
  </Box>;
}
