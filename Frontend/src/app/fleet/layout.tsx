import type { ReactNode } from "react";
import { FleetWorkspaceNav } from "@/components/fleet-workspace-nav";

export default function FleetLayout({ children }: { children: ReactNode }) {
  return <div className="fleet-workspace min-h-full bg-canvas">
    <FleetWorkspaceNav />
    {children}
  </div>;
}
