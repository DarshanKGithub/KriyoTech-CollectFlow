"use client";
import { BarChart } from "@mui/x-charts/BarChart";
export function SubscriptionChart({values}:{values:number[]}) {
  return <BarChart height={238} layout="horizontal" borderRadius={5} hideLegend
    series={[{data:values,label:"Subscriptions",color:"#166b55",valueFormatter:value=>String(value??0)}]}
    yAxis={[{scaleType:"band",data:["Active","On trial","Past due / grace","Suspended"],width:112,tickLabelStyle:{fontSize:11,fill:"#68766f"}}]}
    xAxis={[{min:0,tickMinStep:1,tickLabelStyle:{fontSize:10,fill:"#829087"}}]} grid={{vertical:true}}
    margin={{top:8,right:22,bottom:20,left:0}} sx={{"& .MuiChartsGrid-line":{stroke:"#edf1ee"},"& .MuiChartsAxis-line, & .MuiChartsAxis-tick":{stroke:"#dfe7e2"}}}/>;
}
