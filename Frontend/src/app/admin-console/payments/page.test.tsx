import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PaymentsPage from "./page";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }));
vi.mock("../data-table", () => ({ AdminDataTable: () => null }));
const payment = { id: "payment-test", tenant_name: "Synthetic company", amount: 10000, currency: "INR",
  status: "PAID", razorpay_payment_id: "pay_synthetic", created_at: "2026-10-26" };
const response = (data: unknown) => Promise.resolve({ ok: true, json: async () => data } as Response);
function setup(outcome: () => Promise<Response>) {
  vi.mocked(apiFetch).mockImplementation((path, init) => {
    if (init?.method === "POST") return outcome();
    if (path === "/admin/payments") return response({ results: [payment] });
    if (path === "/admin/auth/me") return response({ role: "BILLING_ADMIN" });
    if (path.startsWith("/admin/companies")) return response({ results: [] });
    return response([]);
  });
}
async function submit() {
  fireEvent.change(screen.getByRole("spinbutton", { name: "Refund amount in ₹" }), { target: { value: "20.01" } });
  fireEvent.change(screen.getByRole("textbox", { name: /Reason/ }), { target: { value: "Correction" } });
  fireEvent.submit(screen.getByRole("button", { name: "Request refund" }).closest("form")!);
}
afterEach(() => { cleanup(); vi.clearAllMocks(); sessionStorage.clear(); });

describe("billing refund retry safety", () => {
  it("keeps the same intent key and exact paise after an unknown provider outcome", async () => {
    setup(() => response({ status: "UNKNOWN", message: "Provider outcome unknown; check the same request." }));
    render(<PaymentsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /^Refund$/ }));
    await submit();
    await screen.findByText(/Provider outcome unknown/);
    await submit();
    await waitFor(() => expect(vi.mocked(apiFetch).mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(2));
    const posts = vi.mocked(apiFetch).mock.calls.filter(([, init]) => init?.method === "POST");
    const first = JSON.parse(String(posts[0][1]?.body));
    expect(first.amount).toBe("2001");
    expect(first.idempotency_key).toBeTruthy();
    expect(JSON.parse(String(posts[1][1]?.body)).idempotency_key).toBe(first.idempotency_key);
    expect(screen.getByRole("button", { name: "Request refund" })).toBeTruthy();
  });
  it("retains the key after a lost network response and allows retry", async () => {
    setup(() => Promise.reject(new Error("connection lost")));
    render(<PaymentsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /^Refund$/ }));
    await submit();
    await screen.findByText(/Could not confirm the refund response/);
    expect(sessionStorage.getItem("kriyopay_refund_intent_payment-test")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Request refund" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

