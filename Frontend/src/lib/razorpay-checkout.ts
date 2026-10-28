export type CheckoutResult = { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string };
export type CheckoutOptions = {
  key: string; amount: number; currency: string; name: string; description: string; order_id: string;
  handler: (result: CheckoutResult) => void; modal: { ondismiss: () => void }; theme: { color: string };
  prefill?: { name?: string; email?: string };
};
declare global { interface Window { Razorpay?: new(options: CheckoutOptions) => { open: () => void }; } }

let loading: Promise<void> | null = null;
export function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  if (loading) return loading;
  loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    const fail = () => { window.clearTimeout(timer); script.remove(); loading = null; reject(new Error("Razorpay could not load. Check your connection and resume payment.")); };
    const timer = window.setTimeout(fail, 15000);
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => { window.clearTimeout(timer); if (window.Razorpay) resolve(); else fail(); };
    script.onerror = fail;
    document.body.appendChild(script);
  });
  return loading;
}
