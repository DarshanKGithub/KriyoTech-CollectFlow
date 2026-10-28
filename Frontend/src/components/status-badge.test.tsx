import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./status-badge";

describe("StatusBadge",()=>{
  it("renders a readable label for workflow statuses",()=>{
    render(<StatusBadge status="APPROVAL_PENDING"/>);
    expect(screen.getByText("APPROVAL PENDING")).toBeTruthy();
  });
});
