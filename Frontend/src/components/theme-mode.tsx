"use client";
import { createContext, useContext } from "react";
export type ThemeMode = "light" | "dark";
export const ThemeModeContext = createContext<{mode:ThemeMode;toggle:()=>void}>({mode:"light",toggle:()=>{}});
export const useThemeMode = () => useContext(ThemeModeContext);
