"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { OverviewVisualDashboard, type OverviewSummary } from "@/components/overview-visual-dashboard";
import type { NavigationAccess } from "@/lib/navigation-access";
import { accessToken, apiFetch } from "@/lib/api";

export default function Home() {
  const [summary, setSummary] = useState<OverviewSummary | null>(null);
  const [profile, setProfile] = useState<NavigationAccess | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const sequence = useRef(0);
  const load = useCallback(async (silent = false) => {
    const request = ++sequence.current;
    setRefreshing(true);
    try {
      if (!accessToken()) throw new Error("Sign in to load your workspace data.");
      const [summaryResponse, profileResponse] = await Promise.all([
        apiFetch("/dashboard/summary?analytics=1&days=30&include_recent=0"), apiFetch("/auth/me"),
      ]);
      if (!summaryResponse.ok || !profileResponse.ok)
        throw new Error(summaryResponse.status === 401 || profileResponse.status === 401
          ? "Your session has expired. Sign in again." : "Could not load workspace data.");
      const [summaryData, profileData] = await Promise.all([summaryResponse.json(), profileResponse.json()]);
      if (request !== sequence.current) return;
      setSummary(summaryData); setProfile(profileData); setMessage("");
    } catch (error) {
      if (request !== sequence.current) return;
      setMessage(error instanceof Error ? error.message : "Could not load workspace data.");
      if (silent) throw error;
    } finally {
      if (request === sequence.current) { setRefreshing(false); setLoading(false); }
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <OverviewVisualDashboard summary={summary} profile={profile} loading={loading} refreshing={refreshing} message={message} onRefresh={load} />;
}
