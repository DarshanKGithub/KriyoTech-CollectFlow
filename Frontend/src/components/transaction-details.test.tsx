import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { TransactionDetails } from "./transaction-details";
import { FinancialStatus } from "./financial-ui";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api",()=>({apiFetch:vi.fn()}));
const payment={id:"22222222-2222-4222-8222-222222222222",vendor:null,amount:"125.50",reference_number:"PAY-125",mode:"BANK_TRANSFER",paid_at:"2026-10-20",created_at:"2026-10-20T10:00:00Z",allocations:[]};
afterEach(()=>{cleanup();vi.clearAllMocks();});
describe("transaction status transparency",()=>{
  it("distinguishes financial states with text",()=>{
    render(<><FinancialStatus status="PENDING"/><FinancialStatus status="FAILED"/><FinancialStatus status="REFUNDED"/><FinancialStatus status="REVERSED"/></>);
    for(const label of ["pending","failed","refunded","reversed"])expect(screen.getByText(label)).toBeTruthy();
  });
  it("does not turn an internal payment record into verified settlement",async()=>{
    vi.mocked(apiFetch).mockResolvedValue({ok:true,json:async()=>({transactions:[],counts:{}})} as Response);
    render(<TransactionDetails payment={payment} counterparty="Supplier" onClose={()=>{}}/>);
    await screen.findByText(/No linked bank row was found/);
    expect(screen.getByText("Payment recorded")).toBeTruthy();
    expect(screen.getByText(/does not confirm a gateway payment or bank settlement/)).toBeTruthy();
    expect(screen.getByText("Not provided by the payment register")).toBeTruthy();
    expect(screen.queryByText("Completed")).toBeNull();
  });
  it("handles a non-JSON service failure without claiming no bank link exists",async()=>{
    vi.mocked(apiFetch).mockResolvedValue({ok:false,json:async()=>{throw new SyntaxError("Unexpected token <");}} as unknown as Response);
    render(<TransactionDetails payment={payment} counterparty="Supplier" onClose={()=>{}}/>);
    await screen.findByText("The financial service is unavailable. Please retry.");
    expect(screen.queryByText(/No linked bank row was found/)).toBeNull();
    expect(screen.getByRole("button",{name:"Retry"})).toBeTruthy();
  });
});
