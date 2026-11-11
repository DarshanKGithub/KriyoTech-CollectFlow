"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { Copy, Link2, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useListPagination } from "@/components/list-pagination";

type ShipmentLink = { id: string; trip: string; expires_at: string; revoked: boolean };
type ShipmentTrip = { id: string; trip_number: string };
const linkStatus = (link: ShipmentLink, now: number) => link.revoked ? "Revoked" : Date.parse(link.expires_at) <= now ? "Expired" : "Active";

export default function ShipmentLinksPage() {
  const [links, setLinks] = useState<ShipmentLink[]>([]);
  const [trips, setTrips] = useState<ShipmentTrip[]>([]);
  const [trip, setTrip] = useState("");
  const [created, setCreated] = useState<{ id: string; url: string } | null>(null);
  const [dialog, setDialog] = useState<"create" | "share" | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ShipmentLink | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [dialogError, setDialogError] = useState("");
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
    setBusy(true); setMessage(""); setDialogError("");
    try {
      const response = await apiFetch("/fleet/shipment-links", { method: "POST", body: JSON.stringify({ trip_id: trip, notify_email: email, notify_phone: phone, customer_consented: consent, consent_note: consentNote }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not create shipment link.");
      setCreated({ id: data.id, url: data.url });
      setDialog("share");
      await load();
    } catch (cause) { setDialogError(cause instanceof Error ? cause.message : "Could not create link."); }
    finally { setBusy(false); }
  }
  async function revoke(id: string) {
    setBusy(true); setDialogError(""); setMessage("");
    try {
      const response = await apiFetch("/fleet/shipment-links", { method: "DELETE", body: JSON.stringify({ id }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not revoke shipment link.");
      if (created?.id === id) setCreated(null);
      setRevokeTarget(null);
      await load(); setMessage("Shipment link revoked.");
    } catch (cause) { setDialogError(cause instanceof Error ? cause.message : "Could not revoke link."); }
    finally { setBusy(false); }
  }
  async function copyLink() {
    if (!created) return;
    try { await navigator.clipboard.writeText(created.url); setDialogError(""); setMessage("Link copied to clipboard."); }
    catch { setDialogError("Select the link and copy it manually."); }
  }

  const now = Date.now();
  const statuses = ["Active", "Expired", "Revoked"];
  const filtered = links.filter(link => (!filter || linkStatus(link, now) === filter) &&
    link.trip.toLowerCase().includes(search.trim().toLowerCase()));
  const page = useListPagination(filtered, `${filter}:${search}`, "Tracking links");
  const hasContact = Boolean(email.trim() || phone.trim());

  function openDialog(next: "create" | "share") {
    setDialogError(""); setMessage("");
    if (next === "create") {
      setTrip(""); setEmail(""); setPhone(""); setConsent(false); setConsentNote("");
    }
    setDialog(next);
  }

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Customer portal</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Shipment tracking links</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Create and manage the links customers use to follow their deliveries.</Typography>
      </Box>
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button variant="outlined" startIcon={<RefreshCw size={16}/>} disabled={loading || busy} onClick={() => void load()}>Refresh</Button>
        <Button variant="contained" startIcon={<Plus size={17}/>} disabled={loading || busy} onClick={() => openDialog("create")}>Create tracking link</Button>
      </Stack>
    </Stack>
    {error && <Alert severity="error">{error}</Alert>}
    {message && dialog !== "share" && <Alert severity="success">{message}</Alert>}
    <Box role="group" aria-label="Filter links by status" className="grid gap-3 sm:grid-cols-3">
      {statuses.map(status => <Button key={status} variant="outlined" aria-pressed={filter === status}
        onClick={() => setFilter(filter === status ? "" : status)}
        sx={{ justifyContent: "space-between", p: 2, bgcolor: filter === status ? "action.selected" : "background.paper", borderColor: filter === status ? "primary.main" : "divider" }}>
        {status} <Typography component="span" sx={{ fontWeight: 750 }}>{loading ? "—" : links.filter(link => linkStatus(link, now) === status).length}</Typography>
      </Button>)}
    </Box>

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box><Typography component="h2" variant="h6">Issued links</Typography><Typography variant="body2" color="text.secondary">{loading ? "Loading links…" : `${filtered.length} shown · ${links.length} total`}</Typography></Box>
        <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={1}>
          <TextField size="small" label="Search by trip number" value={search} onChange={event => setSearch(event.target.value)}/>
          <TextField select size="small" label="Status" value={filter} onChange={event => setFilter(event.target.value)} sx={{ minWidth: 130 }}>
            <MenuItem value="">All links</MenuItem>{statuses.map(status => <MenuItem key={status} value={status}>{status}</MenuItem>)}
          </TextField>
        </Stack>
      </Stack>
      {page.rows.map(link => {
        const status = linkStatus(link, now);
        return <Stack key={link.id} direction={{ xs: "column", sm: "row" }} useFlexGap spacing={1.5} sx={{ alignItems: { sm: "center" }, justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
          <Stack direction="row" useFlexGap spacing={1.5} sx={{ alignItems: "center" }}>
            <Box className="grid size-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-forest"><Link2 size={18}/></Box>
            <Box sx={{ minWidth: 0 }}>
              <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap", alignItems: "center" }}>
                <Typography variant="subtitle2" sx={{ overflowWrap: "anywhere" }}>{link.trip}</Typography>
                <Chip size="small" label={status} color={status === "Active" ? "success" : status === "Expired" ? "warning" : "default"}/>
              </Stack>
              <Typography variant="caption" color="text.secondary">{status === "Revoked" ? "Access turned off" : `${status === "Expired" ? "Expired" : "Expires"} ${new Date(link.expires_at).toLocaleString()}`}</Typography>
            </Box>
          </Stack>
          {status === "Active" && <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
            {created?.id === link.id && <Button size="small" onClick={() => openDialog("share")}>View link</Button>}
            <Button size="small" color="error" disabled={busy} onClick={() => { setDialogError(""); setRevokeTarget(link); }}>Revoke access</Button>
          </Stack>}
        </Stack>;
      })}
      {!loading && !filtered.length && !error && <Box sx={{ p: 5, textAlign: "center" }}>
        <Typography sx={{ fontWeight: 700 }}>{links.length ? "No matching links" : "No tracking links yet"}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>{links.length ? "Try a different trip number or status." : "Create a tracking link to share a delivery with a customer."}</Typography>
      </Box>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <Dialog open={Boolean(dialog)} onClose={() => { if (!busy) setDialog(null); }} fullWidth maxWidth="sm" aria-labelledby="tracking-dialog-title">
      <DialogTitle id="tracking-dialog-title">{dialog === "share" ? "Share tracking link" : "Create tracking link"}</DialogTitle>
      <DialogContent dividers>
        {dialogError && <Alert severity="error" sx={{ mb: 2 }}>{dialogError}</Alert>}
        {dialog === "share" && created ? <Stack useFlexGap spacing={2}>
          <Alert severity="info">Copy this link before leaving the page. Anyone with it can view the shipment until it expires or is revoked.</Alert>
          <TextField label="Customer tracking link" value={created.url} slotProps={{ htmlInput: { readOnly: true } }}/>
          {message && <Alert severity="success">{message}</Alert>}
        </Stack> : <Stack id="create-tracking-link" component="form" onSubmit={event => { event.preventDefault(); void create(); }} spacing={2}>
          <Alert severity="info" icon={<ShieldCheck size={20}/>}>The link is valid for seven days. Share it only with the intended customer.</Alert>
          <TextField select required label="Shipment" value={trip} onChange={event => setTrip(event.target.value)}>
            {trips.map(item => <MenuItem key={item.id} value={item.id}>{item.trip_number}</MenuItem>)}
          </TextField>
          {!trips.length && <Typography variant="body2" color="text.secondary">No trips linked to customer orders are available.</Typography>}
          <Typography variant="subtitle2">Customer notifications (optional)</Typography>
          <TextField label="Customer email" type="email" value={email} onChange={event => setEmail(event.target.value)}/>
          <TextField label="WhatsApp number" type="tel" value={phone} onChange={event => setPhone(event.target.value)} placeholder="+919876543210"/>
          {hasContact && <>
            <FormControlLabel control={<Checkbox checked={consent} onChange={event => setConsent(event.target.checked)}/>} label="The customer agreed to receive shipment updates."/>
            <TextField required label="How did the customer agree?" value={consentNote} onChange={event => setConsentNote(event.target.value)} placeholder="Call, email, or customer reference"/>
          </>}
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setDialog(null)}>{dialog === "share" ? "Done" : "Cancel"}</Button>
        {dialog === "share" ? <Button variant="contained" startIcon={<Copy size={16}/>} onClick={() => void copyLink()}>Copy link</Button> :
          <Button variant="contained" type="submit" form="create-tracking-link" disabled={busy || !trip || (hasContact && (!consent || !consentNote.trim()))}>{busy ? "Creating…" : "Create link"}</Button>}
      </DialogActions>
    </Dialog>

    <Dialog open={Boolean(revokeTarget)} onClose={() => { if (!busy) setRevokeTarget(null); }} aria-labelledby="revoke-link-title">
      <DialogTitle id="revoke-link-title">Revoke tracking link?</DialogTitle>
      <DialogContent>
        {dialogError && <Alert severity="error" sx={{ mb: 2 }}>{dialogError}</Alert>}
        <Typography variant="body2">Anyone using this link for trip {revokeTarget?.trip} will lose access immediately.</Typography>
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setRevokeTarget(null)}>Cancel</Button>
        <Button color="error" variant="contained" disabled={busy || !revokeTarget} onClick={() => { if (revokeTarget) void revoke(revokeTarget.id); }}>{busy ? "Revoking…" : "Revoke link"}</Button>
      </DialogActions>
    </Dialog>
  </Box>;
}
