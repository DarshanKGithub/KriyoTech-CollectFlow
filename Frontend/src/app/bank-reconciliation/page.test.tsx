import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ReconciliationPage from "./page";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api",()=>({apiFetch:vi.fn(),workspaceKey:()=>"test-workspace"}));
vi.mock("next/navigation",()=>({usePathname:()=>"/bank-reconciliation"}));
vi.mock("@mui/material/useMediaQuery",()=>({default:()=>true}));
const row={id:"11111111-1111-4111-8111-111111111111",date:"2026-10-20",description:"Supplier transfer",reference:"BANK-125",amount:"-125.00",status:"MATCHED",payment_id:"22222222-2222-4222-8222-222222222222",transport_collection_id:null,driver_salary_payment_id:null,statement:"october.csv"};
function response(data:unknown,ok=true){return Promise.resolve({ok,json:async()=>data} as Response);}
afterEach(()=>{cleanup();vi.clearAllMocks();localStorage.clear();});
describe("reconciliation financial safeguards",()=>{
  it("searches all records through the server",async()=>{
    vi.mocked(apiFetch).mockImplementation(async path=>path==="/auth/me"?await response({role:"FINANCE"}):await response({transactions:[row],count:620,counts:{MATCHED:620}}));
    render(<ReconciliationPage/>);
    await screen.findByRole("button",{name:"Review match"});
    fireEvent.change(screen.getByLabelText("Search transactions"),{target:{value:"OLDER-TRANSFER"}});
    await waitFor(()=>expect(vi.mocked(apiFetch).mock.calls.some(([path])=>String(path).includes("search=OLDER-TRANSFER"))).toBe(true));
    expect(screen.getByText("620 matching transactions")).toBeTruthy();
  });
  it("blocks confirmation for an unverified statement and offers verification",async()=>{
    vi.mocked(apiFetch).mockImplementation(async path=>path==="/auth/me"?await response({role:"FINANCE"}):await response({transactions:[{...row,source_verified:false,statement_id:"statement-1"}],counts:{MATCHED:1}}));
    render(<ReconciliationPage/>);
    fireEvent.click(await screen.findByRole("button",{name:"View details"}));
    expect((screen.getByRole("button",{name:"Review & confirm reconciliation"}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("link",{name:"Verify source"}).getAttribute("href")).toContain("record_id=statement-1");
    expect((screen.getByRole("button",{name:"Clear match"}) as HTMLButtonElement).disabled).toBe(false);
  });
  it("provides a read-only auditor workspace",async()=>{
    vi.mocked(apiFetch).mockImplementation(async path=>path==="/auth/me"?await response({role:"AUDITOR"}):await response({transactions:[row],counts:{MATCHED:1}}));
    render(<ReconciliationPage/>);
    await screen.findByText(/Read-only view/);
    expect(screen.queryByRole("button",{name:"Import statement"})).toBeNull();
    fireEvent.click(screen.getByRole("button",{name:"View details"}));
    expect(screen.queryByRole("button",{name:"Review & confirm reconciliation"})).toBeNull();
    expect(screen.queryByRole("button",{name:"Clear match"})).toBeNull();
  });
  it("requires explicit evidence acknowledgement and prevents duplicate confirmation",async()=>{
    let current={...row};
    vi.mocked(apiFetch).mockImplementation(async(path,init)=>{
      if(path==="/auth/me")return await response({role:"FINANCE"});
      if(init?.method==="PATCH"){current={...current,status:"RECONCILED"};return await response({id:row.id,status:"RECONCILED",payment_id:row.payment_id,target_type:"VENDOR_PAYMENT",target_id:row.payment_id});}
      return await response({transactions:[current],counts:{[current.status]:1}});
    });
    render(<ReconciliationPage/>);await screen.findByRole("button",{name:"Review match"});
    fireEvent.click(screen.getByRole("button",{name:"Review match"}));
    fireEvent.click(screen.getByRole("button",{name:"Review & confirm reconciliation"}));
    const confirm=screen.getByRole("button",{name:"Confirm reconciliation"}) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(apiFetch).not.toHaveBeenCalledWith(expect.anything(),expect.objectContaining({method:"PATCH"}));
    fireEvent.click(screen.getByLabelText("I checked the statement, record reference, amount and direction."));
    fireEvent.click(confirm);fireEvent.click(confirm);
    await waitFor(()=>expect(vi.mocked(apiFetch).mock.calls.filter(([,init])=>init?.method==="PATCH")).toHaveLength(1));
    await waitFor(()=>expect(screen.queryByRole("dialog",{name:"Confirm reconciliation"})).toBeNull());
  });
  it("shows a recoverable load failure instead of a successful empty workspace",async()=>{
    vi.mocked(apiFetch).mockImplementation(async path=>path==="/auth/me"?await response({role:"OWNER"}):await response({error:"Reconciliation service unavailable"},false));
    render(<ReconciliationPage/>);
    await screen.findByText("Reconciliation records unavailable");
    expect(screen.queryByText("No statements imported")).toBeNull();
    expect(screen.getAllByRole("button",{name:"Retry"}).length).toBeGreaterThan(0);
  });
});
