"use client";
import { useEffect, useMemo, useState } from "react";
import { ThemeModeContext, type ThemeMode } from "@/components/theme-mode";
import { financeTokens } from "@/lib/finance-design";
import { brandColors } from "@/lib/brand-colors";
import { usePartnerBrand } from "@/components/partner-brand";

import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";

export const productTheme = createTheme({
  breakpoints: { values: { xs: 0, sm: 640, md: 768, lg: 1024, xl: 1280 } },
  palette: {
    primary: { main: brandColors.green, light: brandColors.greenScale[500], dark: brandColors.greenScale[800], contrastText: "#FFFFFF" },
    secondary: { main: "#EDF3EE", light: brandColors.canvas, dark: "#DCE5E0", contrastText: brandColors.green },
    success: { main: financeTokens.success }, warning: { main: financeTokens.warning }, error: { main: financeTokens.error }, info: { main: financeTokens.info },
    background: { default: financeTokens.background, paper: financeTokens.surface },
    text: { primary: financeTokens.ink, secondary: financeTokens.muted }, divider: financeTokens.border,
    action: { hover: "rgba(0,0,0,.04)", selected: "rgba(0,0,0,.08)", focus: "rgba(0,0,0,.12)" },
  },
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
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: ({ theme }) => ({ minHeight: financeTokens.controlHeight, gap: 6,"&.Mui-focusVisible":{outline:`2px solid ${theme.palette.primary.main}`,outlineOffset:2} }) } },
    MuiCssBaseline:{styleOverrides:{"@media (prefers-reduced-motion: reduce)":{"*, *::before, *::after":{animationDuration:"0.01ms !important",transitionDuration:"0.01ms !important"}}}},
    MuiTextField: { defaultProps: { size: "small", variant: "outlined" } },
    MuiInputBase: { styleOverrides: { root: { fontSize: 13 }, input: { minWidth: 0 } } },
    MuiPaper: { styleOverrides: { outlined: { borderColor: financeTokens.border } } },
    MuiDrawer: { styleOverrides: { paper: { backgroundColor: "#FFFFFF", borderColor: brandColors.border } } },
    MuiOutlinedInput: { styleOverrides: { root: { backgroundColor: brandColors.surface, "& .MuiOutlinedInput-notchedOutline": { borderColor: brandColors.border } } } },
    MuiTableCell: { styleOverrides: { root: { fontSize: 12, borderColor: brandColors.border }, head: { fontWeight: 700, background: brandColors.subtle } } },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 16 } } },
    MuiLink: { defaultProps: { underline: "hover" } },
  },
});

export function MuiProvider({ children }: { children: React.ReactNode }) {
  const brand = usePartnerBrand();
  const [mode,setMode]=useState<ThemeMode>("light");
  useEffect(()=>{
    let saved:string|null=null;try{saved=localStorage.getItem("kriyopay:theme");}catch{/* Storage may be restricted. */}
    const initial:ThemeMode=saved==="dark"||saved==="light"?saved:window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";
    setMode(initial);document.documentElement.classList.toggle("dark",initial==="dark");document.documentElement.style.colorScheme=initial;
    const sync=(event:StorageEvent)=>{if(event.key==="kriyopay:theme"&&(event.newValue==="light"||event.newValue==="dark")){setMode(event.newValue);document.documentElement.classList.toggle("dark",event.newValue==="dark");document.documentElement.style.colorScheme=event.newValue;}};
    window.addEventListener("storage",sync);return()=>window.removeEventListener("storage",sync);
  },[]);
  const toggle=()=>{const next=mode==="light"?"dark":"light";setMode(next);document.documentElement.classList.toggle("dark",next==="dark");document.documentElement.style.colorScheme=next;try{localStorage.setItem("kriyopay:theme",next);}catch{/* Theme still works without persistent storage. */}};
  const theme=useMemo(()=>mode==="light"?createTheme(productTheme,{palette:{primary:{main:brand.primary_color}}}):createTheme(productTheme,{
    palette:{mode:"dark",primary:{main:brandColors.cream,light:"#E7F1EB",dark:"#CFC0A0",contrastText:brandColors.green},secondary:{main:brandColors.greenScale[300],light:brandColors.greenScale[200],dark:brandColors.greenScale[400],contrastText:brandColors.dark.canvas},success:{main:brandColors.greenScale[300],light:brandColors.greenScale[200],dark:brandColors.greenScale[400],contrastText:brandColors.dark.canvas},warning:{main:"#edbc69",light:"#f3ce92",dark:"#d3a453",contrastText:"#2a200e"},error:{main:"#ff94a4",light:"#ffb4bf",dark:"#e17889",contrastText:"#310f17"},info:{main:"#8cc7ff",light:"#b1daff",dark:"#6ba9e1",contrastText:"#102133"},background:{default:brandColors.dark.canvas,paper:brandColors.dark.surface},text:{primary:brandColors.dark.text,secondary:brandColors.dark.muted},divider:brandColors.dark.border,action:{hover:"rgba(255,255,255,.08)",selected:"rgba(255,255,255,.16)",focus:"rgba(255,255,255,.12)"}},
    components:{MuiPaper:{styleOverrides:{root:{backgroundImage:"none"},outlined:{borderColor:brandColors.dark.border}}},MuiDrawer:{styleOverrides:{paper:{backgroundColor:"#18251F",borderColor:brandColors.dark.border}}},MuiOutlinedInput:{styleOverrides:{root:{backgroundColor:brandColors.dark.surface,"& .MuiOutlinedInput-notchedOutline":{borderColor:brandColors.dark.border}}}},MuiTableCell:{styleOverrides:{root:{borderColor:brandColors.dark.border},head:{background:brandColors.dark.subtle}}}}
  }),[mode,brand.primary_color]);
  return <ThemeModeContext.Provider value={{mode,toggle}}><ThemeProvider theme={theme}><LocalizationProvider dateAdapter={AdapterDayjs}><CssBaseline/>{children}</LocalizationProvider></ThemeProvider></ThemeModeContext.Provider>;
}
