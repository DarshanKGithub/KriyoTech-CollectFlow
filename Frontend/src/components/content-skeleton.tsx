"use client";

import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";

type SkeletonVariant = "table" | "cards" | "form" | "chart";

/** Layout placeholders for initial loads. Keep existing records visible during background refresh. */
export function ContentSkeleton({ variant = "table", label = "Loading records", rows = 5 }: {
  variant?: SkeletonVariant;
  label?: string;
  rows?: number;
}) {
  return <Box role="status" aria-label={label} aria-busy="true" sx={{
    width: "100%", minWidth: 0, p: { xs: 2, sm: 3 },
    "@media (prefers-reduced-motion: reduce)": { "& .MuiSkeleton-root": { animation: "none" } },
  }}>
    <Box aria-hidden="true">
      {variant === "table" && <>
        <Box sx={{ display: "flex", gap: 3, mb: 2 }}>
          {[38, 22, 18, 22].map((width, index) => <Skeleton key={index} width={`${width}%`} height={28} />)}
        </Box>
        {Array.from({ length: rows }, (_, index) => <Box key={index} sx={{ display: "flex", gap: 3, py: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
          <Box sx={{ width: "38%" }}><Skeleton width={index % 2 ? "85%" : "65%"} /><Skeleton width="45%" height={16} /></Box>
          <Skeleton width="22%" height={30} /><Skeleton width="18%" height={30} /><Skeleton variant="rounded" width="22%" height={28} />
        </Box>)}
      </>}
      {variant === "cards" && <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" } }}>
        {Array.from({ length: rows }, (_, index) => <Paper key={index} variant="outlined" sx={{ p: 2 }}>
          <Box sx={{ display: "flex", gap: 2, alignItems: "center", mb: 2 }}><Skeleton variant="rounded" width={40} height={40} /><Skeleton width="55%" height={28} /></Box>
          <Skeleton width="90%" /><Skeleton width="65%" /><Skeleton width="35%" height={36} />
        </Paper>)}
      </Box>}
      {variant === "form" && <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" } }}>
        {Array.from({ length: rows }, (_, index) => <Box key={index}><Skeleton width="45%" height={24} /><Skeleton variant="rounded" height={44} sx={{ mt: 1 }} /></Box>)}
        <Skeleton variant="rounded" width={150} height={38} />
      </Box>}
      {variant === "chart" && <><Skeleton width="35%" height={28} /><Skeleton variant="rounded" height={280} sx={{ mt: 2 }} /></>}
    </Box>
  </Box>;
}

export function PageSkeleton({ variant = "table", label = "Loading page" }: { variant?: SkeletonVariant; label?: string }) {
  return <Box sx={{ width: "100%", minWidth: 0, px: { xs: 2, sm: 3 }, py: 4 }}>
    <Box aria-hidden="true" sx={{ mb: 3, "@media (prefers-reduced-motion: reduce)": { "& .MuiSkeleton-root": { animation: "none" } } }}>
      <Skeleton width="30%" height={40} /><Skeleton width="55%" height={24} />
    </Box>
    <Paper variant="outlined"><ContentSkeleton variant={variant} label={label} /></Paper>
  </Box>;
}
