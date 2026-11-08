"use client";
import { ProductName } from "@/components/partner-brand";
import { authStorage } from "@/lib/partner";

import { WorkspaceAccessContext } from "@/components/workspace-access-context";
import { ThemeToggle } from "@/components/theme-toggle";
import { ProductBreadcrumbs } from "@/components/product-breadcrumbs";
import { NotificationBell } from "@/components/notification-bell";
import { UiBox, UiButton, UiIconButton, UiLabel, UiSection, UiSelect, UiSpan, UiStrong } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import Drawer from "@mui/material/Drawer";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import ListSubheader from "@mui/material/ListSubheader";
import Collapse from "@mui/material/Collapse";
import Tooltip from "@mui/material/Tooltip";
import Chip from "@mui/material/Chip";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useId } from "react";
import { Activity, Bell, BriefcaseBusiness, ChartNoAxesColumn, Check, ChevronDown, CircleAlert, CreditCard, Clock3, FileCheck2, FilePlus2, Files, FolderOpen, Fuel, LayoutDashboard, LogOut, Mail, MapPin, Menu, ReceiptIndianRupee, MessageCircle, PanelLeftClose, PanelLeftOpen, Plug, ScrollText, Send, Settings2, ShieldCheck, Sparkles, Tags, Truck, UsersRound, Workflow, Wrench, X } from "lucide-react";
import { accessToken, apiFetch, workspaceKey } from "@/lib/api";
import { canShowNavigation, filterNavigation, type NavigationAccess } from "@/lib/navigation-access";
type Profile = NavigationAccess & {
    email: string;
    name: string;
    tenant: string;
    workspace_key: string;
    role: string;
};
type WorkspaceChoice = {
    tenant: string;
    workspace_key: string;
    role: string;
};
type Summary = {
    total_invoices: number;
    exceptions: number;
    pending_approvals: number;
};
type NavItem = {
    label: string;
    href: string;
    icon: typeof LayoutDashboard;
    count?: keyof Summary;
    alert?: boolean;
    children?: NavItem[];
};
const groups: {
    title: string;
    items: NavItem[];
}[] = [
    { title: "Workspace", items: [
            { label: "Overview", href: "/", icon: LayoutDashboard },
            { label: "Needs attention", href: "/attention", icon: CircleAlert, alert: true },
            { label: "Fleet & trips", href: "/fleet", icon: Truck, children: [
                    { label: "Live operations", href: "/fleet/live-tracking", icon: MapPin },
                    { label: "Dispatch & trips", href: "/fleet/dispatch", icon: Workflow, children: [
                        { label: "Transport orders", href: "/fleet/orders", icon: FilePlus2 },
                        { label: "Dock schedule", href: "/fleet/dock-schedule", icon: Clock3 },
                        { label: "Create a trip", href: "/fleet/create-trip", icon: FilePlus2 },
                        { label: "Trip register", href: "/fleet/trips", icon: Files },
                        { label: "Trip alerts", href: "/fleet/alerts", icon: Bell },
                        { label: "Trip follow-ups", href: "/fleet/follow-ups", icon: Bell },
                        { label: "Return loads", href: "/fleet/return-loads", icon: Truck },
                        { label: "Driver phone view", href: "/fleet/driver", icon: Truck },
                    ] },
                    { label: "Fleet assets", href: "/fleet/trucks", icon: BriefcaseBusiness, children: [
                        { label: "Truck documents", href: "/fleet/truck-documents", icon: FolderOpen },
                        { label: "Maintenance", href: "/fleet/maintenance", icon: Wrench },
                        { label: "Sites & geofences", href: "/fleet/geofences", icon: MapPin },
                        { label: "Reliability", href: "/fleet/reliability", icon: ChartNoAxesColumn },
                        { label: "Reminder settings", href: "/fleet/settings", icon: Settings2 },
                    ] },
                    { label: "Customers & freight", href: "/fleet/customers", icon: UsersRound, children: [
                        { label: "Booking history", href: "/fleet/booking-history", icon: Truck },
                        { label: "Customer invoices", href: "/fleet/customer-invoices", icon: ReceiptIndianRupee },
                        { label: "Customer shipment portal", href: "/fleet/customer-portal", icon: Files },
                        { label: "Customer notifications", href: "/fleet/customer-notifications", icon: Bell },
                        { label: "Freight reconciliation", href: "/fleet/freight-reconciliation", icon: Files },
                        { label: "Logistics documents", href: "/fleet/documents", icon: FileCheck2 },
                        { label: "Exception center", href: "/fleet/exception-center", icon: CircleAlert },
                    ] },
                    { label: "Fleet finance & insights", href: "/fleet/operational-reports", icon: ChartNoAxesColumn, children: [
                        { label: "Fuel management", href: "/fleet/fuel", icon: Fuel },
                        { label: "Trip reports", href: "/fleet/trip-reports", icon: ChartNoAxesColumn },
                        { label: "Driver settlements", href: "/fleet/driver-salaries", icon: ReceiptIndianRupee },
                        { label: "Driver pay setup", href: "/fleet/finance-settings", icon: Settings2 },
                        { label: "Revenue leakage", href: "/fleet/revenue-leakage", icon: CircleAlert },
                    ] },
                ] },
            { label: "Invoices", href: "/invoices", icon: Files, count: "total_invoices", children: [
                    { label: "Email intake", href: "/email-intake", icon: Mail },
                    { label: "Duplicate review", href: "/duplicates", icon: Files },
                    { label: "Bulk actions", href: "/bulk-actions", icon: Check },
                ] },
            { label: "Exceptions", href: "/exceptions", icon: CircleAlert, count: "exceptions", alert: true, children: [
                    { label: "Follow-up drafts", href: "/follow-ups", icon: Send },
                    { label: "SLA rules", href: "/sla-rules", icon: Clock3 },
                ] },
            { label: "Approvals", href: "/approvals", icon: FileCheck2, count: "pending_approvals", children: [
                    { label: "Approval rules", href: "/approval-rules", icon: Workflow },
                ] },
            { label: "Payments", href: "/payments", icon: ReceiptIndianRupee },
            { label: "Vendors", href: "/vendors", icon: Truck, children: [
                    { label: "Vendor aliases", href: "/vendor-aliases", icon: Tags },
                    { label: "Vendor portal", href: "/vendor-portal", icon: UsersRound },
                ] },
            { label: "Procurement", href: "/purchase-orders", icon: BriefcaseBusiness, children: [
                    { label: "Purchase orders", href: "/purchase-orders", icon: BriefcaseBusiness },
                    { label: "Goods received", href: "/grns", icon: Check },
                    { label: "Financial notes", href: "/financial-notes", icon: ScrollText },
                ] },
        ] },
    { title: "Insights & controls", items: [
            { label: "Reports", href: "/reports", icon: ChartNoAxesColumn },
            { label: "Audit log", href: "/audit", icon: Activity },
            { label: "Tally export", href: "/exports", icon: ShieldCheck },
            { label: "Tax review", href: "/compliance", icon: ShieldCheck },
            { label: "Bank reconciliation", href: "/bank-reconciliation", icon: ReceiptIndianRupee },
            { label: "Settlement sources", href: "/settlements", icon: ReceiptIndianRupee },
            { label: "AI review", href: "/ai-review", icon: Sparkles },
            { label: "Integrations", href: "/integrations", icon: Plug, children: [
                    { label: "API & webhooks", href: "/integrations", icon: Plug },
                    { label: "ERP & accounting", href: "/integrations/erp", icon: Plug },
                ] },
            { label: "WhatsApp", href: "/whatsapp", icon: MessageCircle },
            { label: "Custom fields", href: "/custom-fields", icon: Files },
            { label: "Notifications", href: "/notifications", icon: Bell },
        ] },
];
function WorkspaceNav({ pathname, summary, collapsed, access }: {
    access: Profile | null;
    pathname: string;
    summary: Summary | null;
    collapsed: boolean;
}) {
    const router = useRouter();
    const expandedForPath = useCallback(() => {
        const matches = (href: string) => pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
        const collectOpenGroups = (item: NavItem): string[] => {
            const descendants = item.children?.flatMap(collectOpenGroups) || [];
            return [...(item.children && (matches(item.href) || descendants.length) ? [item.label] : []), ...descendants];
        };
        return new Set(groups.flatMap(group => group.items.flatMap(collectOpenGroups)));
    }, [pathname]);
    const [openItems, setOpenItems] = useState<Set<string>>(expandedForPath);
    useEffect(() => {
        let saved: string[] = [];
        try { const stored: unknown = JSON.parse(authStorage.getItem("kriyopay_navigation_open_groups") || "[]"); if (Array.isArray(stored)) saved = stored.filter((item): item is string => typeof item === "string"); } catch { /* Ignore a malformed saved preference. */ }
        setOpenItems(current => new Set([...current, ...saved, ...expandedForPath()]));
    }, [expandedForPath]);
    const visibleGroups = groups.map(group => ({ ...group, items: filterNavigation(group.items, access) })).filter(group => group.items.length);
    const administration = filterNavigation<NavItem>([
        { label: "Users & roles", href: "/users", icon: UsersRound },
        { label: "Branches", href: "/branches", icon: BriefcaseBusiness },
        { label: "Billing & plan", href: "/billing", icon: CreditCard },
        { label: "Settings", href: "/settings", icon: Settings2 },
    ], access);
    const navigationId = useId();
    function renderItem(item: NavItem, nested = false): React.ReactNode {
        const Icon = item.icon;
        const active = pathname === item.href;
        const count = item.count ? summary?.[item.count] : undefined;
        const childId = `${navigationId}-${item.href.replace(/[^a-zA-Z0-9]/g, "-")}`;
        const link = <ListItemButton component={Link} href={item.href} prefetch={false} onPointerDown={() => router.prefetch(item.href)} onMouseEnter={() => router.prefetch(item.href)} onFocus={() => router.prefetch(item.href)} selected={active} aria-label={collapsed ? item.label : undefined} aria-current={pathname === item.href ? "page" : undefined} sx={{ borderRadius: 1, minHeight: 39, py: 0.7, px: collapsed ? 1 : 1.5, ml: nested && !collapsed ? 1 : 0,
                justifyContent: collapsed ? "center" : "flex-start", "&.Mui-selected": { bgcolor: "action.selected", color: "primary.main", "&:hover": { bgcolor: "action.focus" } } }}>
          <ListItemIcon sx={{ minWidth: collapsed ? 0 : 30, color: "inherit" }}><Icon size={17}/></ListItemIcon>
          {!collapsed && <ListItemText primary={item.label} slotProps={{ primary: { sx: { fontSize: 13, fontWeight: active ? 700 : 500 } } }}/>}
          {!collapsed && typeof count === "number" && <Chip label={count} size="small" color={item.alert && count > 0 ? "error" : "default"} sx={{ height: 21, fontSize: 10, ml: 1 }}/>}
        </ListItemButton>;
        return <UiBox key={`${item.href}-${item.label}`}>
          <UiBox className="flex items-center gap-1"><UiBox className="min-w-0 flex-1"><Tooltip title={collapsed ? item.label : ""} placement="right" arrow>{link}</Tooltip></UiBox>
            {item.children && <Tooltip title={`${openItems.has(item.label) ? "Close" : "Open"} ${item.label}`}><UiIconButton type="button" aria-label={`${openItems.has(item.label) ? "Close" : "Open"} ${item.label} sub-features`} aria-expanded={openItems.has(item.label)} aria-controls={childId} onClick={() => { const next = new Set(openItems); if (next.has(item.label)) next.delete(item.label); else next.add(item.label); setOpenItems(next); try { authStorage.setItem("kriyopay_navigation_open_groups", JSON.stringify([...next])); } catch { /* Navigation remains usable if storage is unavailable. */ } }}>
              <ChevronDown size={15} style={{ transform: openItems.has(item.label) ? "rotate(0)" : "rotate(-90deg)"}}/>
            </UiIconButton></Tooltip>}
          </UiBox>
          {item.children && <Collapse in={openItems.has(item.label)} timeout="auto" unmountOnExit id={childId}><List component="div" disablePadding sx={{ ml: collapsed ? 0 : 2, borderLeft: collapsed ? 0 : "1px solid", borderColor: "divider" }}>{item.children.map(child => renderItem(child, true))}</List></Collapse>}
        </UiBox>;
    }
    return <List component="nav" aria-label="Workspace navigation" disablePadding>
      {visibleGroups.map(group => <UiSection key={group.title} className="border-t border-line pt-3 first:border-0">
        {!collapsed && <ListSubheader component="div" disableSticky sx={{ bgcolor: "transparent", fontSize: 10, fontWeight: 700, lineHeight: "28px", textTransform: "uppercase", letterSpacing: 1 }}>{group.title}</ListSubheader>}
        {group.items.map(item => renderItem(item))}
      </UiSection>)}
      {administration.length > 0 && <UiSection className="border-t border-line pt-3">
        {!collapsed && <ListSubheader component="div" disableSticky sx={{ fontSize: 10, fontWeight: 700, lineHeight: "28px", textTransform: "uppercase", letterSpacing: 1 }}>Administration</ListSubheader>}
        {administration.map(item => renderItem(item))}
      </UiSection>}
    </List>;
}
export function WorkspaceShell({ children }: {
    children: React.ReactNode;
}) {
    const pathname = usePathname();
    const [profile, setProfile] = useState<Profile | null>(null);
    const [accessError,setAccessError] = useState("");
    const [workspaces, setWorkspaces] = useState<WorkspaceChoice[]>([]);
    const [summary, setSummary] = useState<Summary | null>(null);
    const [savedWorkspaceKey, setSavedWorkspaceKey] = useState("");
    const [menuOpen, setMenuOpen] = useState(false);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const hidden = pathname === "/login" || pathname === "/admin-login" || pathname === "/signup" || pathname === "/forgot-password" || pathname === "/reset-password" || pathname.startsWith("/portal/") || pathname.startsWith("/invite/") || pathname.startsWith("/admin-console");
    useEffect(() => {
        setSavedWorkspaceKey(workspaceKey());
        setSidebarCollapsed(authStorage.getItem("kriyopay_sidebar_collapsed") === "true");
        if (hidden || !accessToken())
            return;
        apiFetch("/auth/workspaces").then(async workspacesResponse => {
            if (workspacesResponse.ok)
                setWorkspaces(await workspacesResponse.json());
        }).catch(() => { });
    }, [hidden]);
    useEffect(() => {
        if (hidden || !accessToken()) {
            setProfile(null);
            return;
        }
        let active = true;
        let loading = false;
        let lastSummary = 0;
        const refreshAccess = async () => {
            if (loading)
                return;
            loading = true;
            try {
                const [response, summaryResponse] = await Promise.all([apiFetch("/auth/me"), Date.now()-lastSummary>60000?apiFetch("/dashboard/summary?compact=1"):Promise.resolve(null)]);
                if (summaryResponse?.ok && active) {
                    setSummary(await summaryResponse.json()); lastSummary=Date.now();
                }
                const next = response.ok ? await response.json() as Profile : null;
                if (active) {
                    setProfile(next);
                    setAccessError(response.ok?"":"Your workspace access is unavailable. Contact your company administrator.");
                }
            }
            catch {
                // Keep the last known menu during network outages; APIs still enforce access.
            }
            finally {
                loading = false;
            }
        };
        void refreshAccess();
        const whenVisible = () => { if (!document.hidden) void refreshAccess(); };
        window.addEventListener("focus", refreshAccess);
        window.addEventListener("kriyopay:access-check", refreshAccess);
        document.addEventListener("visibilitychange", whenVisible);
        const timer = window.setInterval(() => {
            if (!document.hidden)
                void refreshAccess();
        }, 30000);
        return () => { active = false; window.removeEventListener("focus", refreshAccess); window.removeEventListener("kriyopay:access-check", refreshAccess); document.removeEventListener("visibilitychange", whenVisible); window.clearInterval(timer); };
    }, [hidden]);
    useEffect(() => {
        if (!menuOpen)
            return;
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape")
                setMenuOpen(false);
        };
        window.addEventListener("keydown", closeOnEscape);
        return () => window.removeEventListener("keydown", closeOnEscape);
    }, [menuOpen]);
    function logout() {
        const refresh = authStorage.getItem("kriyopay_refresh") || "";
        void apiFetch("/auth/logout", { method: "POST", body: JSON.stringify({ refresh }) });
        ["kriyopay_access", "kriyopay_refresh", "kriyopay_workspace"].forEach(key => authStorage.removeItem(key));
        window.location.assign("/login");
    }
    function switchWorkspace(key: string) {
        if (!key || key === workspaceKey())
            return;
        authStorage.setItem("kriyopay_workspace", key);
        window.location.reload();
    }
    function toggleSidebar() {
        setSidebarCollapsed(current => {
            const next = !current;
            authStorage.setItem("kriyopay_sidebar_collapsed", String(next));
            return next;
        });
    }
    if (hidden)
        return <>{children}</>;
    const userName = profile?.name || profile?.email?.split("@")[0] || "Workspace member";
    const initials = userName.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map(item => item[0].toUpperCase()).join("") || "KP";
    return <WorkspaceAccessContext.Provider value={profile}><UiBox sx={pathname === "/" ? { "@media (min-width: 900px)": { height: "100dvh", minHeight: 0, display: "flex", flexDirection: "column", "& > header, & > .border-b": { flexShrink: 0 } } } : undefined} className={`min-h-screen transition-[padding] duration-200 ${sidebarCollapsed ? "lg:pl-[68px]" : "lg:pl-[248px]"}`}>
    <Drawer variant="permanent" sx={{ display: { xs: "none", lg: "block" }, "& .MuiDrawer-paper": { width: sidebarCollapsed ? 68 : 248, boxSizing: "border-box", display: "flex", flexDirection: "column", overflowY: "auto", py: 2, px: sidebarCollapsed ? 1 : 2, transition: "width 200ms" } }}>
      <UiBox className={`flex items-center ${sidebarCollapsed ? "justify-center" : "justify-between"}`}><Link href="/" title="KriyoPay overview" className={`flex items-center ${sidebarCollapsed ? "justify-center" : "gap-3 px-2"}`}><UiSpan className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-forest text-white"><ReceiptIndianRupee size={21}/></UiSpan>{!sidebarCollapsed && <UiSpan><UiStrong className="block text-base tracking-tight"><ProductName/></UiStrong><UiSpan className="text-[10px] font-medium tracking-[.16em] text-slate-400">FINANCE &amp; FLEET OPS</UiSpan></UiSpan>}</Link>{!sidebarCollapsed && <UiIconButton type="button" onClick={toggleSidebar} title="Collapse sidebar" aria-label="Collapse sidebar" className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-slate-100"><PanelLeftClose size={17}/></UiIconButton>}</UiBox>
      {sidebarCollapsed ? <UiBox className="mt-5 flex justify-center" title={profile?.tenant || "Your workspace"}><UiSpan className="grid h-8 w-8 place-items-center rounded-lg bg-mint text-[10px] font-bold text-forest">{(profile?.tenant || "KP").slice(0, 2).toUpperCase()}</UiSpan></UiBox> : <UiBox className="mt-5 rounded-xl border border-line px-3 py-3"><UiStrong className="block truncate text-xs">{profile?.tenant || "Your workspace"}</UiStrong><UiSpan className="text-[10px] text-slate-400">{profile?.workspace_key || savedWorkspaceKey || "Sign in to connect"}</UiSpan>{workspaces.length > 1 && <UiLabel className="mt-2 block text-[10px] font-semibold text-slate-500">Switch company<UiSelect aria-label="Switch workspace" value={profile?.workspace_key || savedWorkspaceKey} onChange={e => switchWorkspace(e.target.value)} className="mt-1 w-full rounded-md border border-line bg-white px-2 py-1.5 text-xs text-ink">{workspaces.map(item => <option key={item.workspace_key} value={item.workspace_key}>{item.tenant}</option>)}</UiSelect></UiLabel>}</UiBox>}
      {sidebarCollapsed && <UiIconButton type="button" onClick={toggleSidebar} title="Expand sidebar" aria-label="Expand sidebar" className="mt-2 grid h-8 place-items-center rounded-lg text-slate-500 hover:bg-slate-100"><PanelLeftOpen size={17}/></UiIconButton>}
      <UiBox className="mt-5 flex-1"><WorkspaceNav access={profile} pathname={pathname} summary={summary} collapsed={sidebarCollapsed}/></UiBox>
      <UiButton type="button" onClick={logout} title={sidebarCollapsed ? `${userName} · Sign out` : undefined} aria-label={sidebarCollapsed ? `${userName} · Sign out` : undefined} className={`mt-4 flex min-h-10 items-center rounded-lg text-left text-xs text-slate-500 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest ${sidebarCollapsed ? "justify-center px-2" : "gap-2 px-2 py-2"}`}><UiSpan className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-mint text-[11px] font-bold text-forest">{initials}</UiSpan>{!sidebarCollapsed && <><UiSpan className="min-w-0 flex-1"><UiStrong className="block truncate text-xs text-ink">{userName}</UiStrong><UiSpan className="text-[10px]">{profile?.role || "Member"} · Sign out</UiSpan></UiSpan><LogOut size={15}/></>}</UiButton>
    </Drawer>
    <AppBar component="header" position="sticky" color="inherit" elevation={0} sx={{ display: { xs: "block", lg: "none" }, borderBottom: "1px solid", borderColor: "divider" }}><Toolbar sx={{ justifyContent: "space-between", minHeight: 56 }}>
      <Link href="/" className="flex items-center gap-2 font-bold"> <UiSpan className="grid h-8 w-8 place-items-center rounded-lg bg-forest text-white"><ReceiptIndianRupee size={17}/></UiSpan>kriyo<UiSpan className="-ml-2 text-forest">pay</UiSpan></Link>
      <UiIconButton type="button" aria-label="Open navigation menu" aria-expanded={menuOpen} aria-controls="mobile-workspace-menu" onClick={() => setMenuOpen(open => !open)} className="grid h-10 w-10 place-items-center rounded-lg text-slate-700 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest">{menuOpen ? <X size={20}/> : <Menu size={20}/>}</UiIconButton>
    </Toolbar></AppBar>
    <Drawer open={menuOpen} onClose={() => setMenuOpen(false)} anchor="right" sx={{ display: { lg: "none" } }} slotProps={{ paper: { sx: { width: "min(88vw,360px)", p: 2 } } }}><UiBox id="mobile-workspace-menu" aria-label="Mobile workspace menu">
      <UiBox className="mb-5 flex items-center justify-between"><UiBox><UiStrong className="block text-sm">{profile?.tenant || "Your workspace"}</UiStrong><UiSpan className="text-[11px] text-slate-500">{profile?.role || "Member"}</UiSpan></UiBox><UiIconButton aria-label="Close navigation menu" onClick={() => setMenuOpen(false)} className="grid h-9 w-9 place-items-center rounded-lg hover:bg-slate-100"><X size={18}/></UiIconButton></UiBox>
      <WorkspaceNav access={profile} pathname={pathname} summary={summary} collapsed={false}/>
      <UiButton onClick={logout} className="mt-5 flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-sm text-slate-600 hover:bg-slate-50"><LogOut size={17}/>Sign out</UiButton>
    </UiBox></Drawer>
    <UiBox className="flex items-center justify-between gap-3 border-b border-line bg-white px-5 py-2"><ProductBreadcrumbs allowedPaths={groups.flatMap(group => filterNavigation(group.items, profile).flatMap(item => [item.href, ...(item.children?.map(child => child.href) || [])]))}/><UiBox className="flex items-center gap-2"><ThemeToggle/><NotificationBell access={profile}/></UiBox></UiBox>
    {accessError || (profile && !canShowNavigation(pathname, profile)) ? <UiBox role="status" sx={{m:3,p:4,border:"1px solid",borderColor:"divider",borderRadius:3,bgcolor:"background.paper"}}><ShieldCheck size={28}/><h1 className="mt-4 text-xl font-semibold">Access unavailable</h1><p className="mt-2 text-sm text-slate-500">{accessError || "Your company’s feature access or your role has changed. This page is no longer available to your account. Contact your company administrator if you need access."}</p><p className="mt-2 text-xs text-slate-500">Access refreshes automatically. If it is enabled again, this page will reopen.</p></UiBox> : children}
  </UiBox></WorkspaceAccessContext.Provider>;
}
