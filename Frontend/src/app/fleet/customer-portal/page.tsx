"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, FormControlLabel, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { Check, Copy, Link2, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { apiFetch } from "@/lib/api";

type ShipmentLink = { id: string; trip: string; expires_at: string; revoked: boolean };
type ShipmentTrip = { id: string; trip_number: string };

export default function ShipmentLinksPage() {
  const [links, setLinks] = useState<ShipmentLink[]>([]);
  const [trips, setTrips] = useState<ShipmentTrip[]>([]);
  const [trip, setTrip] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(false);
  const [consentNote, setConsentNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/fleet/shipment-links");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load shipment links.");
      setLinks(data.links); setTrips(data.trips); setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load shipment links."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  async function create() {
    setBusy(true); setMessage(""); setError("");
    try {
      const response = await apiFetch("/fleet/shipment-links", { method: "POST", body: JSON.stringify({ trip_id: trip, notify_email: email, notify_phone: phone, customer_consented: consent, consent_note: consentNote }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not create shipment link.");
      setUrl(data.url); setMessage("Private shipment link created. Share it with the intended customer."); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create link."); }
    finally { setBusy(false); }
  }
  async function revoke(id: string) {
    setBusy(true); setError("");
    try {
      const response = await apiFetch("/fleet/shipment-links", { method: "DELETE", body: JSON.stringify({ id }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not revoke shipment link.");
      if (links.find(item => item.id === id)?.trip === trip) setUrl("");
      await load(); setMessage("Shipment link revoked.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not revoke link."); }
    finally { setBusy(false); }
  }
  async function copyLink() {
    try { await navigator.clipboard.writeText(url); setMessage("Link copied to clipboard."); }
    catch { setError("Could not copy automatically. Select and copy the link below."); }
  }
  const activeLinks = links.filter(link => !link.revoked).length;
  const revokedLinks = links.length - activeLinks;

  return <Box component="main" sx={{ width: "100%", maxWidth: 1760, mx: "auto", p: { xs: 2, sm: 3, lg: 4 } }}>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "flex-end" } }}>
      <Box><Typography variant="overline" color="primary" sx={{ fontWeight: 700, letterSpacing: ".14em" }}>CUSTOMER EXPERIENCE</Typography><Typography variant="h4">Shipment tracking links</Typography><Typography color="text.secondary" sx={{ mt: .75, maxWidth: 760 }}>Give customers a private, time-limited view of a shipment. Consent is required before sending email or WhatsApp updates.</Typography></Box>
      <Button variant="outlined" startIcon={<RefreshCw size={16}/>} onClick={() => void load()} disabled={loading}>Refresh links</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }} action={<Button color="inherit" size="small" onClick={() => void load()}>Retry</Button>}>{error}</Alert>}
    {message && <Alert severity="success" sx={{ mt: 2 }}>{message}</Alert>}
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(3, minmax(0,1fr))" }, gap: 1.5, mt: 3 }}>
      {[{ label: "Shipments available", value: trips.length }, { label: "Active links", value: activeLinks }, { label: "Revoked links", value: revokedLinks }].map(metric => <Paper key={metric.label} variant="outlined" sx={{ p: 2 }}><Typography variant="body2" color="text.secondary">{metric.label}</Typography><Typography variant="h5" sx={{ mt: .5, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{loading ? "—" : metric.value}</Typography></Paper>)}
    </Box>
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "minmax(340px,.85fr) minmax(0,1.15fr)" }, gap: 2, mt: 2.5, alignItems: "start" }}>
      <Paper variant="outlined" sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center", mb: 2 }}><Box sx={{ display: "grid", placeItems: "center", width: 38, height: 38, borderRadius: 2, bgcolor: "action.hover", color: "primary.main" }}><Link2 size={18}/></Box><Box><Typography variant="subtitle1">Create customer link</Typography><Typography variant="caption" color="text.secondary">The link expires after seven days.</Typography></Box></Stack>
        <Stack spacing={1.5}>
          <TextField select required label="Shipment" value={trip} onChange={event => setTrip(event.target.value)}><MenuItem value="">Choose a shipment</MenuItem>{trips.map(item => <MenuItem key={item.id} value={item.id}>{item.trip_number}</MenuItem>)}</TextField>
          <TextField label="Customer email (optional)" type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="name@company.com"/>
          <TextField label="WhatsApp number (optional)" value={phone} onChange={event => setPhone(event.target.value)} placeholder="+91 98765 43210"/>
          <TextField label="Consent source or reference" value={consentNote} onChange={event => setConsentNote(event.target.value)} placeholder="Call, email, or customer reference"/>
          <FormControlLabel control={<Checkbox checked={consent} onChange={event => setConsent(event.target.checked)}/>} label={<Typography variant="body2">Customer agreed to receive shipment updates on the selected channels.</Typography>}/>
          <Button variant="contained" startIcon={<Link2 size={16}/>} disabled={busy || !trip} onClick={() => void create()}>{busy ? "Creating link…" : "Create private link"}</Button>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ mt: 2, p: 1.5, borderRadius: 2, bgcolor: "action.hover", color: "text.secondary", alignItems: "flex-start" }}><ShieldCheck size={16}/><Typography variant="caption">Anyone with the link can view the shipment until it expires or you revoke it.</Typography></Stack>
      </Paper>
      <Stack spacing={1.5}>
        {url && <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}><Check size={16} color="#16835f"/><Typography variant="subtitle2">New tracking link</Typography></Stack><Stack direction={{ xs: "column", sm: "row" }} spacing={1}><TextField size="small" fullWidth value={url} slotProps={{ htmlInput: { readOnly: true, "aria-label": "Created tracking link" } }}/><Button variant="outlined" startIcon={<Copy size={15}/>} onClick={() => void copyLink()}>Copy</Button></Stack></Paper>}
        <Paper variant="outlined" sx={{ overflow: "hidden" }}>
          <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}><Typography variant="subtitle1">Issued links</Typography><Typography variant="caption" color="text.secondary">Revoke access at any time.</Typography></Box>
          <Stack>
            {links.map(link => <Stack key={link.id} direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" }, p: 2, borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 } }}>
              <Box sx={{ minWidth: 0 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}><Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{link.trip}</Typography><Chip size="small" color={link.revoked ? "default" : "success"} label={link.revoked ? "Revoked" : "Active"}/></Stack><Typography variant="caption" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: .5, mt: .5 }}><RefreshCw size={12}/>{link.revoked ? "Access disabled" : `Expires ${new Date(link.expires_at).toLocaleString()}`}</Typography></Box>
              <Button color="error" variant="outlined" size="small" startIcon={<XCircle size={15}/>} disabled={busy || link.revoked} onClick={() => void revoke(link.id)}>Revoke access</Button>
            </Stack>)}
            {!loading && links.length === 0 && <Box sx={{ p: 5, textAlign: "center" }}><Link2 size={24} color="#94a3b8"/><Typography variant="subtitle2" sx={{ mt: 1 }}>No tracking links yet</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>Create a private link for an active shipment to share delivery progress.</Typography></Box>}
            {loading && <Typography variant="body2" color="text.secondary" sx={{ p: 3 }}>Loading issued links…</Typography>}
          </Stack>
        </Paper>
      </Stack>
    </Box>
  </Box>;
}
