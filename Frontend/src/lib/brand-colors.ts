/** Shared KriyoPay palette. Keep CSS theme variables aligned with these values. */
export const brandColors = {
  green: "#16734A",
  cream: "#E8DCC4",
  ink: "#1F3D2B",
  muted: "#64705F",
  canvas: "#F5F7F5",
  surface: "#FFFFFF",
  subtle: "#F8FAF9",
  border: "#DCE5E0",
  greenScale: {
    50: "#EFFAF3", 100: "#DCF2E4", 200: "#B9E4CB", 300: "#8AD0AC",
    400: "#55B487", 500: "#2C9667", 600: "#228057", 700: "#16734A",
    800: "#125C3B", 900: "#104A32", 950: "#082C1D",
  },
  dark: {
    canvas: "#101A17", surface: "#18251F", subtle: "#233B30",
    border: "#33483D", text: "#E7F1EB", muted: "#A4B8AD", accent: "#E8DCC4",
  },
  chart: ["#16734A", "#2C9667", "#8AD0AC", "#AA8B52", "#786B45", "#9C9D89"],
} as const;
