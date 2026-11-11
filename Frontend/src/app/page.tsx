"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { OverviewVisualDashboard, type FleetSnapshot, type OverviewSummary } from "@/components/overview-visual-dashboard";
import { canShowNavigation, type NavigationAccess } from "@/lib/navigation-access";
import { accessToken, apiFetch } from "@/lib/api";

export default function Home() {
  const [summary, setSummary] = useState<OverviewSummary | null>(null);
  const [profile, setProfile] = useState<NavigationAccess | null>(null);
  const [fleetSnapshot, setFleetSnapshot] = useState<FleetSnapshot | null>(null);
  const [fleetMessage, setFleetMessage] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const sequence = useRef(0);
  const load = useCallback(async (silent = false) => {
    const request = ++sequence.current;
    setRefreshing(true);
    try {
      if (!accessToken()) throw new Error("Sign in to load your workspace data.");
      const [summaryResponse, profileResponse] = await Promise.all([
        apiFetch(`/dashboard/summary?analytics=1&days=${days}&include_recent=0`), apiFetch("/auth/me"),
      ]);
      if (!summaryResponse.ok || !profileResponse.ok)
        throw new Error(summaryResponse.status === 401 || profileResponse.status === 401
          ? "Your session has expired. Sign in again." : "Could not load workspace data.");
      const [summaryData, profileData] = await Promise.all([summaryResponse.json(), profileResponse.json()]);
      if (request !== sequence.current) return;
      setSummary(summaryData); setProfile(profileData); setMessage("");
      if (canShowNavigation("/fleet", profileData)) {
        try {
          const trackingAllowed = canShowNavigation("/fleet/live-tracking", profileData);
          const [fleetResponse, trackingResponse] = await Promise.all([
            apiFetch("/fleet/dashboard"), trackingAllowed ? apiFetch("/fleet/live-locations") : Promise.resolve(null),
          ]);
          const fleetData = await fleetResponse.json();
          if (!fleetResponse.ok) throw new Error(fleetData.error || fleetData.detail || "Fleet summary is unavailable.");
          const trackingData = trackingResponse?.ok ? await trackingResponse.json() : null;
          if (request !== sequence.current) return;
          const locations = trackingData?.trips || [];
          setFleetSnapshot({
            ...fleetData,
            tracking_available: trackingAllowed && Boolean(trackingResponse?.ok),
            live_locations: trackingAllowed ? locations.filter((trip: { status: string }) => trip.status === "LIVE").length : null,
            stale_locations: trackingAllowed ? locations.filter((trip: { status: string }) => trip.status === "STALE").length : null,
            waiting_locations: trackingAllowed ? locations.filter((trip: { status: string }) => trip.status === "WAITING_FOR_GPS").length : null,
          });
          setFleetMessage(!trackingAllowed ? "Live GPS status is restricted for your role." : trackingResponse?.ok ? "" : "Live GPS status is unavailable right now.");
        } catch (error) {
          if (request !== sequence.current) return;
          setFleetSnapshot(null);
          setFleetMessage(error instanceof Error ? error.message : "Fleet summary is unavailable.");
        }
      } else {
        setFleetSnapshot(null);
        setFleetMessage("");
      }
    } catch (error) {
      if (request !== sequence.current) return;
      setMessage(error instanceof Error ? error.message : "Could not load workspace data.");
      if (silent) throw error;
    } finally {
      if (request === sequence.current) { setRefreshing(false); setLoading(false); }
    }
  }, [days]);
  useEffect(() => { void load(); }, [load]);

  return <OverviewVisualDashboard summary={summary} profile={profile} fleet={fleetSnapshot} fleetMessage={fleetMessage} loading={loading} refreshing={refreshing} message={message} days={days} onDaysChange={setDays} onRefresh={load} />;
}
