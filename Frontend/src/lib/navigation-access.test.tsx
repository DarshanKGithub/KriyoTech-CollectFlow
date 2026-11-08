import { describe, expect, it } from "vitest";
import { canShowNavigation, filterNavigation, type NavigationAccess } from "./navigation-access";

type Item = { href: string; children?: Item[] };
function access(features: Record<string, boolean>, role = "OWNER"): NavigationAccess {
  return { role, entitlements: { features: Object.fromEntries(Object.entries(features).map(([key, enabled]) => [key, { enabled }])) } };
}

describe("workspace navigation access", () => {
  it("checks fleet subfeatures and settlement review separately from their parent access", () => {
    const profile=access({fleet_management:true,fleet_fuel:false,fleet_tracking:true,payment_tracking:true,settlement_review:false});
    expect(canShowNavigation("/fleet/fuel",profile)).toBe(false);
    expect(canShowNavigation("/fleet/live-tracking",profile)).toBe(true);
    expect(canShowNavigation("/settlements",profile)).toBe(false);
    expect(canShowNavigation("/fleet/fuel",access({fleet_management:false,fleet_fuel:true}))).toBe(false);
  });
  it("hides gated links until access has loaded", () => {
    expect(canShowNavigation("/fleet", null)).toBe(false);
    expect(canShowNavigation("/fleet", access({}))).toBe(false);
  });
  it("removes the entire fleet group when fleet is disabled", () => {
    expect(filterNavigation<Item>([{ href: "/fleet", children: [{ href: "/fleet/trucks" }] }], access({ fleet_management: false }))).toEqual([]);
    expect(canShowNavigation("/fleet/trucks", access({ fleet_management: true }))).toBe(true);
  });
  it("filters invoice subfeatures independently", () => {
    const result = filterNavigation<Item>([{ href: "/invoices", children: [{ href: "/email-intake" }, { href: "/duplicates" }] }], access({ invoice_upload: true, duplicate_detection: true }));
    expect(result[0].children).toEqual([{ href: "/duplicates", children: undefined }]);
  });
  it("keeps an enabled financial-notes child with a reachable parent link", () => {
    const result = filterNavigation<Item>([{ href: "/purchase-orders", children: [{ href: "/grns" }, { href: "/financial-notes" }] }], access({ credit_debit_notes: true }));
    expect(result[0].href).toBe("/financial-notes");
    expect(result[0].children).toHaveLength(1);
  });
  it("restricts drivers to their phone workspace even with fleet enabled", () => {
    const driver = access({ fleet_management: true, invoice_upload: true }, "DRIVER");
    expect(canShowNavigation("/fleet/driver", driver)).toBe(true);
    expect(canShowNavigation("/fleet/driver-salaries", driver)).toBe(false);
    expect(canShowNavigation("/invoices", driver)).toBe(false);
  });
  it("does not expose owner administration to other roles", () => {
    expect(canShowNavigation("/settlements", access({ payment_tracking: false }))).toBe(false);
    expect(canShowNavigation("/settlements", access({ payment_tracking: true }, "FINANCE"))).toBe(true);
    expect(canShowNavigation("/settlements", access({ payment_tracking: true }, "PURCHASE"))).toBe(false);
    expect(canShowNavigation("/users", access({}, "FINANCE"))).toBe(false);
    expect(canShowNavigation("/branches", access({}, "OWNER"))).toBe(true);
  });
});
