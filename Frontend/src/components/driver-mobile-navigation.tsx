"use client";

import { useEffect, useState } from "react";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import Paper from "@mui/material/Paper";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Truck, MapPin, Receipt, UserRound } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { ContentSkeleton } from "@/components/content-skeleton";

export type DriverTab = "trips" | "checkin" | "receipts" | "profile";
export function DriverMobileNavigation({ value, onChange }: { value: DriverTab; onChange: (value: DriverTab) => void }) {
  return <Paper component="nav" aria-label="Driver workspace" elevation={4} sx={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 1100, pb: "env(safe-area-inset-bottom)", display: { xs: "block", lg: "none" } }}>
    <BottomNavigation showLabels value={value} onChange={(_, next: DriverTab) => onChange(next)}>
      <BottomNavigationAction label="Trips" value="trips" icon={<Truck size={20} />} /><BottomNavigationAction label="Check-in" value="checkin" icon={<MapPin size={20} />} /><BottomNavigationAction label="Receipts" value="receipts" icon={<Receipt size={20} />} /><BottomNavigationAction label="Profile" value="profile" icon={<UserRound size={20} />} />
    </BottomNavigation>
  </Paper>;
}

export function DriverProfile() {
  const [profile, setProfile] = useState<{ name: string; email: string; role: string; tenant: string } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    apiFetch("/auth/me").then(async response => { if (!response.ok) throw new Error(); const data = await response.json(); if (active) setProfile(data); }).catch(() => { if (active) setError("Could not load your profile."); });
    return () => { active = false; };
  }, [attempt]);
  if (error) return <Alert severity="error" action={<Button color="inherit" onClick={() => setAttempt(current => current + 1)}>Retry</Button>}>{error}</Alert>;
  if (!profile) return <ContentSkeleton variant="form" label="Loading your profile" />;
  return <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h6">My profile</Typography><Stack spacing={2} sx={{ mt: 2 }}>{[["Name", profile.name || "—"], ["Email", profile.email], ["Company", profile.tenant], ["Role", profile.role]].map(([label, value]) => <Stack key={label}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography>{value}</Typography></Stack>)}</Stack></Paper>;
}
