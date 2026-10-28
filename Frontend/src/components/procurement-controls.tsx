"use client";
import { UiAlert, UiBox, UiButton, UiDetails, UiForm, UiH2, UiInput, UiLabel, UiSection, UiSelect, UiSmall, UiSpan, UiStrong, UiSummary, UiText } from "@/components/product-ui";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
type Vendor = {
    id: string;
    name: string;
};
type POLine = {
    id: string;
    line_no: number;
    description: string;
    item_code: string;
    hsn_sac: string;
    quantity: string;
    received_quantity: string;
    remaining_quantity: string;
    maximum_receivable_quantity: string;
    uom: string;
    rate: string;
    taxable_value: string;
    gst_rate: string;
};
type PO = {
    id: string;
    number: string;
    vendor: string;
    vendor_id: string;
    order_date: string | null;
    status: string;
    revision: number;
    lines: POLine[];
};
type GRN = {
    id: string;
    number: string;
    vendor: string;
    quality_status: string;
    quality_note: string;
};
type POLineDraft = {
    key: string;
    description: string;
    item_code: string;
    hsn_sac: string;
    quantity: string;
    uom: string;
    rate: string;
    gst_rate: string;
};
type PORevision = {
    revision: number;
    action: string;
    change_note: string;
    snapshot: {
        status: string;
        vendor_name: string;
        order_date: string | null;
        lines: Array<{
            description: string;
            quantity: string;
            rate: string;
            gst_rate: string;
        }>;
    };
    changed_by: string | null;
    created_at: string;
};
const newLine = (): POLineDraft => ({ key: `${Date.now()}-${Math.random()}`, description: "", item_code: "", hsn_sac: "", quantity: "1", uom: "", rate: "0", gst_rate: "0" });
const messageOf = (data: {
    error?: string | {
        message?: string;
    };
}) => typeof data.error === "string" ? data.error : data.error?.message || "The request could not be completed.";
export function ProcurementControls({ kind }: {
    kind: "po" | "grn";
}) {
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [pos, setPos] = useState<PO[]>([]);
    const [grns, setGrns] = useState<GRN[]>([]);
    const [poNumber, setPoNumber] = useState("");
    const [vendorId, setVendorId] = useState("");
    const [orderDate, setOrderDate] = useState(new Date().toISOString().slice(0, 10));
    const [lines, setLines] = useState<POLineDraft[]>([newLine()]);
    const [changeNote, setChangeNote] = useState("");
    const [editingPO, setEditingPO] = useState<PO | null>(null);
    const [history, setHistory] = useState<Record<string, PORevision[]>>({});
    const [historyOpen, setHistoryOpen] = useState("");
    const [poId, setPoId] = useState("");
    const [grnNumber, setGrnNumber] = useState("");
    const [receipts, setReceipts] = useState<Record<string, string>>({});
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState(false);
    async function load() {
        const [v, p, g] = await Promise.all([apiFetch("/vendors"), apiFetch("/purchase-orders"), apiFetch("/grns")]);
        if (v.ok)
            setVendors(await v.json());
        if (p.ok)
            setPos(await p.json());
        if (g.ok)
            setGrns(await g.json());
    }
    useEffect(() => { void load(); }, []);
    function changed() { window.dispatchEvent(new Event("kriyopay:data-changed")); void load(); }
    function editPO(po: PO) {
        setEditingPO(po);
        setPoNumber(po.number);
        setVendorId(po.vendor_id);
        setOrderDate(po.order_date || "");
        setLines(po.lines.map(line => ({ key: line.id, description: line.description, item_code: line.item_code || "", hsn_sac: line.hsn_sac || "", quantity: line.quantity, uom: line.uom || "", rate: line.rate, gst_rate: line.gst_rate || "0" })));
        setChangeNote("");
        setNotice(`Editing draft ${po.number} · revision ${po.revision}.`);
        document.getElementById("po-editor")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    function cancelEdit() {
        setEditingPO(null);
        setPoNumber("");
        setVendorId("");
        setOrderDate(new Date().toISOString().slice(0, 10));
        setLines([newLine()]);
        setChangeNote("");
    }
    async function savePO(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setNotice("");
        const payloadLines = lines.map(({ key: _key, ...line }) => line);
        const response = editingPO
            ? await apiFetch("/purchase-orders", { method: "PATCH", body: JSON.stringify({ purchase_order_id: editingPO.id, action: "edit", vendor_id: vendorId, order_date: orderDate || null, lines: payloadLines, change_note: changeNote }) })
            : await apiFetch("/purchase-orders", { method: "POST", body: JSON.stringify({ vendor_id: vendorId, number: poNumber, order_date: orderDate || null, lines: payloadLines }) });
        const data = await response.json();
        setNotice(response.ok ? (editingPO ? `Saved revision ${data.revision} of ${editingPO.number}.` : "Purchase order saved as a draft.") : messageOf(data));
        setBusy(false);
        if (response.ok) {
            cancelEdit();
            changed();
        }
    }
    async function poAction(id: string, action: string) {
        const response = await apiFetch("/purchase-orders", { method: "PATCH", body: JSON.stringify({ purchase_order_id: id, action }) });
        const data = await response.json();
        setNotice(response.ok ? `Purchase order ${data.status.toLowerCase().replaceAll("_", " ")}.` : messageOf(data));
        if (response.ok)
            changed();
    }
    async function toggleHistory(po: PO) {
        if (historyOpen === po.id) {
            setHistoryOpen("");
            return;
        }
        setHistoryOpen(po.id);
        if (history[po.id])
            return;
        const response = await apiFetch(`/purchase-orders/${po.id}/revisions`);
        if (!response.ok) {
            setNotice("Could not load purchase order history.");
            return;
        }
        const revisions = await response.json();
        setHistory(old => ({ ...old, [po.id]: revisions }));
    }
    async function createGRN(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const po = pos.find(item => item.id === poId);
        if (!po)
            return;
        const receiptLines = po.lines.map(line => ({ purchase_order_line_id: line.id, quantity_received: receipts[line.id] || "0" })).filter(line => Number(line.quantity_received) > 0);
        if (!receiptLines.length) {
            setNotice("Enter a received quantity for at least one PO line.");
            return;
        }
        setBusy(true);
        const response = await apiFetch("/grns", { method: "POST", body: JSON.stringify({ purchase_order_id: poId, number: grnNumber, received_at: new Date().toISOString().slice(0, 10), lines: receiptLines }) });
        const data = await response.json();
        setNotice(response.ok ? "Goods receipt saved. Quality status is pending." : messageOf(data));
        setBusy(false);
        if (response.ok) {
            setGrnNumber("");
            setReceipts({});
            changed();
        }
    }
    async function quality(grn: GRN, value: string) {
        const response = await apiFetch("/grns", { method: "PATCH", body: JSON.stringify({ grn_id: grn.id, quality_status: value, quality_note: grn.quality_note || "" }) });
        const data = await response.json();
        setNotice(response.ok ? "Receipt quality status updated." : messageOf(data));
        if (response.ok)
            changed();
    }
    return <UiSection className="mt-6 w-full min-w-0 space-y-5 px-5">
    <UiBox id="po-editor" className="rounded-xl border border-line bg-white p-5">
      <UiH2 className="text-sm font-bold">{kind === "po" ? (editingPO ? `Edit draft ${editingPO.number}` : "Create a purchase order") : "Record a goods receipt"}</UiH2>
      <UiText className="mt-1 text-xs text-slate-500">{kind === "po" ? "Create multi-line drafts, then submit for separate finance approval. Every saved edit records a numbered snapshot and reason." : "Only approved purchase orders can be received. Prior receipts reduce each line balance."}</UiText>
      {kind === "po" ? <UiForm onSubmit={savePO} className="mt-4 space-y-4">
        <UiBox className="grid gap-3 md:grid-cols-3">
          <UiSelect required value={vendorId} onChange={event => setVendorId(event.target.value)} className="rounded-lg border border-line px-3 py-2 text-sm"><option value="">Select vendor</option>{vendors.map(vendor => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</UiSelect>
          <UiInput required disabled={!!editingPO} placeholder="PO number" value={poNumber} onChange={event => setPoNumber(event.target.value)} className="rounded-lg border border-line px-3 py-2 text-sm disabled:bg-slate-50"/>
          <UiInput type="date" aria-label="PO order date" value={orderDate} onChange={event => setOrderDate(event.target.value)} className="rounded-lg border border-line px-3 py-2 text-sm"/>
        </UiBox>
        <UiBox className="space-y-2">{lines.map((line, index) => <UiBox key={line.key} className="grid gap-2 rounded-lg border border-line bg-slate-50 p-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr_1fr_auto]">
          <UiInput required aria-label={`Description for PO line ${index + 1}`} placeholder="Item or service description" value={line.description} onChange={event => setLines(old => old.map((item, i) => i === index ? { ...item, description: event.target.value } : item))} className="rounded border border-line bg-white px-2.5 py-2 text-sm"/>
          <UiInput aria-label={`Item code for PO line ${index + 1}`} placeholder="Item code" value={line.item_code} onChange={event => setLines(old => old.map((item, i) => i === index ? { ...item, item_code: event.target.value } : item))} className="rounded border border-line bg-white px-2.5 py-2 text-sm"/>
          <UiInput aria-label={`HSN or SAC for PO line ${index + 1}`} placeholder="HSN / SAC" value={line.hsn_sac} onChange={event => setLines(old => old.map((item, i) => i === index ? { ...item, hsn_sac: event.target.value } : item))} className="rounded border border-line bg-white px-2.5 py-2 text-sm"/>
          <UiInput required type="number" min="0.000001" step="any" aria-label={`Quantity for PO line ${index + 1}`} placeholder="Qty" value={line.quantity} onChange={event => setLines(old => old.map((item, i) => i === index ? { ...item, quantity: event.target.value } : item))} className="rounded border border-line bg-white px-2.5 py-2 text-sm"/>
          <UiInput required type="number" min="0" step="any" aria-label={`Rate for PO line ${index + 1}`} placeholder="Rate" value={line.rate} onChange={event => setLines(old => old.map((item, i) => i === index ? { ...item, rate: event.target.value } : item))} className="rounded border border-line bg-white px-2.5 py-2 text-sm"/>
          <UiInput type="number" min="0" max="100" step="any" aria-label={`GST percent for PO line ${index + 1}`} placeholder="GST %" value={line.gst_rate} onChange={event => setLines(old => old.map((item, i) => i === index ? { ...item, gst_rate: event.target.value } : item))} className="rounded border border-line bg-white px-2.5 py-2 text-sm"/>
          <UiInput aria-label={`Unit of measure for PO line ${index + 1}`} placeholder="UOM" value={line.uom} onChange={event => setLines(old => old.map((item, i) => i === index ? { ...item, uom: event.target.value } : item))} className="rounded border border-line bg-white px-2.5 py-2 text-sm"/>
          <UiButton type="button" disabled={lines.length === 1} onClick={() => setLines(old => old.filter((_, i) => i !== index))} aria-label={`Remove PO line ${index + 1}`} className="rounded border border-line bg-white px-3 py-2 text-xs disabled:opacity-40">Remove</UiButton>
        </UiBox>)}</UiBox>
        <UiButton type="button" disabled={lines.length >= 50} onClick={() => setLines(old => [...old, newLine()])} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold disabled:opacity-50">Add line</UiButton>
        {editingPO && <UiLabel className="block text-xs font-semibold">Change reason<UiInput required minLength={8} maxLength={500} value={changeNote} onChange={event => setChangeNote(event.target.value)} placeholder="Explain what changed and why" className="mt-1.5 min-h-10 w-full rounded-lg border border-line px-3 text-sm font-normal"/></UiLabel>}
        <UiBox className="flex flex-wrap gap-2"><UiButton disabled={busy} className="rounded-lg bg-forest px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : editingPO ? `Save revision ${editingPO.revision + 1}` : "Save draft"}</UiButton>{editingPO && <UiButton type="button" onClick={cancelEdit} className="rounded-lg border border-line px-4 py-2 text-xs font-semibold">Cancel edit</UiButton>}</UiBox>
      </UiForm> : <UiForm onSubmit={createGRN} className="mt-4 space-y-3"><UiBox className="grid gap-3 md:grid-cols-3"><UiSelect required value={poId} onChange={event => { setPoId(event.target.value); setReceipts({}); }} className="rounded-lg border border-line px-3 py-2 text-sm"><option value="">Select approved PO</option>{pos.filter(po => po.status === "APPROVED").map(po => <option key={po.id} value={po.id}>{po.number} · {po.vendor}</option>)}</UiSelect><UiInput required placeholder="GRN number" value={grnNumber} onChange={event => setGrnNumber(event.target.value)} className="rounded-lg border border-line px-3 py-2 text-sm"/><UiButton disabled={busy || !poId} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Record receipt</UiButton></UiBox>{pos.find(po => po.id === poId)?.lines.map(line => <UiLabel key={line.id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm"><UiSpan>{line.description} <UiSmall className="text-slate-400">Ordered {line.quantity} · received {line.received_quantity} · remaining {line.remaining_quantity}</UiSmall></UiSpan><UiInput type="number" min="0" max={Math.max(0, Number(line.maximum_receivable_quantity) - Number(line.received_quantity))} step="any" placeholder="Qty received" aria-label={`Received quantity for ${line.description}`} value={receipts[line.id] || ""} onChange={event => setReceipts(old => ({ ...old, [line.id]: event.target.value }))} className="w-36 rounded border border-line px-2 py-1.5"/></UiLabel>)}</UiForm>}
      {notice && <UiAlert role="status" className="mt-3 text-xs text-slate-600">{notice}</UiAlert>}
    </UiBox>

    {kind === "po" && <UiBox className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Approval queue</UiH2><UiBox className="mt-3 divide-y divide-line">{pos.map(po => <UiBox key={po.id} className="py-3 text-sm"><UiBox className="flex flex-wrap items-center justify-between gap-3"><UiSpan><UiStrong>{po.number}</UiStrong> · {po.vendor}<UiSmall className="ml-2 text-slate-500">{po.status.replaceAll("_", " ")} · revision {po.revision}</UiSmall></UiSpan><UiSpan className="flex flex-wrap gap-2">{po.status === "DRAFT" && <><UiButton onClick={() => editPO(po)} className="rounded border px-3 py-1.5 text-xs">Edit draft</UiButton><UiButton onClick={() => void poAction(po.id, "submit")} className="rounded border px-3 py-1.5 text-xs">Submit</UiButton></>}{po.status === "PENDING_APPROVAL" && <><UiButton onClick={() => void poAction(po.id, "approve")} className="rounded bg-forest px-3 py-1.5 text-xs text-white">Approve</UiButton><UiButton onClick={() => void poAction(po.id, "reject")} className="rounded border px-3 py-1.5 text-xs">Reject</UiButton></>}<UiButton onClick={() => void toggleHistory(po)} className="rounded border px-3 py-1.5 text-xs">{historyOpen === po.id ? "Hide history" : "Version history"}</UiButton></UiSpan></UiBox>
      {historyOpen === po.id && <UiBox className="mt-3 space-y-2 rounded-lg bg-slate-50 p-3">{(history[po.id] || []).map(revision => <UiDetails key={revision.revision} className="rounded border border-line bg-white p-3"><UiSummary className="cursor-pointer text-xs font-semibold">Revision {revision.revision} · {revision.action.toLowerCase()} · {new Date(revision.created_at).toLocaleString()}</UiSummary><UiText className="mt-2 text-[11px] text-slate-500">{revision.change_note || "No change note"} · {revision.changed_by || "System import"} · {revision.snapshot.vendor_name} · {revision.snapshot.lines.length} line(s)</UiText><ul className="mt-2 space-y-1 text-[11px] text-slate-600">{revision.snapshot.lines.map((line, index) => <li key={`${revision.revision}-${index}`}>{line.description} · qty {line.quantity} · rate ₹{line.rate} · GST {line.gst_rate}%</li>)}</ul></UiDetails>)}{!history[po.id]?.length && <UiText className="text-xs text-slate-500">No version snapshots available.</UiText>}</UiBox>}</UiBox>)}{!pos.length && <UiText className="py-5 text-xs text-slate-500">No purchase orders yet.</UiText>}</UiBox></UiBox>}
    {kind === "grn" && <UiBox className="rounded-xl border border-line bg-white p-5"><UiH2 className="text-sm font-bold">Receipt quality review</UiH2><UiBox className="mt-3 divide-y divide-line">{grns.map(grn => <UiBox key={grn.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><UiSpan><UiStrong>{grn.number}</UiStrong> · {grn.vendor}</UiSpan><UiSelect aria-label={`Quality status for ${grn.number}`} value={grn.quality_status} onChange={event => void quality(grn, event.target.value)} className="rounded border border-line px-2 py-1.5 text-xs">{["PENDING", "ACCEPTED", "PARTIAL", "REJECTED"].map(value => <option key={value} value={value}>{value}</option>)}</UiSelect></UiBox>)}{!grns.length && <UiText className="py-5 text-xs text-slate-500">No receipt records yet.</UiText>}</UiBox></UiBox>}
  </UiSection>;
}
