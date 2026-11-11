"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { ChevronDown, History, RefreshCw, Truck } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useListPagination } from "@/components/list-pagination";

type Booking = { id: string; status: string; order: string; customer: string; truck: string; proposed_amount: string; accepted_amount: string | null; trip: string | null; notes: string };

const money = (value: string | null) => value ? `₹${Number(value).toLocaleString("en-IN")}` : "—";
const statuses = {
  BOOKED: { label: "Booked", color: "success" },
  OFFERED: { label: "Waiting for customer", color: "warning" },
  DECLINED: { label: "Declined", color: "default" },
  CANCELLED: { label: "Cancelled", color: "default" },
} as const;
const bookingStatus = (status: string) => statuses[status as keyof typeof statuses] ??
  { label: status.replaceAll("_", " ").toLowerCase(), color: "default" as const };

export default function BookingHistory() {
  const [rows, setRows] = useState<Booking[]>([]);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [cancelTarget, setCancelTarget] = useState<Booking | null>(null);
  const [cancelError, setCancelError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/fleet/booking-history");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load booking history.");
      setRows(data);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load booking history.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  async function cancel(id: string) {
    setBusy(true);
    setCancelError("");
    setNotice("");
    try {
      const response = await apiFetch(`/fleet/booking-history/${id}/cancel`, { method: "POST", body: JSON.stringify({ reason: reason.trim() }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Cancellation failed.");
      setRows(current => current.map(row => row.id === id ? { ...row, status: "CANCELLED" } : row));
      setCancelTarget(null);
      setNotice("Booking cancelled. The order is open again.");
      await load();
    } catch (cause) { setCancelError(cause instanceof Error ? cause.message : "Cancellation failed."); }
    finally { setBusy(false); }
  }
  const filtered = rows.filter(row => {
    const matchesStatus = !statusFilter || row.status === statusFilter;
    const text = [row.order, row.customer, row.truck, row.trip, row.status, bookingStatus(row.status).label].join(" ");
    return matchesStatus && text.toLowerCase().includes(query.trim().toLowerCase());
  });
  const page = useListPagination(filtered, `${query}:${statusFilter}`, "Booking history pages");

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Return loads</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Booking history</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>See which bookings are confirmed and which trip was assigned.</Typography>
      </Box>
      <Button startIcon={<RefreshCw size={16}/>} variant="outlined" onClick={() => void load()} disabled={loading || busy}>Refresh</Button>
    </Stack>

    {error && <Alert severity="error">{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box>
          <Typography component="h2" variant="h6">Return load bookings</Typography>
          <Typography variant="body2" color="text.secondary" aria-live="polite">{loading ? "Loading bookings…" : `${filtered.length} shown · ${rows.length} total`}</Typography>
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Search bookings" placeholder="Order, customer, truck, or trip" value={query} onChange={event => setQuery(event.target.value)} sx={{ minWidth: { sm: 245 } }}/>
          <TextField select size="small" label="Booking status" value={statusFilter} onChange={event => setStatusFilter(event.target.value)} sx={{ minWidth: 185 }}>
            <MenuItem value="">All statuses</MenuItem>
            {Object.entries(statuses).map(([value, status]) => <MenuItem key={value} value={value}>{status.label}</MenuItem>)}
          </TextField>
        </Stack>
      </Stack>

      {page.rows.map(row => {
        const status = bookingStatus(row.status);
        const cancelled = row.status === "CANCELLED";
        const booked = row.status === "BOOKED";
        return <Box component="article" key={row.id} sx={{ px: 2, py: 2, borderBottom: 1, borderColor: "divider", "&:last-child": { borderBottom: 0 } }}>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0,1fr) minmax(150px,.7fr) minmax(0,1fr)" }, gap: 2, alignItems: "center" }}>
            <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
              <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 700 }}>{row.customer}</Typography>
              <Typography variant="body2" color="text.secondary">Order {row.order}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: .5 }}>Booking status</Typography>
              <Chip size="small" color={status.color} label={status.label}/>
            </Box>
            <Stack direction="row" spacing={1.25} sx={{ alignItems: "center", minWidth: 0, p: 1.25, borderRadius: 2, bgcolor: booked && row.trip ? undefined : "action.hover" }} className={booked && row.trip ? "bg-emerald-50" : undefined}>
              <Truck size={18} aria-hidden="true" className="shrink-0 text-forest"/>
              <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
                <Typography variant="caption" color="text.secondary">{cancelled && row.trip ? "Cancelled trip" : "Assigned trip"}</Typography>
                <Typography variant="subtitle2" sx={{ fontWeight: 750 }}>{row.trip || "No trip assigned"}</Typography>
                {row.trip && row.truck && <Typography variant="caption" color="text.secondary">Truck {row.truck}</Typography>}
              </Box>
            </Stack>
          </Box>
          <Box component="details" sx={{ mt: 1.5, "&[open] .booking-details-icon": { transform: "rotate(180deg)" } }}>
            <Box component="summary" sx={{ display: "inline-flex", gap: .75, alignItems: "center", cursor: "pointer", color: "primary.main", fontSize: 14, fontWeight: 600, "&::-webkit-details-marker": { display: "none" } }}>
              Booking details <ChevronDown size={15} aria-hidden="true" className="booking-details-icon"/>
            </Box>
            <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={2} sx={{ mt: 1.5, flexWrap: "wrap" }}>
              <Box><Typography variant="caption" color="text.secondary">Offered rate</Typography><Typography variant="body2">{money(row.proposed_amount)}</Typography></Box>
              <Box><Typography variant="caption" color="text.secondary">Accepted rate</Typography><Typography variant="body2">{money(row.accepted_amount)}</Typography></Box>
              {!row.trip && row.truck && <Box><Typography variant="caption" color="text.secondary">Suggested truck</Typography><Typography variant="body2">{row.truck}</Typography></Box>}
            </Stack>
            {row.notes && <Typography variant="body2" sx={{ mt: 1, overflowWrap: "anywhere" }} color="text.secondary">{row.notes}</Typography>}
            {booked && <Button size="small" color="error" sx={{ mt: 1 }} disabled={busy || loading} onClick={() => { setReason(""); setCancelError(""); setCancelTarget(row); }}>Cancel unstarted booking</Button>}
          </Box>
        </Box>;
      })}

      {!loading && !filtered.length && !error && <Stack spacing={1} sx={{ p: 5, textAlign: "center", alignItems: "center" }}>
        <History size={25} aria-hidden="true"/>
        <Typography variant="subtitle2">{rows.length ? "No matching bookings" : "No return load offers yet"}</Typography>
        <Typography variant="body2" color="text.secondary">{rows.length ? "Try a different search or booking status." : "Offers and assigned trips will appear here as you work on return loads."}</Typography>
        {rows.length > 0 && <Button onClick={() => { setQuery(""); setStatusFilter(""); }}>Clear filters</Button>}
      </Stack>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <Dialog open={Boolean(cancelTarget)} onClose={() => { if (!busy) setCancelTarget(null); }} fullWidth maxWidth="sm" aria-labelledby="cancel-booking-title">
      <DialogTitle id="cancel-booking-title">Cancel booking?</DialogTitle>
      <DialogContent dividers>
        {cancelError && <Alert severity="error" sx={{ mb: 2 }}>{cancelError}</Alert>}
        <Typography variant="body2" sx={{ mb: 2 }}>Cancelling this booking will reopen order {cancelTarget?.order}. Only unstarted trips without financial records can be cancelled here.</Typography>
        <TextField fullWidth multiline minRows={2} label="Cancellation reason" value={reason} onChange={event => setReason(event.target.value)} slotProps={{ htmlInput: { maxLength: 500 } }}/>
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => setCancelTarget(null)}>Keep booking</Button>
        <Button color="error" variant="contained" disabled={busy || !reason.trim() || !cancelTarget} onClick={() => { if (cancelTarget) void cancel(cancelTarget.id); }}>{busy ? "Cancelling…" : "Cancel booking"}</Button>
      </DialogActions>
    </Dialog>
  </Box>;
}
