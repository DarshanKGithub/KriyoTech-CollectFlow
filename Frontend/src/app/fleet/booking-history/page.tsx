"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Chip, Paper, Stack, TextField, Typography } from "@mui/material";
import { ArrowRight, ClipboardList, History, RefreshCw, Truck } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Booking = { id: string; status: string; order: string; customer: string; truck: string; proposed_amount: string; accepted_amount: string | null; trip: string | null; notes: string };

const money = (value: string | null) => value ? `₹${Number(value).toLocaleString("en-IN")}` : "—";
const statusColor = (status: string): "success" | "warning" | "default" | "error" => status === "BOOKED" ? "success" : status === "CANCELLED" ? "default" : status === "EXPIRED" ? "error" : "warning";

export default function BookingHistory() {
  const [rows, setRows] = useState<Booking[]>([]);
  const [error, setError] = useState("");
  const [reason, setReason] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
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
    try {
      const response = await apiFetch(`/fleet/booking-history/${id}/cancel`, { method: "POST", body: JSON.stringify({ reason: reason[id] }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Cancellation failed.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Cancellation failed."); }
    finally { setBusy(false); }
  }
  const filtered = useMemo(() => rows.filter(row => `${row.order} ${row.customer} ${row.truck} ${row.trip || ""} ${row.status}`.toLowerCase().includes(query.trim().toLowerCase())), [rows, query]);
  const booked = rows.filter(row => row.status === "BOOKED").length;
  const accepted = rows.filter(row => row.accepted_amount !== null).length;
  const metrics = [{ label: "Recorded offers", value: rows.length, Icon: History }, { label: "Booked", value: booked, Icon: Truck }, { label: "Accepted rates", value: accepted, Icon: ClipboardList }];

  return <Box component="main" sx={{ width: "100%", maxWidth: 1760, mx: "auto", p: { xs: 2, sm: 3, lg: 4 } }}>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "flex-end" } }}>
      <Box><Typography variant="overline" color="primary" sx={{ fontWeight: 700, letterSpacing: ".14em" }}>CUSTOMERS · RETURN LOADS</Typography><Typography variant="h4">Booking history</Typography><Typography color="text.secondary" sx={{ mt: .75, maxWidth: 760 }}>Review offered rates, accepted bookings and assigned trips. Cancelling an unstarted booking reopens its order and preserves the audit history.</Typography></Box>
      <Button startIcon={<RefreshCw size={16}/>} variant="outlined" onClick={() => void load()} disabled={loading}>Refresh history</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }} action={<Button color="inherit" size="small" onClick={() => void load()}>Retry</Button>}>{error}</Alert>}
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", lg: "repeat(3, minmax(0, 1fr))" }, gap: 1.5, mt: 3 }}>
      {metrics.map(({ label, value, Icon }) => <Paper key={label} variant="outlined" sx={{ p: 2, minWidth: 0 }}><Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start" }}><Box><Typography variant="body2" color="text.secondary">{label}</Typography><Typography variant="h5" sx={{ mt: .5, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{loading ? "—" : value}</Typography></Box><Box sx={{ display: "grid", placeItems: "center", width: 36, height: 36, borderRadius: 2, bgcolor: "action.hover", color: "primary.main" }}><Icon size={17}/></Box></Stack></Paper>)}
    </Box>
    <Paper variant="outlined" sx={{ mt: 2.5, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" }, p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box><Typography variant="subtitle1">Offers and bookings</Typography><Typography variant="caption" color="text.secondary">{loading ? "Loading records…" : `${filtered.length} of ${rows.length} records`}</Typography></Box>
        <TextField size="small" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search order, customer, truck…" slotProps={{ htmlInput: { "aria-label": "Search booking history" } }} sx={{ width: { xs: "100%", sm: 330 } }}/>
      </Stack>
      <Stack spacing={0}>
        {filtered.map(row => <Box key={row.id} sx={{ p: { xs: 2, sm: 2.5 }, borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 } }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", md: "flex-start" } }}>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}><Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{row.order}</Typography><Chip size="small" label={row.status.replaceAll("_", " ")} color={statusColor(row.status)}/></Stack>
              <Typography variant="body2" sx={{ mt: .75, fontWeight: 600 }}>{row.customer}</Typography>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: .75, color: "text.secondary" }}><Truck size={14}/><Typography variant="caption">{row.truck || "Truck not assigned"}</Typography>{row.trip && <><ArrowRight size={13}/><Typography variant="caption">{row.trip}</Typography></>}</Stack>
              {row.notes && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>{row.notes}</Typography>}
            </Box>
            <Stack direction="row" spacing={3} sx={{ flexShrink: 0 }}><Box><Typography variant="caption" color="text.secondary">Proposed</Typography><Typography variant="subtitle2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{money(row.proposed_amount)}</Typography></Box><Box><Typography variant="caption" color="text.secondary">Accepted</Typography><Typography variant="subtitle2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{money(row.accepted_amount)}</Typography></Box></Stack>
          </Stack>
          {row.status === "BOOKED" && <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { xs: "stretch", sm: "center" }, mt: 2 }}><TextField size="small" label="Cancellation reason" value={reason[row.id] || ""} onChange={event => setReason(current => ({ ...current, [row.id]: event.target.value }))} slotProps={{ htmlInput: { maxLength: 500 } }} sx={{ maxWidth: 460, flex: 1 }}/><Button color="warning" variant="outlined" disabled={busy || !reason[row.id]?.trim()} onClick={() => void cancel(row.id)}>Cancel unstarted booking</Button></Stack>}
        </Box>)}
        {!loading && filtered.length === 0 && <Box sx={{ p: 6, textAlign: "center" }}><History size={24} color="#9C9D89"/><Typography variant="subtitle2" sx={{ mt: 1 }}>{query ? "No matching bookings" : "No return-load offers yet"}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>{query ? "Try another order, customer, or vehicle." : "Accepted return-load offers will appear here with their trip and rate."}</Typography></Box>}
      </Stack>
    </Paper>
  </Box>;
}
