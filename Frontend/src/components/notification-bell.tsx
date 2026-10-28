"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import NextLink from "next/link";
import Badge from "@mui/material/Badge";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import Link from "@mui/material/Link";
import Alert from "@mui/material/Alert";
import { Bell, Check } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { canShowNavigation, type NavigationAccess } from "@/lib/navigation-access";
import { EmptyState } from "@/components/empty-state";
import { ContentSkeleton } from "@/components/content-skeleton";

type Notification = { id: string; read_at: string | null; created_at: string; payload: { title?: string; body?: string; link?: string } };
export function NotificationBell({ access }: { access: NavigationAccess | null }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [rows, setRows] = useState<Notification[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const fetching = useRef(false);
  const enabled = canShowNavigation("/notifications", access);
  const refresh = useCallback(async () => {
    if (!enabled || fetching.current) return;
    fetching.current = true;
    try {
      const response = await apiFetch("/notifications");
      if (!response.ok) throw new Error("Notifications could not load.");
      const data = await response.json();
      setRows(Array.isArray(data) ? data : data.results || []); setError("");
    } catch { setError("Notifications could not load. Retry to see current alerts."); }
    finally { fetching.current = false; setLoading(false); }
  }, [enabled]);
  useEffect(() => {
    if (!enabled) { setRows([]); return; }
    void refresh();
    const update = () => { if (!document.hidden) void refresh(); };
    const timer = window.setInterval(update, 30000);
    window.addEventListener("focus", update);
    return () => { clearInterval(timer); window.removeEventListener("focus", update); };
  }, [enabled, refresh]);
  if (!enabled) return null;
  const visible = rows.filter(row => {
    const href = row.payload.link || "/notifications";
    return href.startsWith("/") && !href.startsWith("//") && canShowNavigation(href.split(/[?#]/)[0], access);
  });
  const unread = visible.filter(row => !row.read_at).length;
  async function read(id: string) {
    setBusy(id);
    try {
      const response = await apiFetch(`/notifications/${id}/read`, { method: "PATCH" });
      if (!response.ok) throw new Error();
      const result = await response.json();
      setRows(current => current.map(row => row.id === id ? { ...row, read_at: result.read_at } : row));
    } catch { setError("Could not mark this notification as read. Please retry."); }
    finally { setBusy(""); }
  }
  return <>
    <IconButton aria-label={error ? "Notifications unavailable" : `Notifications, ${unread} unread`} aria-haspopup="dialog" aria-expanded={Boolean(anchor)} aria-controls={anchor ? "notification-preview" : undefined} onClick={event => { setAnchor(event.currentTarget); void refresh(); }}>
      <Badge badgeContent={error ? "!" : unread} color={error ? "warning" : "error"} max={99}><Bell size={20} /></Badge>
    </IconButton>
    <Popover id="notification-preview" open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }} slotProps={{ paper: { role: "dialog", "aria-label": "Notifications", sx: { width: 400, maxWidth: "calc(100vw - 24px)", maxHeight: "75vh", p: 2 } } }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}><Typography variant="h6">Notifications</Typography><Button onClick={() => void refresh()}>Refresh</Button></Stack>
      {error && <Alert severity="error">{error}</Alert>}
      {loading ? <ContentSkeleton variant="cards" rows={2} label="Loading notifications" /> : !visible.length ? <EmptyState title="No notifications yet" description="Your workspace alerts will appear here." /> : <List disablePadding>{visible.slice(0, 8).map(row => <ListItem key={row.id} disableGutters sx={{ borderBottom: "1px solid", borderColor: "divider", alignItems: "flex-start", gap: 1, py: 1.5 }}>
        <Stack spacing={0.5} sx={{ flex: 1, minWidth: 0 }}><Link component={NextLink} href={row.payload.link || "/notifications"} onClick={() => setAnchor(null)} sx={{ fontWeight: row.read_at ? 400 : 700 }}>{row.payload.title || "Workspace update"}</Link><Typography variant="body2" color="text.secondary">{row.payload.body}</Typography><Typography variant="caption" color="text.secondary">{new Date(row.created_at).toLocaleString()}</Typography></Stack>
        {!row.read_at && <IconButton size="small" disabled={Boolean(busy)} aria-label={`Mark ${row.payload.title || "notification"} as read`} onClick={() => void read(row.id)}><Check size={17} /></IconButton>}
      </ListItem>)}</List>}
      <Button fullWidth component={NextLink} href="/notifications" onClick={() => setAnchor(null)} sx={{ mt: 1 }}>View all notifications</Button>
    </Popover>
  </>;
}
