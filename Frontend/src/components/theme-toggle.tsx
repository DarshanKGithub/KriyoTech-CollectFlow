"use client";
import { Moon, Sun } from "lucide-react";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { useThemeMode } from "@/components/theme-mode";
export function ThemeToggle(){
  const {mode,toggle}=useThemeMode();
  const label=mode==="dark"?"Switch to light theme":"Switch to dark theme";
  return <Tooltip title={label}><IconButton type="button" onClick={toggle} aria-label={label} aria-pressed={mode==="dark"} size="small" sx={{width:36,height:36,color:"text.primary",border:"1px solid",borderColor:"divider",borderRadius:2}}>{mode==="dark"?<Sun size={18}/>:<Moon size={18}/>}</IconButton></Tooltip>;
}
