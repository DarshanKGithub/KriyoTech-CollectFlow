"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import type { GridColumnVisibilityModel, GridDensity, GridSortModel } from "@mui/x-data-grid";
import { workspaceKey } from "@/lib/api";

type Preferences = { visibility: GridColumnVisibilityModel; density: GridDensity; sort: GridSortModel };
const defaults: Preferences = { visibility: {}, density: "standard", sort: [] };
export function useGridPreferences(name: string, initialSort: GridSortModel = []) {
  const pathname = usePathname();
  const [state, setState] = useState<Preferences>(defaults);
  const [storageKey, setStorageKey] = useState("");
  const initialSortKey=JSON.stringify(initialSort);
  useEffect(() => {
    const key = `kriyopay:grid:v1:${workspaceKey()}:${pathname}:${name}`;
    setStorageKey(key);
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      setState(saved ? {
        visibility: saved.visibility && typeof saved.visibility === "object" ? Object.fromEntries(Object.entries(saved.visibility).filter(([, value]) => typeof value === "boolean")) as GridColumnVisibilityModel : {},
        density: ["compact", "standard", "comfortable"].includes(saved.density) ? saved.density : "standard",
        sort: Array.isArray(saved.sort) ? saved.sort.filter((item: { field?: unknown; sort?: unknown }) => typeof item?.field === "string" && ["asc", "desc"].includes(String(item.sort))).slice(0, 1) : [],
      } : {...defaults,sort:JSON.parse(initialSortKey)});
    } catch { setState({...defaults,sort:JSON.parse(initialSortKey)}); }
  }, [pathname, name, initialSortKey]);
  function update(patch: Partial<Preferences>) {
    setState(current => {
      const next = { ...current, ...patch };
      if (storageKey) { try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Preferences are optional when storage is unavailable. */ } }
      return next;
    });
  }
  return { ready:Boolean(storageKey), columnVisibilityModel: state.visibility, onColumnVisibilityModelChange: (visibility: GridColumnVisibilityModel) => update({ visibility }), density: state.density, onDensityChange: (density: GridDensity) => update({ density }), sortModel: state.sort, onSortModelChange: (sort: GridSortModel) => update({ sort }) };
}
