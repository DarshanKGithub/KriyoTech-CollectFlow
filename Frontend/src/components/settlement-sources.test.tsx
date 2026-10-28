import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { SettlementSources } from "./settlement-sources";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api",()=>({apiFetch:vi.fn()}));
vi.mock("@/components/product-dialogs",()=>({showNotice:vi.fn()}));
const batch={id:"batch-1",account_id:"account-1",filename:"report.csv",status:"NEEDS_REVIEW",row_count:1,errors:[],warnings:[],review_note:""};
function response(data:unknown,ok=true){return Promise.resolve({ok,json:async()=>data} as Response);}
function setup(platform=false,role="FINANCE") {
  const base=platform?"/admin/settlements":"/settlements";
  vi.mocked(apiFetch).mockImplementation(async(path)=>{
    if(path===(platform?"/admin/auth/me":"/auth/me"))return response({role});
    if(path===base+"/accounts")return response({accounts:[]});
    if(path===base+"/imports/batch-1")return response(batch);
    if(String(path).includes("?rows=1"))return response({count:1,results:[{row_number:2,data:{record_type:"SETTLEMENT",external_id:"setl-1",currency:"USD",net:"97.00",gross:null,fees:null}}]});
    return response({count:1,results:[batch]});
  });
  render(<SettlementSources platform={platform}/>);
}
afterEach(()=>{cleanup();vi.resetAllMocks();});
it("uses only platform endpoints in the platform workspace",async()=>{
  setup(true,"BILLING_ADMIN");
  await screen.findByText("report.csv");
  expect(screen.getByRole("button",{name:"Add account"})).toBeTruthy();
  expect(screen.queryByRole("tab",{name:"Verify legacy sources"})).toBeNull();
  expect(vi.mocked(apiFetch).mock.calls.every(([path])=>String(path).startsWith("/admin/"))).toBe(true);
});
it("allows an auditor to inspect source rows without approve or reject controls",async()=>{
  setup(false,"AUDITOR");
  await screen.findByText("report.csv");
  expect(screen.queryByRole("button",{name:"Add account"})).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Open import"}));
  await screen.findByRole("table",{name:"Staged source rows"});
  expect(screen.queryByRole("button",{name:"Approve observations"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Reject import"})).toBeNull();
  const row=screen.getByText("setl-1").closest("tr")!;
  expect(within(row).getByText("USD 97.00")).toBeTruthy();
  expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
  expect(vi.mocked(apiFetch).mock.calls.some(([path])=>String(path).startsWith("/admin/"))).toBe(false);
});
it("can retry initialization after a service error",async()=>{
  vi.mocked(apiFetch).mockImplementation(async()=>response({error:"Sources unavailable"},false));
  render(<SettlementSources/>);
  await screen.findByText("Sources unavailable");
  vi.mocked(apiFetch).mockImplementation(async path=>path==="/auth/me"?response({role:"FINANCE"}):String(path).endsWith("/accounts")?response({accounts:[]}):response({count:0,results:[]}));
  fireEvent.click(screen.getByRole("button",{name:"Refresh list"}));
  await screen.findByRole("button",{name:"Add account"});
  expect(screen.queryByText("Sources unavailable")).toBeNull();
});
