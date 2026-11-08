"use client";
import { createContext } from "react";
import type { NavigationAccess } from "@/lib/navigation-access";
export const WorkspaceAccessContext = createContext<NavigationAccess|null>(null);
