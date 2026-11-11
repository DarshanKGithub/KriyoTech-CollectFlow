"use client";
import { ProductName } from "@/components/partner-brand";
import { authStorage } from "@/lib/partner";
import Image from "next/image";

import { WorkspaceAccessContext } from "@/components/workspace-access-context";
import { ThemeToggle } from "@/components/theme-toggle";
import { ProductBreadcrumbs } from "@/components/product-breadcrumbs";
import { NotificationBell } from "@/components/notification-bell";
import { UiBox, UiIconButton, UiLabel, UiSection, UiSelect, UiSpan, UiStrong } from "@/components/product-ui";
import { AppLink as Link } from "@/components/product-ui";
import Drawer from "@mui/material/Drawer";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Avatar from "@mui/material/Avatar";
import Divider from "@mui/material/Divider";
import ListItemText from "@mui/material/ListItemText";
import MenuListPopover from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListSubheader from "@mui/material/ListSubheader";
import Collapse from "@mui/material/Collapse";
import Tooltip from "@mui/material/Tooltip";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import TextField from "@mui/material/TextField";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useId } from "react";
import { Activity, Bell, BriefcaseBusiness, ChartNoAxesColumn, Check, ChevronDown, CircleAlert, CreditCard, Clock3, FileCheck2, FilePlus2, Files, FolderOpen, Fuel, LayoutDashboard, LogOut, Mail, MapPin, Menu, ReceiptIndianRupee, MessageCircle, PanelLeftClose, PanelLeftOpen, Plug, ScrollText, Search, Send, Settings2, ShieldCheck, Sparkles, Tags, Truck, UsersRound, Workflow, Wrench, X } from "lucide-react";
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
                        { label: "LR management", href: "/fleet/lrs", icon: ScrollText },
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
function WorkspaceNav({ pathname, summary, collapsed, access, onNavigate }: {
    access: Profile | null;
    pathname: string;
    summary: Summary | null;
    collapsed: boolean;
    onNavigate?: () => void;
}) {
    const router = useRouter();
    const [search, setSearch] = useState("");
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
    const query = collapsed ? "" : search.trim().toLowerCase();
    function matchingItems(items: NavItem[]): NavItem[] {
        return items.flatMap(item => [
            ...(item.label.toLowerCase().includes(query) ? [{ ...item, children: undefined }] : []),
            ...matchingItems(item.children || []),
        ]);
    }
    const matches = query ? matchingItems([...visibleGroups.flatMap(group => group.items), ...administration]) : [];
    function renderItem(item: NavItem, nested = false): React.ReactNode {
        const Icon = item.icon;
        const active = pathname === item.href;
        const branchActive = !active && Boolean(item.children?.some(function contains(child): boolean {
            return pathname === child.href || Boolean(child.children?.some(contains));
        }));
        const count = item.count ? summary?.[item.count] : undefined;
        const childId = `${navigationId}-${item.href.replace(/[^a-zA-Z0-9]/g, "-")}`;
        const link = <ListItemButton component={Link} href={item.href} prefetch={false} onClick={() => { setSearch(""); onNavigate?.(); }} onPointerDown={() => router.prefetch(item.href)} onMouseEnter={() => router.prefetch(item.href)} onFocus={() => router.prefetch(item.href)} selected={active} aria-label={collapsed ? item.label : undefined} aria-current={pathname === item.href ? "page" : undefined} sx={{
            borderRadius: 1.5, minHeight: nested ? 31 : 36, py: .45, px: collapsed ? .45 : 1,
            gap: .75, position: "relative", justifyContent: collapsed ? "center" : "flex-start",
            color: branchActive ? "primary.main" : "text.secondary",
            "&.Mui-selected": {
              bgcolor: "action.selected", color: "primary.main",
              "&::before": { content: '""', position: "absolute", left: 0, top: 6, bottom: 6, width: 3, borderRadius: 2, bgcolor: "primary.main" },
              "&:hover": { bgcolor: "action.focus" },
            },
          }}>
          <ListItemIcon sx={{ minWidth: collapsed ? 0 : 20, color: "inherit" }}><Icon size={nested ? 14 : 17}/></ListItemIcon>
          {!collapsed && <ListItemText primary={item.label} slotProps={{ primary: { sx: { fontSize: nested ? 12 : 13, lineHeight: 1.25, fontWeight: active || branchActive ? 700 : 500 } } }}/>}
          {!collapsed && typeof count === "number" && count > 0 && <Chip label={count} size="small" color={item.alert && count > 0 ? "error" : "default"} sx={{ height: 18, fontSize: 10, ml: .25, fontWeight: 700, "& .MuiChip-label": { px: .65 } }}/>}
        </ListItemButton>;
        return <UiBox key={`${item.href}-${item.label}`}>
          <UiBox className="flex items-center gap-1"><UiBox className="min-w-0 flex-1"><Tooltip title={collapsed ? item.label : ""} placement="right" arrow>{link}</Tooltip></UiBox>
            {item.children && <Tooltip title={`${openItems.has(item.label) ? "Close" : "Open"} ${item.label}`}><IconButton size="small" sx={{ width: collapsed ? 18 : 28, height: 28, p: 0, flexShrink: 0 }} type="button" aria-label={`${openItems.has(item.label) ? "Close" : "Open"} ${item.label} sub-features`} aria-expanded={openItems.has(item.label)} aria-controls={childId} onClick={() => { const next = new Set(openItems); if (next.has(item.label)) next.delete(item.label); else next.add(item.label); setOpenItems(next); try { authStorage.setItem("kriyopay_navigation_open_groups", JSON.stringify([...next])); } catch { /* Navigation remains usable if storage is unavailable. */ } }}>
              <ChevronDown size={13} style={{ transition: "transform 140ms", transform: openItems.has(item.label) ? "rotate(0)" : "rotate(-90deg)"}}/>
            </IconButton></Tooltip>}
          </UiBox>
          {item.children && <Collapse in={openItems.has(item.label)} timeout="auto" unmountOnExit id={childId}><List component="div" disablePadding sx={{ ml: collapsed ? 0 : 1.5, pl: collapsed ? 0 : .75, borderLeft: collapsed ? 0 : "1px solid", borderColor: "divider" }}>{item.children.map(child => renderItem(child, true))}</List></Collapse>}
        </UiBox>;
    }
    return <List component="nav" aria-label="Workspace navigation" disablePadding sx={{ pb: 1 }}>
      {!collapsed && <UiBox sx={{ position: "sticky", top: 0, zIndex: 2, bgcolor: "background.default", px: .25, pb: .75 }}>
        <TextField fullWidth size="small" value={search} onChange={event => setSearch(event.target.value)} placeholder="Find a page"
          slotProps={{ htmlInput: { "aria-label": "Find a page" }, input: {
            startAdornment: <InputAdornment position="start"><Search size={15} /></InputAdornment>,
            endAdornment: search ? <InputAdornment position="end"><IconButton size="small" aria-label="Clear page search" onClick={() => setSearch("")}><X size={13} /></IconButton></InputAdornment> : undefined,
          } }}
          sx={{ "& .MuiInputBase-root": { fontSize: 12, bgcolor: "background.paper" }, "& input": { py: .9 } }} />
      </UiBox>}
      {query ? <UiSection aria-label="Matching pages">
        {matches.length ? matches.map(item => renderItem(item)) : <UiBox role="status" className="px-2 py-3 text-xs">No matching pages</UiBox>}
      </UiSection> : <>
      {visibleGroups.map(group => <UiSection key={group.title} className="mt-1.5 border-t border-line pt-1.5 first-of-type:mt-0 first-of-type:border-0">
        {!collapsed && <ListSubheader component="div" disableSticky sx={{ bgcolor: "transparent", px: 1, fontSize: 10, fontWeight: 750, lineHeight: "24px", textTransform: "uppercase", letterSpacing: 1 }}>{group.title}</ListSubheader>}
        {group.items.map(item => renderItem(item))}
      </UiSection>)}
      {administration.length > 0 && <UiSection className="mt-1.5 border-t border-line pt-1.5">
        {!collapsed && <ListSubheader component="div" disableSticky sx={{ bgcolor: "transparent", px: 1, fontSize: 10, fontWeight: 750, lineHeight: "24px", textTransform: "uppercase", letterSpacing: 1 }}>Administration</ListSubheader>}
        {administration.map(item => renderItem(item))}
      </UiSection>}
      </>}
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
    const [profileAnchor, setProfileAnchor] = useState<HTMLButtonElement | null>(null);
    const profileMenuId = useId();
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const hidden = pathname === "/login" || pathname === "/admin-login" || pathname === "/signup" || pathname === "/forgot-password" || pathname === "/reset-password" || pathname === "/integrations/gmail/callback" || pathname.startsWith("/portal/") || pathname.startsWith("/invite/") || pathname.startsWith("/admin-console");
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
    function getBreadcrumbPaths(items: NavItem[]): string[] {
        return items.flatMap(item => [item.href, ...getBreadcrumbPaths(item.children || [])]);
    }
    const closeProfile = () => setProfileAnchor(null);
    const breadcrumbPaths = groups.flatMap(group => getBreadcrumbPaths(filterNavigation(group.items, profile)));
    return <WorkspaceAccessContext.Provider value={profile}><UiBox sx={{ "--workspace-navbar-height": "56px", ...(pathname === "/" ? { "@media (min-width: 900px)": { height: "100dvh", minHeight: 0, display: "flex", flexDirection: "column", "& > header, & > .border-b": { flexShrink: 0 } } } : {}) }} className={`min-h-screen transition-[padding] duration-200 ${sidebarCollapsed ? "lg:pl-[68px]" : "lg:pl-[248px]"}`}>
    <Drawer variant="permanent" sx={{ display: { xs: "none", lg: "block" }, "& .MuiDrawer-paper": { width: sidebarCollapsed ? 68 : 248, boxSizing: "border-box", display: "flex", flexDirection: "column", overflow: "hidden", py: 1.25, px: sidebarCollapsed ? .75 : 1.25, bgcolor: "background.default", borderRight: "1px solid", borderColor: "divider", transition: "width 200ms" } }}>
      <UiBox sx={{ flexShrink: 0 }} className={`flex items-center ${sidebarCollapsed ? "justify-center" : "justify-between"}`}><Link href="/" title="KriyoPay overview" aria-label="KriyoTech KriyoPay overview" className={`flex min-w-0 items-center ${sidebarCollapsed ? "justify-center" : "gap-2 px-1"}`}>{sidebarCollapsed ? <Image src="/kriyotech-monogram-ivory.jpg" alt="KriyoTech" width={40} height={40} className="h-10 w-10 rounded-xl object-cover" priority/> : <UiSpan className="flex min-w-0 flex-col items-start gap-1"><UiSpan className="inline-flex rounded-md bg-white px-2 py-1"><Image src="/kriyotech-logistics-wordmark.png" alt="KriyoTech" width={140} height={38} className="h-auto w-[140px]" priority/></UiSpan><UiSpan className="pl-1 text-[9px] font-semibold tracking-[.12em] text-slate-500"><ProductName/> · TRANSPORT ERP</UiSpan></UiSpan>}</Link>{!sidebarCollapsed && <UiIconButton type="button" onClick={toggleSidebar} title="Collapse sidebar" aria-label="Collapse sidebar" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-slate-100"><PanelLeftClose size={17}/></UiIconButton>}</UiBox>
      {sidebarCollapsed ? <UiBox className="mt-3 flex shrink-0 justify-center" title={profile?.tenant || "Your workspace"}><UiSpan className="grid h-8 w-8 place-items-center rounded-lg bg-mint text-[10px] font-bold text-forest">{(profile?.tenant || "KP").slice(0, 2).toUpperCase()}</UiSpan></UiBox> : <UiBox sx={{ bgcolor: "background.paper", flexShrink: 0 }} className="mt-3 rounded-lg border border-line px-3 py-2"><UiStrong className="block truncate text-xs">{profile?.tenant || "Your workspace"}</UiStrong><UiSpan className="text-[10px] text-slate-400">{profile?.workspace_key || savedWorkspaceKey || "Sign in to connect"}</UiSpan>{workspaces.length > 1 && <UiLabel className="mt-2 block text-[10px] font-semibold text-slate-500">Switch company<UiSelect aria-label="Switch workspace" value={profile?.workspace_key || savedWorkspaceKey} onChange={e => switchWorkspace(e.target.value)} className="mt-1 w-full rounded-md border border-line bg-white px-2 py-1.5 text-xs text-ink">{workspaces.map(item => <option key={item.workspace_key} value={item.workspace_key}>{item.tenant}</option>)}</UiSelect></UiLabel>}</UiBox>}
      {sidebarCollapsed && <UiIconButton type="button" onClick={toggleSidebar} title="Expand sidebar" aria-label="Expand sidebar" className="mt-2 grid h-8 place-items-center rounded-lg text-slate-500 hover:bg-slate-100"><PanelLeftOpen size={17}/></UiIconButton>}
      <UiBox sx={{ flex: 1, minHeight: 0, overflowY: "auto", scrollbarWidth: "thin", mt: 1.25 }}><WorkspaceNav access={profile} pathname={pathname} summary={summary} collapsed={sidebarCollapsed}/></UiBox>
    </Drawer>
    <AppBar component="header" position="sticky" color="inherit" elevation={0} sx={{
      bgcolor: "background.paper", borderBottom: "1px solid", borderColor: "divider", zIndex: theme => theme.zIndex.appBar,
    }}>
      <Toolbar disableGutters sx={{ height: "calc(var(--workspace-navbar-height) - 1px)", minHeight: { xs: 0, sm: 0 }, px: { xs: 1, sm: 2 }, gap: 1, justifyContent: "space-between" }}>
        <UiBox sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0 }}>
          <Tooltip title={menuOpen ? "Close menu" : "Open menu"}>
            <IconButton type="button" size="small" aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
              aria-expanded={menuOpen} aria-controls={menuOpen ? "mobile-workspace-menu" : undefined} onClick={() => setMenuOpen(open => !open)}
              sx={{ display: { xs: "inline-flex", lg: "none" }, flexShrink: 0, border: "1px solid", borderColor: "divider", borderRadius: 1.5, width: 35, height: 35 }}>
              {menuOpen ? <X size={18} /> : <Menu size={18} />}
            </IconButton>
          </Tooltip>
          <ProductBreadcrumbs compact allowedPaths={breadcrumbPaths} />
        </UiBox>
        <UiBox sx={{ display: "flex", alignItems: "center", flexShrink: 0, gap: .75 }}>
          {sidebarCollapsed && profile?.tenant && <UiBox sx={{ display: { xs: "none", lg: "block" }, mr: .5, pr: 1.25, borderRight: "1px solid", borderColor: "divider" }}>
            {workspaces.length > 1 ? <UiSelect aria-label="Switch workspace" value={profile.workspace_key || savedWorkspaceKey} onChange={event => switchWorkspace(event.target.value)}
              className="max-w-48 rounded-md border border-line px-2 py-1 text-xs">{workspaces.map(item => <option key={item.workspace_key} value={item.workspace_key}>{item.tenant}</option>)}</UiSelect>
              : <UiSpan className="block max-w-48 truncate text-xs font-semibold" title={profile.tenant}>{profile.tenant}</UiSpan>}
          </UiBox>}
          <ThemeToggle />
          <NotificationBell access={profile} />
          {profile && <>
            <Tooltip title="Profile menu">
              <IconButton type="button" id={`${profileMenuId}-button`} aria-label="Open profile menu" aria-haspopup="menu"
                aria-expanded={Boolean(profileAnchor)} aria-controls={profileAnchor ? profileMenuId : undefined}
                onClick={event => setProfileAnchor(event.currentTarget)} size="small" sx={{ p: .25, ml: .25 }}>
                <Avatar sx={{ width: 34, height: 34, bgcolor: "primary.main", color: "primary.contrastText", fontSize: 12, fontWeight: 700 }}>{initials}</Avatar>
              </IconButton>
            </Tooltip>
            <MenuListPopover anchorEl={profileAnchor} open={Boolean(profileAnchor)} onClose={closeProfile}
              anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
              slotProps={{ list: { id: profileMenuId, "aria-labelledby": `${profileMenuId}-button` }, paper: { sx: { minWidth: 208, maxWidth: 280, mt: .75 } } }}>
              <UiBox sx={{ px: 2, py: .75 }}>
                <UiStrong className="block truncate text-sm">{userName}</UiStrong>
                <UiSpan className="block truncate text-xs text-slate-500">{profile.tenant}</UiSpan>
              </UiBox>
              <Divider sx={{ my: .5 }} />
              {canShowNavigation("/settings", profile) && <MenuItem component={Link} href="/settings" onClick={closeProfile}>
                <ListItemIcon><Settings2 size={16} /></ListItemIcon><ListItemText>Settings</ListItemText>
              </MenuItem>}
              <MenuItem onClick={() => { closeProfile(); logout(); }}>
                <ListItemIcon><LogOut size={16} /></ListItemIcon><ListItemText>Sign out</ListItemText>
              </MenuItem>
            </MenuListPopover>
          </>}
        </UiBox>
      </Toolbar>
    </AppBar>
    <Drawer open={menuOpen} onClose={() => setMenuOpen(false)} anchor="right" sx={{ display: { lg: "none" } }} slotProps={{ paper: { sx: { width: "min(88vw,360px)", p: 2 } } }}><UiBox id="mobile-workspace-menu" aria-label="Mobile workspace menu">
      <UiBox className="mb-4 flex items-start justify-between gap-3"><Link href="/" title="KriyoPay overview" aria-label="KriyoTech KriyoPay overview" onClick={() => setMenuOpen(false)} className="flex min-w-0 flex-col items-start gap-1"><UiSpan className="inline-flex rounded-md bg-white px-2 py-1"><Image src="/kriyotech-logistics-wordmark.png" alt="KriyoTech" width={150} height={40} className="h-auto w-[150px]" priority/></UiSpan><UiSpan className="pl-1 text-[9px] font-semibold tracking-[.12em] text-slate-500"><ProductName/> · TRANSPORT ERP</UiSpan></Link><UiIconButton aria-label="Close navigation menu" onClick={() => setMenuOpen(false)} className="grid h-9 w-9 shrink-0 place-items-center rounded-lg hover:bg-slate-100"><X size={18}/></UiIconButton></UiBox>
      <UiBox sx={{ bgcolor: "background.default" }} className="mb-4 rounded-lg border border-line px-3 py-2"><UiStrong className="block truncate text-sm">{profile?.tenant || "Your workspace"}</UiStrong><UiSpan className="text-[11px] text-slate-500">{profile?.role || "Member"}</UiSpan></UiBox>
      <WorkspaceNav access={profile} pathname={pathname} summary={summary} collapsed={false} onNavigate={() => setMenuOpen(false)}/>
    </UiBox></Drawer>
    {accessError || (profile && !canShowNavigation(pathname, profile)) ? <UiBox role="status" sx={{m:3,p:4,border:"1px solid",borderColor:"divider",borderRadius:3,bgcolor:"background.paper"}}><ShieldCheck size={28}/><h1 className="mt-4 text-xl font-semibold">Access unavailable</h1><p className="mt-2 text-sm text-slate-500">{accessError || "Your company’s feature access or your role has changed. This page is no longer available to your account. Contact your company administrator if you need access."}</p><p className="mt-2 text-xs text-slate-500">Access refreshes automatically. If it is enabled again, this page will reopen.</p></UiBox> : children}
  </UiBox></WorkspaceAccessContext.Provider>;
}
