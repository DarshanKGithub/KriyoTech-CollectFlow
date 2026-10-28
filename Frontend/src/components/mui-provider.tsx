"use client";
import { useEffect, useMemo, useState } from "react";
import { ThemeModeContext, type ThemeMode } from "@/components/theme-mode";
import { financeTokens } from "@/lib/finance-design";

import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";

export const productTheme = createTheme({
  breakpoints: { values: { xs: 0, sm: 640, md: 768, lg: 1024, xl: 1280 } },
  palette: { primary: { main: financeTokens.brand },success:{main:financeTokens.success},warning:{main:financeTokens.warning},error:{main:financeTokens.error},info:{main:financeTokens.info}, background: { default: financeTokens.background,paper:financeTokens.surface }, text: { primary: financeTokens.ink, secondary: financeTokens.muted } },
  typography: {
    fontFamily: "Arial, Helvetica, sans-serif",
    h4: { fontSize: 28, fontWeight: 700, letterSpacing: "-0.025em" },
    h6: { fontSize: 18, fontWeight: 700 },
    subtitle1: { fontSize: 15, fontWeight: 600 },
    subtitle2: { fontSize: 13, fontWeight: 600 },
    body1: { fontSize: 14 }, body2: { fontSize: 13, lineHeight: 1.6 },
    button: { textTransform: "none", fontWeight: 600, fontSize: 13 },
  },
  shape: { borderRadius: financeTokens.radius },
  components: {
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { minHeight: financeTokens.controlHeight, gap: 6,"&.Mui-focusVisible":{outline:"2px solid #245f92",outlineOffset:2} } } },
    MuiCssBaseline:{styleOverrides:{"@media (prefers-reduced-motion: reduce)":{"*, *::before, *::after":{animationDuration:"0.01ms !important",transitionDuration:"0.01ms !important"}}}},
    MuiTextField: { defaultProps: { size: "small", variant: "outlined" } },
    MuiInputBase: { styleOverrides: { root: { fontSize: 13 }, input: { minWidth: 0 } } },
    MuiPaper: { styleOverrides: { outlined: { borderColor: financeTokens.border } } },
    MuiTableCell: { styleOverrides: { root: { fontSize: 12, borderColor: "#e0e7e3" }, head: { fontWeight: 700, background: "#f8faf9" } } },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 16 } } },
    MuiLink: { defaultProps: { underline: "hover" } },
  },
});

export function MuiProvider({ children }: { children: React.ReactNode }) {
  const [mode,setMode]=useState<ThemeMode>("light");
  useEffect(()=>{
    let saved:string|null=null;try{saved=localStorage.getItem("kriyopay:theme");}catch{/* Storage may be restricted. */}
    const initial:ThemeMode=saved==="dark"||saved==="light"?saved:window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";
    setMode(initial);document.documentElement.classList.toggle("dark",initial==="dark");document.documentElement.style.colorScheme=initial;
    const sync=(event:StorageEvent)=>{if(event.key==="kriyopay:theme"&&(event.newValue==="light"||event.newValue==="dark")){setMode(event.newValue);document.documentElement.classList.toggle("dark",event.newValue==="dark");document.documentElement.style.colorScheme=event.newValue;}};
    window.addEventListener("storage",sync);return()=>window.removeEventListener("storage",sync);
  },[]);
  const toggle=()=>{const next=mode==="light"?"dark":"light";setMode(next);document.documentElement.classList.toggle("dark",next==="dark");document.documentElement.style.colorScheme=next;try{localStorage.setItem("kriyopay:theme",next);}catch{/* Theme still works without persistent storage. */}};
  const theme=useMemo(()=>mode==="light"?productTheme:createTheme(productTheme,{
    palette:{mode:"dark",primary:{main:"#6ed5b2",light:"#96e1c7",dark:"#52b997",contrastText:"#10251c"},success:{main:"#6ed5b2",light:"#96e1c7",dark:"#52b997",contrastText:"#10251c"},warning:{main:"#edbc69",light:"#f3ce92",dark:"#d3a453",contrastText:"#2a200e"},error:{main:"#ff94a4",light:"#ffb4bf",dark:"#e17889",contrastText:"#310f17"},info:{main:"#8cc7ff",light:"#b1daff",dark:"#6ba9e1",contrastText:"#102133"},background:{default:"#101a17",paper:"#18251f"},text:{primary:"#e7f1eb",secondary:"#a4b8ad"},divider:"#33483d"},
    components:{MuiPaper:{styleOverrides:{root:{backgroundImage:"none"},outlined:{borderColor:"#33483d"}}},MuiTableCell:{styleOverrides:{root:{borderColor:"#33483d"},head:{background:"#20322a"}}}}
  }),[mode]);
  return <ThemeModeContext.Provider value={{mode,toggle}}><ThemeProvider theme={theme}><LocalizationProvider dateAdapter={AdapterDayjs}><CssBaseline/>{children}</LocalizationProvider></ThemeProvider></ThemeModeContext.Provider>;
}
