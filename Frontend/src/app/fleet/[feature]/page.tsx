"use client";
import { UiH1, UiMain } from "@/components/product-ui";
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
    return <FleetPage />;
}
