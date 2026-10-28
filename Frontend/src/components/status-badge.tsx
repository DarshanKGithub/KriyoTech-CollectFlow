import { UiSpan } from "@/components/product-ui";
const tones: Record<string, string> = { MATCHED: "bg-emerald-50 text-emerald-700", REVIEW_REQUIRED: "bg-amber-50 text-amber-700", EXCEPTION: "bg-rose-50 text-rose-700", APPROVAL_PENDING: "bg-blue-50 text-blue-700", PAYMENT_READY: "bg-emerald-50 text-emerald-700", EXPORTED: "bg-slate-100 text-slate-600" };
export function StatusBadge({ status }: {
    status: string;
}) { return <UiSpan className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${tones[status] || "bg-slate-100 text-slate-600"}`}>{status.replaceAll("_", " ")}</UiSpan>; }
