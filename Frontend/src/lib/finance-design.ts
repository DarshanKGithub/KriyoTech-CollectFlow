import { brandColors } from "./brand-colors";

export const financeTokens = {
  brand:brandColors.green, secondary:brandColors.cream, ink:brandColors.ink, muted:brandColors.muted,
  surface:brandColors.surface, background:brandColors.canvas, border:brandColors.border,
  success:brandColors.green, warning:"#936200", error:"#b42338", info:"#245f92",
  radius:10, spacing:[4,8,12,16,24,32], controlHeight:40,
} as const;
