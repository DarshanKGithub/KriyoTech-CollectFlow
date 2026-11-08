import "./globals.css";
import type { Metadata, Viewport } from "next";
import { brandColors } from "@/lib/brand-colors";
import { WorkspaceShell } from "@/components/workspace-shell";
import { FormNavigationGuard } from "@/components/form-navigation-guard";
import { MuiProvider } from "@/components/mui-provider";
import { AppRouterCacheProvider } from "@mui/material-nextjs/v14-appRouter";
import { ProductDialogs } from "@/components/product-dialogs";
import { PartnerBrandProvider } from "@/components/partner-brand";
export const metadata: Metadata = { title: "KriyoPay · Business Operations", description: "Finance and fleet operations control center for growing businesses" };
export const viewport: Viewport = { themeColor: brandColors.green };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body><AppRouterCacheProvider><PartnerBrandProvider><MuiProvider><ProductDialogs><FormNavigationGuard><WorkspaceShell>{children}</WorkspaceShell></FormNavigationGuard></ProductDialogs></MuiProvider></PartnerBrandProvider></AppRouterCacheProvider></body></html>; }
