import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { partnerHeaders, partnerKey, authStorage } from "./partner";
import { ProductName, PartnerBrandProvider } from "@/components/partner-brand";

afterEach(()=>{cleanup();localStorage.clear();sessionStorage.clear();window.history.replaceState({},"","/login");});
it("ignores retired reseller selection and uses only KriyoPay storage",()=>{
  sessionStorage.setItem("kriyopay_partner","retired-reseller");
  window.history.replaceState({},"","/login?partner=retired-reseller");
  expect(partnerKey()).toBe("");
  expect(partnerHeaders()).toEqual({});
  authStorage.setItem("kriyopay_access","kriyopay-token");
  expect(localStorage.getItem("kriyopay_access")).toBe("kriyopay-token");
});
it("renders KriyoPay without depending on reseller branding API",()=>{
  render(<PartnerBrandProvider><ProductName/></PartnerBrandProvider>);
  expect(screen.getByText("KriyoPay")).toBeTruthy();
});
