"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Alert, Box, Button, Checkbox, FormControlLabel, Paper, Stack, TextField, Typography } from "@mui/material";
import { Bell, Clock3, Gauge, RefreshCw } from "lucide-react";
import { AppLink } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";

type Settings = {
  low_margin_percent: string; fuel_efficiency_tolerance_percent: string;
  fuel_price_per_litre_alert: string; fuel_cost_per_km_alert: string; route_distance_anomaly_factor: string;
  auto_prepare_settlements: boolean; recipient_roles: string[]; escalation_hours: number | string; channels: string[];
  dock_free_minutes: number | string; detention_rate_per_hour: string; route_eta_enabled: boolean;
};

const roles = [
  ["OWNER", "Owner"], ["FINANCE", "Finance"], ["FLEET", "Fleet operations"], ["APPROVER", "Approver"],
  ["PURCHASE", "Purchasing"], ["STORE", "Stores"], ["AUDITOR", "Auditor"],
];
const channels = [["IN_APP", "In-app notifications"], ["EMAIL", "Email"]];
const sections = {
  reminders: ["escalation_hours", "recipient_roles", "channels"],
  alerts: ["low_margin_percent", "fuel_efficiency_tolerance_percent", "fuel_price_per_litre_alert", "fuel_cost_per_km_alert", "route_distance_anomaly_factor"],
  operations: ["auto_prepare_settlements", "route_eta_enabled", "dock_free_minutes", "detention_rate_per_hour"],
} satisfies Record<string, Array<keyof Settings>>;
type Section = keyof typeof sections;

function SettingsPanel({ title, description, icon, children, onSubmit, dirty, disabled, saving, error, notice }: {
  title: string; description: string; icon: ReactNode; children: ReactNode; onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  dirty: boolean; disabled: boolean; saving: boolean; error?: string; notice?: string;
}) {
  return <Paper component="form" variant="outlined" onSubmit={onSubmit} sx={{ p: { xs: 2, sm: 2.5 }, borderRadius: 3 }}>
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start", mb: 2.5 }}>
      <Box className="grid size-9 shrink-0 place-items-center rounded-lg bg-emerald-50 text-forest">{icon}</Box>
      <Box><Typography component="h2" variant="h6">{title}</Typography><Typography variant="body2" color="text.secondary">{description}</Typography></Box>
    </Stack>
    <fieldset disabled={disabled} className="m-0 min-w-0 space-y-4 border-0 p-0">{children}</fieldset>
    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
    {notice && <Alert severity="success" sx={{ mt: 2 }}>{notice}</Alert>}
    <Stack direction="row" useFlexGap spacing={1.5} sx={{ alignItems: "center", flexWrap: "wrap", mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
      <Button type="submit" variant="contained" disabled={disabled || !dirty}>{saving ? "Saving…" : "Save changes"}</Button>
      {dirty && <Typography variant="caption" color="text.secondary">Unsaved changes</Typography>}
    </Stack>
  </Paper>;
}

export default function FleetReminderSettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saved, setSaved] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<Section | null>(null);
  const [loadError, setLoadError] = useState("");
  const [feedback, setFeedback] = useState<{ section: Section; error?: string; notice?: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setLoadError(""); setFeedback(null);
    try {
      const response = await apiFetch("/fleet/reminder-settings");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load settings.");
      setSettings(data); setSaved(data);
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "Could not load settings.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  function update<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings(current => current && { ...current, [key]: value });
    setFeedback(null);
  }

  function changedKeys(section: Section) {
    return sections[section].filter(key => JSON.stringify(settings?.[key]) !== JSON.stringify(saved?.[key]));
  }

  async function save(event: FormEvent<HTMLFormElement>, section: Section) {
    event.preventDefault();
    if (!settings || saving || loading) return;
    const keys = changedKeys(section);
    if (!keys.length) return;
    if (section === "reminders" && (!settings.recipient_roles.length || !settings.channels.length)) {
      setFeedback({ section, error: "Choose at least one recipient role and one delivery channel." });
      return;
    }
    setSaving(section); setFeedback(null);
    try {
      const patch = Object.fromEntries(keys.map(key => [key,
        key === "escalation_hours" || key === "dock_free_minutes" ? Number(settings[key]) : settings[key],
      ]));
      const response = await apiFetch("/fleet/reminder-settings", { method: "PATCH", body: JSON.stringify(patch) });
      const data: Settings & { error?: string } = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save settings.");
      const values = Object.fromEntries(sections[section].map(key => [key, data[key]]));
      setSettings(current => current && { ...current, ...values });
      setSaved(current => current && { ...current, ...values });
      setFeedback({ section, notice: "Changes saved." });
    } catch (cause) {
      setFeedback({ section, error: cause instanceof Error ? cause.message : "Could not save settings." });
    } finally {
      setSaving(null);
    }
  }

  const hasChanges = (Object.keys(sections) as Section[]).some(section => changedKeys(section).length > 0);
  const panelProps = (section: Section) => ({
    onSubmit: (event: FormEvent<HTMLFormElement>) => void save(event, section),
    dirty: changedKeys(section).length > 0,
    disabled: loading || Boolean(saving),
    saving: saving === section,
    error: feedback?.section === section ? feedback.error : undefined,
    notice: feedback?.section === section ? feedback.notice : undefined,
  });
  const toggle = (key: "recipient_roles" | "channels", value: string) => {
    if (!settings) return;
    const list = settings[key];
    update(key, list.includes(value) ? list.filter(item => item !== value) : [...list, value]);
  };
  const numberField = (key: keyof Pick<Settings, "low_margin_percent" | "fuel_efficiency_tolerance_percent" | "fuel_price_per_litre_alert" | "fuel_cost_per_km_alert" | "route_distance_anomaly_factor" | "escalation_hours" | "dock_free_minutes" | "detention_rate_per_hour">, label: string, min: number, max: number, step: number | "any" = 1) =>
    <TextField required fullWidth size="small" type="number" label={label} value={settings?.[key] ?? ""}
      onChange={event => update(key, event.target.value)} slotProps={{ htmlInput: { min, max, step } }}/>;

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Settings</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Alerts and reminders</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Choose who gets reminders, how often overdue items are escalated, and when fleet alerts are raised.</Typography>
      </Box>
      <Button variant="outlined" startIcon={<RefreshCw size={16}/>} disabled={loading || Boolean(saving) || hasChanges} onClick={() => void load()}>Refresh settings</Button>
    </Stack>

    {loadError && <Alert severity="error">{loadError}</Alert>}
    {loading && !settings && <Typography role="status" variant="body2">Loading fleet settings…</Typography>}
    {settings && <>
      <SettingsPanel title="Reminders and follow-ups" description="Set the repeat interval for overdue items and choose how your team is notified." icon={<Bell size={18}/>} {...panelProps("reminders")}>
        <Box sx={{ maxWidth: 320 }}>{numberField("escalation_hours", "Repeat escalation after (hours)", 1, 720)}</Box>
        <Box component="fieldset" sx={{ border: 0, m: 0, p: 0 }}>
          <Typography component="legend" variant="subtitle2">Who receives reminders</Typography>
          <Box className="grid gap-x-4 sm:grid-cols-2 lg:grid-cols-4">
            {roles.map(([value, label]) => <FormControlLabel key={value} control={<Checkbox checked={settings.recipient_roles.includes(value)} onChange={() => toggle("recipient_roles", value)}/>} label={label}/>)}
          </Box>
        </Box>
        <Box component="fieldset" sx={{ border: 0, m: 0, p: 0 }}>
          <Typography component="legend" variant="subtitle2">Delivery channels</Typography>
          <Stack direction={{ xs: "column", sm: "row" }} useFlexGap spacing={1.5}>
            {channels.map(([value, label]) => <FormControlLabel key={value} control={<Checkbox checked={settings.channels.includes(value)} onChange={() => toggle("channels", value)}/>} label={label}/>)}
          </Stack>
        </Box>
      </SettingsPanel>

      <SettingsPanel title="Alert thresholds" description="Set when margins, fuel costs, or unusually long routes need a closer look." icon={<Gauge size={18}/>} {...panelProps("alerts")}>
        <Box className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {numberField("low_margin_percent", "Low trip margin (%)", 0, 100, "any")}
          {numberField("fuel_efficiency_tolerance_percent", "Below truck fuel baseline (%)", 0, 80, "any")}
          {numberField("fuel_price_per_litre_alert", "Fuel price above (₹/L)", 1, 10000, "any")}
          {numberField("fuel_cost_per_km_alert", "Fuel cost above (₹/km)", 1, 100000, "any")}
          {numberField("route_distance_anomaly_factor", "Route distance above typical (×)", 1.01, 10, "any")}
        </Box>
        <Typography variant="caption" color="text.secondary">A 20% fuel tolerance flags efficiency below 80% of the truck’s baseline. Route distance comparisons need at least three completed trips with odometer readings.</Typography>
      </SettingsPanel>

      <SettingsPanel title="Other fleet defaults" description="Manage salary draft preparation, route estimates, and dock waiting charges." icon={<Clock3 size={18}/>} {...panelProps("operations")}>
        <Stack spacing={1.5}>
          <Box>
            <FormControlLabel control={<Checkbox checked={settings.auto_prepare_settlements} onChange={event => update("auto_prepare_settlements", event.target.checked)}/>} label="Prepare monthly salary drafts automatically"/>
            <Typography variant="body2" color="text.secondary">Drafts use pay policies and approved trip earnings. Each draft still needs approval.</Typography>
          </Box>
          <Box>
            <FormControlLabel control={<Checkbox checked={settings.route_eta_enabled} onChange={event => update("route_eta_enabled", event.target.checked)}/>} label="Use Google road and traffic estimates"/>
            <Typography variant="body2" color="text.secondary">Uses the workspace’s configured Maps Routes account for dispatch and arrival estimates. Provider charges may apply.</Typography>
          </Box>
        </Stack>
        <Box className="grid gap-4 sm:grid-cols-2">
          {numberField("dock_free_minutes", "Free dock waiting time (minutes)", 0, 1440)}
          {numberField("detention_rate_per_hour", "Estimated dock waiting charge (₹/hour)", 0, 100000, .01)}
        </Box>
        <Typography variant="caption" color="text.secondary">The dock schedule uses these values to show estimated waiting charges.</Typography>
      </SettingsPanel>
    </>}
    <div className="flex flex-wrap gap-4 text-sm font-semibold text-forest">
      <AppLink href="/fleet/follow-ups">Open follow-ups</AppLink>
      <AppLink href="/fleet/alerts">Open trip alerts</AppLink>
    </div>
  </Box>;
}
