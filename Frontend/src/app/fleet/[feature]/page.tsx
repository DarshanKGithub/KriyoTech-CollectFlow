"use client";
import { UiBox, UiH1, UiMain, UiText } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import { useParams } from "next/navigation";
import FleetPage from "../page";
const fleetFeatures: Record<string, {
    title: string;
}> = {
    trucks: { title: "Trucks & drivers" },
    "create-trip": { title: "Create a trip" },
    "trip-reports": { title: "Trip reports" },
    "driver-salaries": { title: "Driver salary" },
    "follow-ups": { title: "Trip follow-ups" },
    trips: { title: "Trip list" },
    alerts: { title: "Trip alerts" },
};
export default function FleetFeatureRoute() {
    const { feature } = useParams<{
        feature: string;
    }>();
    const selected = fleetFeatures[feature];
    if (!selected)
        return <UiMain className="w-full min-w-0 px-4 py-10 sm:px-6 lg:px-8"><UiH1 className="text-xl font-bold">Fleet feature not found</UiH1><Link href="/fleet" className="mt-3 inline-block text-sm font-semibold text-forest">Return to Fleet & trips</Link></UiMain>;
    return <>
    <UiBox className="flex w-full min-w-0 items-center justify-between px-4 pt-5 sm:px-6 lg:px-8">
      <UiBox><UiText className="text-[10px] font-semibold uppercase tracking-wider text-forest">Fleet & trips</UiText><UiH1 className="mt-1 text-lg font-bold">{selected.title}</UiH1></UiBox>
      <Link href="/fleet" className="rounded-lg border border-line px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50">Fleet overview</Link>
    </UiBox>
    <FleetPage />
  </>;
}
