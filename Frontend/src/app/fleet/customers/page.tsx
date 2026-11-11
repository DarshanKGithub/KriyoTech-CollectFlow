"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { ClipboardList, Pencil, Plus, RefreshCw, UsersRound } from "lucide-react";
import { AppLink } from "@/components/product-ui";
import { useListPagination } from "@/components/list-pagination";
import { apiFetch } from "@/lib/api";

type Customer = {
  id: string;
  name: string;
  contact_name: string;
  email: string;
  phone: string;
  gstin: string;
  billing_address: string;
  status: string;
  notes: string;
  dock_free_minutes: number | null;
  detention_rate_per_hour: string | null;
};
type DialogView = "add" | "edit" | "details" | "terms";
const statuses = [{ value: "", label: "All customers" }, { value: "ACTIVE", label: "Active" }, { value: "INACTIVE", label: "Inactive" }];
const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

function responseError(data: Record<string, unknown> | null, fallback: string) {
  if (!data) return fallback;
  if (typeof data.error === "string") return data.error;
  if (typeof data.detail === "string") return data.detail;
  return Object.entries(data).flatMap(([field, errors]) => Array.isArray(errors)
    ? errors.filter(value => typeof value === "string").map(value => `${field.replaceAll("_", " ")}: ${value}`)
    : []).join(" ") || fallback;
}

export default function FleetCustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [view, setView] = useState<DialogView | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const selected = customers.find(customer => customer.id === selectedId);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/fleet/customers");
      const result = await response.json().catch(() => null);
      if (!response.ok || !Array.isArray(result)) throw new Error(responseError(result, "Could not load customers."));
      setCustomers(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load customers.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  function openDialog(next: DialogView, customer?: Customer) {
    setDialogError("");
    setSelectedId(customer?.id || "");
    setView(next);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || (view !== "add" && view !== "edit" && view !== "terms")) return;
    const form = new FormData(event.currentTarget);
    const creating = view === "add";
    if (!creating && !selected) return;
    const free = form.get("free");
    const data = view !== "terms" ? Object.fromEntries(form.entries()) : {
      dock_free_minutes: free === "" ? null : Number(free),
      detention_rate_per_hour: form.get("rate") || null,
    };
    setBusy(true);
    setDialogError("");
    setNotice("");
    try {
      const response = await apiFetch(creating ? "/fleet/customers" : `/fleet/customers/${selected?.id}`, {
        method: creating ? "POST" : "PATCH",
        body: JSON.stringify(data),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(result, view === "terms" ? "Could not save waiting charges." : "Could not save customer."));
      if (creating) {
        setCustomers(current => [...current, result].sort((a, b) => a.name.localeCompare(b.name)));
        setStatus("");
        setSearch("");
        setNotice(`${result.name} was added to the directory.`);
        openDialog("details", result);
      } else {
        setCustomers(current => current.map(customer => customer.id === result.id ? result : customer));
        setNotice(view === "terms" ? "Waiting charges saved for future check-ins." : `${result.name}’s contact and billing details were updated.`);
        setView(null);
      }
    } catch (cause) {
      setDialogError(cause instanceof Error ? cause.message : "Could not save customer information.");
    } finally {
      setBusy(false);
    }
  }

  const query = search.trim().toLowerCase();
  const filtered = customers.filter(customer => (!status || customer.status === status) &&
    [customer.name, customer.contact_name, customer.email, customer.phone, customer.gstin].join(" ").toLowerCase().includes(query));
  const page = useListPagination(filtered, `${search}:${status}`, "Customer directory pages");
  const activeCount = customers.filter(customer => customer.status === "ACTIVE").length;

  return <Box component="main" className="w-full min-w-0 space-y-5 px-4 py-7 sm:px-6 lg:px-8">
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
      <Box>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>Fleet · Customers</Typography>
        <Typography component="h1" variant="h4" sx={{ fontWeight: 750 }}>Customers</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .75 }}>Find customer contacts, billing details, and waiting charges for transport orders.</Typography>
      </Box>
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button component={AppLink} href="/fleet/orders" variant="outlined" startIcon={<ClipboardList size={16}/>}>Transport orders</Button>
        <Button variant="outlined" startIcon={<RefreshCw size={16}/>} disabled={loading || busy} onClick={() => void refresh()}>Refresh</Button>
        <Button variant="contained" startIcon={<Plus size={16}/>} disabled={loading || busy} onClick={() => openDialog("add")}>Add customer</Button>
      </Stack>
    </Stack>

    {error && <Alert severity="error">{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}

    <Paper component="section" variant="outlined" sx={{ borderRadius: 3, overflow: "hidden" }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box>
          <Typography component="h2" variant="h6">Customer directory</Typography>
          <Typography variant="body2" color="text.secondary" aria-live="polite">
            {loading ? "Loading customers…" : `${filtered.length} shown · ${customers.length} total · ${activeCount} active`}
          </Typography>
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField size="small" label="Search customers" placeholder="Name, contact, phone, or GSTIN" value={search} onChange={event => setSearch(event.target.value)} sx={{ minWidth: { sm: 245 } }}/>
          <TextField select size="small" label="Status" value={status} onChange={event => setStatus(event.target.value)} sx={{ minWidth: 150 }}>
            {statuses.map(item => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
          </TextField>
        </Stack>
      </Stack>
      {loading && <LinearProgress aria-label="Loading customer directory"/>}

      {page.rows.map(customer => <Box component="article" key={customer.id} sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0,1fr) minmax(0,1fr) auto" }, gap: 2, alignItems: "center" }}>
          <Stack direction="row" spacing={1.5} sx={{ minWidth: 0, alignItems: "center" }}>
            <Box className="grid size-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-forest"><UsersRound size={18} aria-hidden="true"/></Box>
            <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
              <Typography component="h3" variant="subtitle1" sx={{ fontWeight: 700 }}>{customer.name}</Typography>
              <Chip size="small" color={customer.status === "ACTIVE" ? "success" : "default"} label={customer.status === "ACTIVE" ? "Active" : "Inactive"}/>
            </Box>
          </Stack>
          <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
            {customer.contact_name && <Typography variant="body2" sx={{ fontWeight: 600 }}>{customer.contact_name}</Typography>}
            {customer.phone && <Typography variant="body2" color="text.secondary">{customer.phone}</Typography>}
            {customer.email && <Typography variant="body2" color="text.secondary">{customer.email}</Typography>}
            {!customer.contact_name && !customer.phone && !customer.email && <Typography variant="body2" color="text.secondary">No contact details</Typography>}
          </Box>
          <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
            <Button size="small" onClick={() => openDialog("details", customer)} aria-label={`View details for ${customer.name}`}>View details</Button>
            <Button variant="outlined" size="small" startIcon={<Pencil size={14}/>} disabled={loading || busy}
              onClick={() => openDialog("edit", customer)} aria-label={`Edit customer ${customer.name}`}>Edit customer</Button>
          </Stack>
        </Box>
      </Box>)}

      {!loading && !error && !filtered.length && <Stack spacing={1} sx={{ p: 5, textAlign: "center", alignItems: "center" }}>
        <UsersRound size={24} aria-hidden="true"/>
        <Typography variant="subtitle2">{customers.length ? "No matching customers" : "No customers yet"}</Typography>
        <Typography variant="body2" color="text.secondary">{customers.length ? "Try another search or status." : "Add your first customer to start creating transport orders."}</Typography>
        {customers.length ? <Button onClick={() => { setSearch(""); setStatus(""); }}>Clear filters</Button> :
          <Button variant="outlined" onClick={() => openDialog("add")}>Add customer</Button>}
      </Stack>}
      {filtered.length > 10 && page.controls}
    </Paper>

    <Dialog open={Boolean(view)} onClose={() => { if (!busy) setView(null); }} fullWidth maxWidth="sm" aria-labelledby="customer-dialog-title">
      <DialogTitle id="customer-dialog-title">{view === "add" ? "Add customer" : view === "edit" ? "Edit customer" : view === "terms" ? "Edit waiting charges" : selected?.name || "Customer details"}</DialogTitle>
      <DialogContent dividers>
        {dialogError && <Alert severity="error" sx={{ mb: 2 }}>{dialogError}</Alert>}
        {(view === "add" || (view === "edit" && selected)) && <Stack id="customer-form" key={`${view}:${selectedId}`} component="form" spacing={2} onSubmit={save}>
          {view === "add" ? <TextField autoFocus required label="Business or customer name" name="name" slotProps={{ htmlInput: { maxLength: 180 } }}/> :
            <Typography variant="subtitle2">{selected?.name}</Typography>}
          <TextField autoFocus={view === "edit"} label="Contact person" name="contact_name" defaultValue={selected?.contact_name ?? ""} slotProps={{ htmlInput: { maxLength: 160 } }}/>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField fullWidth label="Phone" name="phone" type="tel" defaultValue={selected?.phone ?? ""} slotProps={{ htmlInput: { maxLength: 32 } }}/>
            <TextField fullWidth label="Email" name="email" type="email" defaultValue={selected?.email ?? ""}/>
          </Stack>
          <TextField label="GSTIN" name="gstin" defaultValue={selected?.gstin ?? ""} slotProps={{ htmlInput: { maxLength: 15 } }}/>
          <TextField label="Billing address" name="billing_address" defaultValue={selected?.billing_address ?? ""} multiline minRows={2}/>
          {view === "add" && <TextField label="Notes" name="notes" multiline minRows={2}/>}
        </Stack>}
        {view === "details" && selected && <Stack spacing={2}>
          <Box component="dl" className="m-0 grid gap-3 sm:grid-cols-2">
            {[["Contact person", selected.contact_name], ["Phone", selected.phone], ["Email", selected.email],
              ["GSTIN", selected.gstin], ["Billing address", selected.billing_address], ["Notes", selected.notes]].map(([label, value]) =>
              <Box key={label} sx={{ minWidth: 0, p: 1.25, borderRadius: 2, bgcolor: "action.hover" }}>
                <Typography component="dt" variant="caption" color="text.secondary">{label}</Typography>
                <Typography component="dd" variant="body2" sx={{ m: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{value || "Not added"}</Typography>
              </Box>)}
          </Box>
          <Box sx={{ borderTop: 1, borderColor: "divider", pt: 2 }}>
            <Typography variant="subtitle2">Waiting charges</Typography>
            <Typography variant="body2" color="text.secondary">Free waiting time · {selected.dock_free_minutes == null ? "Workspace default" : `${selected.dock_free_minutes} min`}</Typography>
            <Typography variant="body2" color="text.secondary">Charge after free time · {selected.detention_rate_per_hour == null ? "Workspace default" : `${currency.format(Number(selected.detention_rate_per_hour))} per hour`}</Typography>
          </Box>
        </Stack>}
        {view === "terms" && selected && <Stack id="customer-form" key={selected.id} component="form" spacing={2} onSubmit={save}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>{selected.name}</Typography>
          <Typography variant="body2" color="text.secondary">These terms apply to new dock check-ins. Leave a field blank to use the workspace default.</Typography>
          <TextField type="number" label="Free waiting time (minutes)" name="free" defaultValue={selected.dock_free_minutes ?? ""} slotProps={{ htmlInput: { min: 0, max: 1440, step: 1 } }}/>
          <TextField type="number" label="Waiting charge (₹ per hour)" name="rate" defaultValue={selected.detention_rate_per_hour ?? ""} slotProps={{ htmlInput: { min: 0, max: 100000, step: 0.01 } }}/>
        </Stack>}
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={() => { setDialogError(""); setView(view === "terms" ? "details" : null); }}>{view === "details" ? "Close" : "Cancel"}</Button>
        {view === "details" ? <Button variant="outlined" disabled={loading || busy || !selected} onClick={() => setView("terms")}>Edit waiting charges</Button> :
          <Button variant="contained" type="submit" form="customer-form" disabled={busy}>{busy ? "Saving…" : view === "edit" ? "Save changes" : view === "terms" ? "Save waiting charges" : "Save customer"}</Button>}
      </DialogActions>
    </Dialog>
  </Box>;
}
