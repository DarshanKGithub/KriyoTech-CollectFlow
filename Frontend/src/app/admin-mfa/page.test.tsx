import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import AdminMfaPage from "./page";

vi.mock("qrcode", () => ({ toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,test") }));
const response = (data: object, ok = true) => Promise.resolve({ ok, json: async () => data } as Response);

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

it("enrolls with the scoped challenge and keeps session tokens absent after a rejected code", async () => {
  sessionStorage.setItem("kriyopay_admin_mfa", JSON.stringify({ mode: "setup", pendingToken: "setup-challenge", role: "SUPER_ADMIN" }));
  const fetcher = vi.fn().mockImplementation((url: string) => url.endsWith("/setup")
    ? response({ secret: "SYNTHETIC", uri: "otpauth://test" })
    : response({ detail: "Invalid two-factor authentication code." }, false));
  vi.stubGlobal("fetch", fetcher);
  render(<AdminMfaPage />);
  await waitFor(() => expect((screen.getByRole("button", { name: "Enable two-factor access" }) as HTMLButtonElement).disabled).toBe(true));
  await screen.findByText("SYNTHETIC");
  fireEvent.change(screen.getByRole("textbox", { name: "Six-digit code" }), { target: { value: "123456" } });
  fireEvent.submit(screen.getByRole("button", { name: "Enable two-factor access" }).closest("form")!);
  await screen.findByRole("alert");
  expect(fetcher).toHaveBeenCalledTimes(2);
  const setup = fetcher.mock.calls[0][1];
  const enable = fetcher.mock.calls[1][1];
  expect(JSON.parse(setup.body)).toEqual({ mfa_pending_token: "setup-challenge" });
  expect(JSON.parse(enable.body)).toEqual({ code: "123456", mfa_pending_token: "setup-challenge" });
  expect(setup.headers.Authorization).toBeUndefined();
  expect(enable.headers.Authorization).toBeUndefined();
  expect(localStorage.getItem("kriyopay_access")).toBeNull();
  expect(localStorage.getItem("kriyopay_refresh")).toBeNull();
});

it("requires session tokens returned by verification rather than trusting stored pre-MFA credentials", async () => {
  sessionStorage.setItem("kriyopay_admin_mfa", JSON.stringify({ mode: "verify", pendingToken: "verify-challenge", access: "old-token", refresh: "old-refresh" }));
  const fetcher = vi.fn().mockImplementation(() => response({ mfa_verified: true }));
  vi.stubGlobal("fetch", fetcher);
  render(<AdminMfaPage />);
  fireEvent.change(screen.getByRole("textbox", { name: "Six-digit code" }), { target: { value: "123456" } });
  fireEvent.submit(screen.getByRole("button", { name: "Verify and continue" }).closest("form")!);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "MFA verification completed without a session. Please sign in again.");
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ code: "123456", mfa_pending_token: "verify-challenge" });
  expect(localStorage.getItem("kriyopay_access")).toBeNull();
});
