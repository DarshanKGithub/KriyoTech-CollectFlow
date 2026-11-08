"use client";
import { BarChart } from "@mui/x-charts/BarChart";
import { useTheme } from "@mui/material/styles";
export function SubscriptionChart({values}:{values:number[]}) {
  const theme = useTheme();
  return <BarChart height={238} layout="horizontal" borderRadius={5} hideLegend
    series={[{data:values,label:"Subscriptions",color:theme.palette.primary.main,valueFormatter:value=>String(value??0)}]}
    yAxis={[{scaleType:"band",data:["Active","On trial","Past due / grace","Suspended"],width:112,tickLabelStyle:{fontSize:11,fill:theme.palette.text.secondary}}]}
    xAxis={[{min:0,tickMinStep:1,tickLabelStyle:{fontSize:10,fill:theme.palette.text.secondary}}]} grid={{vertical:true}}
    margin={{top:8,right:22,bottom:20,left:0}} sx={{"& .MuiChartsGrid-line":{stroke:theme.palette.divider},"& .MuiChartsAxis-line, & .MuiChartsAxis-tick":{stroke:theme.palette.divider}}}/>;
}
