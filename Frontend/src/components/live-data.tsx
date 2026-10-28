"use client";

import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import { Pause, Play, RefreshCw } from "lucide-react";
import { accessToken } from "@/lib/api";

/** Near-live polling for the active page; never submits forms or repeats writes. */
export function LiveData({ onRefresh, interval = 15000, paused = false, compact = false }: {
  onRefresh: () => Promise<unknown>;
  interval?: number;
  paused?: boolean;
  compact?: boolean;
}) {
  const callback = useRef(onRefresh);
  callback.current = onRefresh;
  const pauseRef = useRef(paused);
  pauseRef.current = paused;
  const refreshRef = useRef<() => void>(() => {});
  const [userPaused, setUserPaused] = useState(false);
  const userPauseRef = useRef(false);
  const [environment, setEnvironment] = useState<"ready" | "offline" | "hidden" | "editing">("ready");
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let running = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout>;
    const state = () => !navigator.onLine ? "offline" : document.hidden ? "hidden" : document.activeElement?.closest("form") ? "editing" : "ready";
    const schedule = () => {
      clearTimeout(timer);
      if (active) timer = setTimeout(() => { void refresh(); }, Math.min(interval * 2 ** failures, 120000));
    };
    const refresh = async () => {
      if (!active || running) return;
      const current = state();
      setEnvironment(current);
      if (userPauseRef.current || pauseRef.current || current !== "ready" || !accessToken()) { schedule(); return; }
      running = true;
      clearTimeout(timer);
      setRefreshing(true);
      try {
        await callback.current();
        if (active) { failures = 0; setFailed(false); setUpdatedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })); }
      } catch {
        if (active) { failures = Math.min(failures + 1, 3); setFailed(true); }
      } finally {
        running = false;
        if (active) { setRefreshing(false); schedule(); }
      }
    };
    const syncEnvironment = () => { if (active) setEnvironment(state()); };
    const resume = () => { syncEnvironment(); void refresh(); };
    refreshRef.current = () => { void refresh(); };
    syncEnvironment();
    schedule();
    document.addEventListener("visibilitychange", resume);
    document.addEventListener("focusin", syncEnvironment);
    document.addEventListener("focusout", syncEnvironment);
    window.addEventListener("online", resume);
    window.addEventListener("offline", syncEnvironment);
    window.addEventListener("focus", resume);
    return () => {
      active = false;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", resume);
      document.removeEventListener("focusin", syncEnvironment);
      document.removeEventListener("focusout", syncEnvironment);
      window.removeEventListener("online", resume);
      window.removeEventListener("offline", syncEnvironment);
      window.removeEventListener("focus", resume);
    };
  }, [interval]);

  const stopped = userPaused || paused || environment !== "ready";
  const label = environment === "offline" ? "Offline" : environment === "editing" ? "Paused while editing" : paused || userPaused || environment === "hidden" ? "Updates paused" : failed ? "Refresh failed" : refreshing ? "Updating…" : "Auto refresh";
  if (compact) return <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
    <span role="status">{failed ? "Refresh failed · showing previous data" : environment === "offline" ? "Offline · showing previous data" : refreshing ? "Updating…" : stopped ? label : updatedAt ? `Updated ${updatedAt}` : `Updates every ${Math.round(interval / 1000)} seconds`}</span>
    <div><Button size="small" onClick={() => { userPauseRef.current = !userPauseRef.current; setUserPaused(userPauseRef.current); if (!userPauseRef.current) refreshRef.current(); }}>{userPaused ? "Resume" : "Pause"}</Button><Button size="small" disabled={refreshing || paused || environment !== "ready" || userPaused} onClick={() => refreshRef.current()} startIcon={<RefreshCw size={13}/>}>Refresh</Button></div>
  </div>;
  return <div className="my-4 rounded-xl border border-line bg-white px-3 py-2">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap items-center gap-3"><Chip size="small" label={label} color={failed || environment === "offline" ? "warning" : stopped ? "default" : "success"} variant="outlined" icon={refreshing ? <CircularProgress size={12} color="inherit"/> : undefined}/><span className="text-xs text-slate-500" role="status">{updatedAt ? `Last updated ${updatedAt} · ` : ""}{failed ? "Retrying with longer intervals" : `Checks every ${Math.round(interval / 1000)} seconds`}</span></div>
      <div className="flex gap-1"><Button size="small" onClick={() => { userPauseRef.current = !userPauseRef.current; setUserPaused(userPauseRef.current); if (!userPauseRef.current) refreshRef.current(); }} startIcon={userPaused ? <Play size={13}/> : <Pause size={13}/>}>{userPaused ? "Resume" : "Pause"}</Button><Button size="small" disabled={refreshing || paused || environment !== "ready" || userPaused} onClick={() => refreshRef.current()} startIcon={<RefreshCw size={13}/>}>Refresh now</Button></div>
    </div>
    {failed && <Alert severity="warning" sx={{ mt: 1 }}>Could not refresh. Last loaded data is still shown. Updates will retry automatically.</Alert>}
  </div>;
}

