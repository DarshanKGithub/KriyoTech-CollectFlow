"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import NextLink from "next/link";
import { Alert, Box, Button, Chip, Divider, Drawer, FormControl, IconButton, InputAdornment, InputLabel, MenuItem, Select, Skeleton, TextField, Typography } from "@mui/material";
import { ArrowLeft, Clock3, FileSearch, RefreshCw, Search, ShieldCheck, X } from "lucide-react";
import { apiFetch } from "@/lib/api";

type AuditEvent = {
  id: string;
  actor: string;
  actor_email: string;
  action: string;
  object_type: string;
  object_id: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

function readable(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function dateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function AuditLogView() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [actionFilter, setActionFilter] = useState("all");
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/audit-logs");
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || data?.error || "Could not load audit events.");
      setEvents(Array.isArray(data) ? data as AuditEvent[] : []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load audit events.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const actions = useMemo(() => [...new Set(events.map(event => event.action))].sort(), [events]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return events.filter(event => {
      if (actionFilter !== "all" && event.action !== actionFilter) return false;
      if (!normalized) return true;
      return [event.actor, event.actor_email, event.action, event.object_type, event.object_id, JSON.stringify(event.metadata || {})]
        .some(value => value.toLowerCase().includes(normalized));
    });
  }, [events, query, actionFilter]);
  const actors = useMemo(() => new Set(events.map(event => event.actor_email || event.actor)).size, [events]);

  return <Box component="main" sx={{ minHeight: "calc(100dvh - 52px)", bgcolor: "background.default", px: { xs: 2, sm: 3, lg: 4 }, py: { xs: 2.5, sm: 3.5 } }}>
    <Box sx={{ width: "100%", minWidth: 0 }}>
      <Button component={NextLink} href="/" startIcon={<ArrowLeft size={15}/>} sx={{ mb: 2, px: 0, color: "text.secondary", fontWeight: 500 }}>Overview</Button>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 2, mb: 3 }}>
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
            <Box sx={{ width: 40, height: 40, display: "grid", placeItems: "center", borderRadius: 2, color: "primary.main", bgcolor: "action.selected" }}><ShieldCheck size={20}/></Box>
            <Box><Typography component="h1" sx={{ fontSize: 28, lineHeight: 1.2, fontWeight: 700, letterSpacing: "-.035em" }}>Audit log</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .35 }}>A record of changes and actions in this workspace.</Typography></Box>
          </Box>
        </Box>
        <Button variant="outlined" startIcon={<RefreshCw size={15}/>} onClick={() => void load()} disabled={loading}>Refresh</Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={() => void load()}>Try again</Button>}>{error}</Alert>}

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(3,minmax(0,1fr))" }, gap: 1.5, mb: 2.5 }}>
        {[
          { label: "Events shown", value: events.length, helper: "Most recent workspace activity" },
          { label: "People and systems", value: actors, helper: "Distinct actors in this list" },
          { label: "Latest activity", value: events[0] ? dateTime(events[0].created_at) : "—", helper: "Most recent recorded event" },
        ].map(item => <Box key={item.label} sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2, bgcolor: "background.paper" }}>
          <Typography variant="body2" color="text.secondary">{item.label}</Typography>
          <Typography sx={{ mt: .5, fontSize: item.label === "Latest activity" ? 17 : 24, lineHeight: 1.3, fontWeight: 650, fontVariantNumeric: "tabular-nums" }}>{loading ? "…" : item.value}</Typography>
          <Typography variant="caption" color="text.secondary">{item.helper}</Typography>
        </Box>)}
      </Box>

      <Box sx={{ overflow: "hidden", border: "1px solid", borderColor: "divider", borderRadius: 2.5, bgcolor: "background.paper" }}>
        <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5, p: { xs: 1.5, sm: 2 }, borderBottom: "1px solid", borderColor: "divider" }}>
          <TextField size="small" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search events, people, records…" aria-label="Search audit events" sx={{ flex: "1 1 280px", maxWidth: 460 }} slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search size={16}/></InputAdornment> } }}/>
          <FormControl size="small" sx={{ width: { xs: "100%", sm: 250 } }}>
            <InputLabel id="audit-action-label">Action</InputLabel>
            <Select labelId="audit-action-label" value={actionFilter} label="Action" onChange={event => setActionFilter(event.target.value)}>
              <MenuItem value="all">All actions</MenuItem>
              {actions.map(action => <MenuItem key={action} value={action}>{readable(action)}</MenuItem>)}
            </Select>
          </FormControl>
          <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>{loading ? "Loading…" : `${filtered.length} ${filtered.length === 1 ? "event" : "events"}`}</Typography>
        </Box>

        {loading ? <Box sx={{ p: 2 }}>{[0, 1, 2].map(item => <Skeleton key={item} height={72} sx={{ mb: 1 }}/>)}</Box> : filtered.length === 0 ? <Box sx={{ display: "grid", justifyItems: "center", textAlign: "center", px: 2, py: 8 }}>
          <Box sx={{ width: 44, height: 44, display: "grid", placeItems: "center", borderRadius: "50%", bgcolor: "action.hover", color: "text.secondary" }}><FileSearch size={21}/></Box>
          <Typography sx={{ mt: 1.5, fontWeight: 600 }}>{events.length ? "No matching events" : "No activity yet"}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>{events.length ? "Try a different search or action filter." : "Workspace changes will appear here when they are recorded."}</Typography>
        </Box> : <>
          <Box sx={{ display: { xs: "none", md: "grid" }, gridTemplateColumns: "minmax(190px,1.1fr) minmax(180px,1fr) minmax(140px,.7fr) minmax(190px,1fr) 150px 90px", gap: 2, px: 2.5, py: 1.25, bgcolor: "action.hover", color: "text.secondary" }}>
            {["Actor", "Activity", "Record", "Details", "Date and time", ""].map((label, index) => <Typography key={`${label}-${index}`} variant="caption" sx={{ fontWeight: 650, textTransform: "uppercase", letterSpacing: ".045em" }}>{label}</Typography>)}
          </Box>
          <Box>
            {filtered.map((event, index) => <Box key={event.id} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(190px,1.1fr) minmax(180px,1fr) minmax(140px,.7fr) minmax(190px,1fr) 150px 90px" }, alignItems: "center", gap: { xs: 1, md: 2 }, px: { xs: 2, sm: 2.5 }, py: { xs: 1.75, md: 1.5 }, borderTop: index ? "1px solid" : "none", borderColor: "divider", "&:hover": { bgcolor: "action.hover" } }}>
              <Box sx={{ minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{event.actor || "System"}</Typography><Typography variant="caption" color="text.secondary" noWrap>{event.actor_email || "Automated event"}</Typography></Box>
              <Box sx={{ minWidth: 0 }}><Chip size="small" label={readable(event.action)} sx={{ maxWidth: "100%", fontWeight: 600, bgcolor: "action.selected", "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" } }}/></Box>
              <Typography variant="body2" noWrap>{readable(event.object_type || "Record")}</Typography>
              <Typography variant="body2" color="text.secondary" noWrap sx={{ fontFamily: "ui-monospace, SFMono-Regular, monospace", fontSize: 12 }}>{event.object_id}</Typography>
              <Box sx={{ display: "flex", alignItems: "center", gap: .75, color: "text.secondary" }}><Clock3 size={14}/><Typography variant="caption">{dateTime(event.created_at)}</Typography></Box>
              <Button size="small" onClick={() => setSelected(event)} sx={{ justifySelf: { md: "end" } }}>Details</Button>
            </Box>)}
          </Box>
          <Divider/>
          <Box sx={{ px: 2.5, py: 1.5, display: "flex", justifyContent: "space-between", gap: 2 }}><Typography variant="caption" color="text.secondary">Showing up to 200 recent events.</Typography><Typography variant="caption" color="text.secondary">{filtered.length} shown</Typography></Box>
        </>}
      </Box>
    </Box>

    <Drawer anchor="right" open={Boolean(selected)} onClose={() => setSelected(null)} slotProps={{ paper: { sx: { width: { xs: "100%", sm: 480 }, maxWidth: "100%", p: 3 } } }}>
      {selected && <>
        <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}><Box><Typography variant="overline" color="text.secondary">Audit event</Typography><Typography component="h2" variant="h6" sx={{ mt: .25 }}>{readable(selected.action)}</Typography></Box><IconButton aria-label="Close event details" onClick={() => setSelected(null)}><X size={19}/></IconButton></Box>
        <Divider sx={{ my: 2 }}/>
        {[["Actor", selected.actor], ["Email", selected.actor_email || "—"], ["Record type", readable(selected.object_type || "Record")], ["Record ID", selected.object_id], ["Date and time", dateTime(selected.created_at)]].map(([label, value]) => <Box key={label} sx={{ mb: 2 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" sx={{ mt: .35, overflowWrap: "anywhere" }}>{value}</Typography></Box>)}
        <Typography variant="subtitle2" sx={{ mt: 1, mb: 1 }}>Event details</Typography>
        <Box component="pre" sx={{ m: 0, p: 1.5, maxHeight: "50vh", overflow: "auto", borderRadius: 1.5, bgcolor: "action.hover", fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(selected.metadata || {}, null, 2)}</Box>
      </>}
    </Drawer>
  </Box>;
}
