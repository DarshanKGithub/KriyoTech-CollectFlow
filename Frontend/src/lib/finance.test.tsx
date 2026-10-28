import { describe, expect, it } from "vitest";
import { minorUnits, decimalAmount, formatMoney, moneyDirection, compareCandidate, apiError } from "./finance";

describe("financial precision and interpretation",()=>{
  it("preserves paise and large decimal strings without floating point arithmetic",()=>{
    expect(minorUnits("9999999999999999.99")).toBe(999999999999999999n);
    expect(decimalAmount(minorUnits("0.10")+minorUnits("0.20"))).toBe("0.30");
    expect(formatMoney("-1234567.5")).toBe("-₹12,34,567.50");
  });
  it("does not disguise unavailable or malformed values as zero",()=>{
    expect(apiError(["Every target needs the same transfer reference."],"Failed")).toBe("Every target needs the same transfer reference.");
    expect(formatMoney("100.00","USD")).toBe("USD 100.00");
    expect(formatMoney("100.00","")).toBe("100.00 (currency unverified)");
    expect(formatMoney("bad")).toBe("Amount unavailable");
    expect(()=>minorUnits("1.001")).toThrow();
    expect(moneyDirection("bad")).toBe("UNKNOWN");
    expect(moneyDirection("0")).toBe("UNKNOWN");
  });
  it("requires exact amounts and correct direction for candidate review",()=>{
    expect(compareCandidate({amount:"-125.00"},{amount:"125",target_type:"VENDOR_PAYMENT"})).toEqual({difference:"0.00",amountMatches:true,directionMatches:true});
    expect(compareCandidate({amount:"125"},{amount:"125",target_type:"VENDOR_PAYMENT"}).directionMatches).toBe(false);
    expect(compareCandidate({amount:"-125.01"},{amount:"125",target_type:"DRIVER_SALARY_PAYMENT"})).toEqual({difference:"0.01",amountMatches:false,directionMatches:true});
    expect(compareCandidate({amount:"125"},{amount:"125",target_type:"CUSTOMER_COLLECTION"}).directionMatches).toBe(true);
    expect(compareCandidate({amount:"bad"},{amount:"125",target_type:"CUSTOMER_COLLECTION"}).amountMatches).toBe(false);
  });
});
