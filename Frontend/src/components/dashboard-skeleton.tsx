"use client";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Skeleton from "@mui/material/Skeleton";

export function DashboardSkeleton() {
  return <Box role="status" aria-label="Loading workspace overview" aria-busy="true" sx={{height:"100%",display:"flex",flexDirection:"column",gap:2,minHeight:0,"@media (prefers-reduced-motion: reduce)":{"& .MuiSkeleton-root":{animation:"none"}}}}>
    <Box sx={{display:"grid",gap:2,gridTemplateColumns:{xs:"1fr",sm:"repeat(3,minmax(0,1fr))"}}}>
      {[0,1,2].map(index=><Card key={index} variant="outlined" sx={{p:2}}><Skeleton width="65%"/><Skeleton width="45%" height={48}/><Skeleton width="80%"/></Card>)}
    </Box><Skeleton variant="rounded" sx={{flex:1,minHeight:{xs:220,md:0},transform:"none"}}/>
  </Box>;
}
