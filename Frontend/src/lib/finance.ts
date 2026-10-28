/** Amounts are decimal strings from the API. Do not round financial comparisons with floats. */
export function minorUnits(value: string): bigint {
  if (!/^-?\d+(\.\d{1,2})?$/.test(value)) throw new Error("Invalid monetary amount");
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  const result = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return negative ? -result : result;
}
export function decimalAmount(value: bigint) {
  const absolute = value < 0n ? -value : value;
  return `${value < 0n ? "-" : ""}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
}
export function formatMoney(value: string, currency = "INR"): string {
  try {
    const amount = minorUnits(value);
    const absolute = amount < 0n ? -amount : amount;
    const prefix = currency === "INR" ? "₹" : currency ? currency + " " : "";
    return `${amount < 0n ? "-" : ""}${prefix}${new Intl.NumberFormat("en-IN").format(absolute / 100n)}.${String(absolute % 100n).padStart(2, "0")}${currency ? "" : " (currency unverified)"}`;
  } catch { return "Amount unavailable"; }
}
export function absoluteAmount(value: string) { try { const amount = minorUnits(value); return decimalAmount(amount < 0n ? -amount : amount); } catch { return ""; } }
export function moneyDirection(value:string):"IN"|"OUT"|"UNKNOWN" { try {const amount=minorUnits(value);return amount>0n?"IN":amount<0n?"OUT":"UNKNOWN";}catch{return "UNKNOWN";} }
export function financialDate(value?: string | null, includeTime = false) {
  if (!value) return "Not provided";
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString("en-IN", { day:"numeric",month:"short",year:"numeric", ...(includeTime ? {hour:"2-digit",minute:"2-digit"} : {}) });
}
export function apiError(payload: unknown, fallback: string) {
  if (Array.isArray(payload)) return payload.filter(value => typeof value === "string").join(" ") || fallback;
  if (!payload || typeof payload !== "object") return fallback;
  const body = payload as { detail?: unknown; error?: unknown };
  if (typeof body.error === "string") return body.error;
  if (body.error && typeof body.error === "object" && "message" in body.error && typeof body.error.message === "string") return body.error.message;
  return typeof body.detail === "string" ? body.detail : fallback;
}
export function financialErrorMessage(error:unknown,fallback:string) {
  if(error instanceof SyntaxError)return "The financial service is unavailable. Please retry.";
  if(error instanceof Error&&error.message.startsWith("Cannot reach"))return "Connection failed. Check your connection and retry.";
  return error instanceof Error?error.message:fallback;
}
export type LedgerPayment = {vendor_name?:string; source_account?:string|null;currency?:string;provenance_note?:string; id:string; vendor:string|null; amount:string; reference_number:string; mode:string; paid_at:string; created_at?:string; remarks?:string; allocations:{invoice:string;amount:string}[] };
export type BankRow = {revision?:number;group_id?:string|null;currency?:string;source_account_id?:string|null;statement_id?:string;source_verified?:boolean;is_test_data?:boolean; id:string; date:string; description:string; reference:string; amount:string; status:string; payment_id:string|null; transport_collection_id:string|null; driver_salary_payment_id:string|null; statement:string };
export type MatchCandidate = {candidate_id?:string;rejected?:boolean;currency?:string; target_type:"VENDOR_PAYMENT"|"CUSTOMER_COLLECTION"|"DRIVER_SALARY_PAYMENT";target_id:string;payment_reference:string;paid_at:string;amount:string;vendor:string;score:number;confidence:string;reasons:string[] };
export const reconciliationLabels: Record<string,string> = {UNMATCHED:"Needs matching",MATCHED:"Matched · confirm next",RECONCILED:"Reconciled",DUPLICATE:"Duplicate · review needed"};
export function compareCandidate(bank: Pick<BankRow,"amount">, candidate: Pick<MatchCandidate,"amount"|"target_type">) {
  try {
  const observed=minorUnits(bank.amount);const expected=minorUnits(candidate.amount);
  const absolute=observed<0n?-observed:observed;
  const directionMatches=candidate.target_type==="CUSTOMER_COLLECTION"?observed>0n:observed<0n;
  return {difference:decimalAmount(absolute-expected),amountMatches:absolute===expected && expected>0n,directionMatches};
  } catch { return {difference:"",amountMatches:false,directionMatches:false}; }
}
