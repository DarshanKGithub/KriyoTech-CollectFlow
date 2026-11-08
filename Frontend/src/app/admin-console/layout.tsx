"use client";
import { ProductName } from "@/components/partner-brand";
import { authStorage } from "@/lib/partner";

import { ThemeToggle } from "@/components/theme-toggle";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Activity, Building2, CreditCard, LayoutDashboard, LogOut, Package, ShieldCheck, UsersRound, Settings, PanelLeftClose, PanelLeftOpen, Search, ChevronRight, ChevronDown, Menu, Command, ArrowUpRight } from "lucide-react";
import { accessToken, apiFetch, refreshToken } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { AdminIdentityContext, type AdminIdentity } from "@/components/admin/admin-context";
import "./admin.css";
const navigation=[
  {label:"Overview",href:"/admin-console",icon:LayoutDashboard,group:"Workspace",description:"Platform performance and priorities"},
  {label:"Companies",href:"/admin-console/companies",icon:Building2,group:"Workspace",description:"Onboarding, access and company accounts"},
  {label:"Plans & features",href:"/admin-console/plans",icon:Package,group:"Workspace",description:"Pricing, limits and feature access"},
  {label:"Subscriptions",href:"/admin-console/subscriptions",icon:UsersRound,group:"Billing & revenue",description:"Subscription records and lifecycle"},
  {label:"Payments",href:"/admin-console/payments",icon:CreditCard,group:"Billing & revenue",description:"Payments, refunds and provider events"},
  {label:"Settlement sources",href:"/admin-console/settlements",icon:Activity,group:"Billing & revenue",description:"Reviewed platform settlement evidence"},
  {label:"Usage",href:"/admin-console/usage",icon:Activity,group:"Governance",description:"Company usage and limits"},
  {label:"Audit log",href:"/admin-console/audit-logs",icon:ShieldCheck,group:"Governance",description:"Recorded administrative activity"},
  {label:"Security",href:"/admin-console/security",icon:Settings,group:"Governance",description:"Staff access, passwords and service health"}
];
const roleNavigation:Record<string,string[]>={
  SUPER_ADMIN:navigation.map(item=>item.label),
  ADMIN:["Overview","Companies","Plans & features","Subscriptions","Usage","Payments","Audit log"],
  SUPPORT:["Overview","Companies","Subscriptions","Usage"],
  BILLING_ADMIN:["Overview","Plans & features","Subscriptions","Usage","Payments","Settlement sources","Audit log"],
  READ_ONLY:["Overview","Companies","Subscriptions","Usage","Audit log"]
};
export default function AdminLayout({children}:{children:React.ReactNode}) {
  const path=usePathname();
  const [staff,setStaff]=useState<AdminIdentity|null>(null),[error,setError]=useState("");
  const [collapsed,setCollapsed]=useState(false),[mobile,setMobile]=useState(false),[searchOpen,setSearchOpen]=useState(false),[query,setQuery]=useState("");
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{try{setCollapsed(authStorage.getItem("kriyopay:admin:collapsed")==="true");}catch{}},[]);
  useEffect(()=>{
    let active=true;setError("");
    if(!accessToken()&&!refreshToken()){window.location.assign("/login?next="+encodeURIComponent(window.location.pathname+window.location.search));return;}
    apiFetch("/admin/auth/me").then(async response=>{const body=await response.json().catch(()=>({}));if(!response.ok)throw new Error(body.detail||body.error|| (response.status===403?"Your account does not have internal administrator access.":"The admin service is unavailable. Please retry."));if(active)setStaff(body);}).catch(e=>{if(active)setError(e.message);});
    return()=>{active=false;};
  },[attempt]);
  useEffect(()=>{setMobile(false);setSearchOpen(false);setQuery("");},[path]);
  useEffect(()=>{function shortcut(event:KeyboardEvent){if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="k"){event.preventDefault();setSearchOpen(value=>!value);}}window.addEventListener("keydown",shortcut);return()=>window.removeEventListener("keydown",shortcut);},[]);
  const allowed=navigation.filter(item=>roleNavigation[staff?.role||""]?.includes(item.label)&&(item.label!=="Resellers"||staff?.is_platform===true)&&(item.label!=="Brand settings"||staff?.is_platform===false));
  const current=navigation.find(item=>item.href===path)||navigation.find(item=>item.href!=="/admin-console"&&path.startsWith(item.href));
  function toggle(){setCollapsed(value=>{try{authStorage.setItem("kriyopay:admin:collapsed",String(!value));}catch{}return !value;});}
  async function logout(){
    const refresh=authStorage.getItem("kriyopay_refresh")||"";
    try{await apiFetch("/admin/auth/logout",{method:"POST",body:JSON.stringify({refresh})});}catch{}finally{["kriyopay_access","kriyopay_refresh","kriyopay_workspace"].forEach(key=>authStorage.removeItem(key));window.location.assign("/login");}
  }
  function sidebar(compact=false){return <div className="flex h-full flex-col">
    <Link href="/admin-console" className={cn("flex h-[76px] shrink-0 items-center gap-3 px-5",compact&&"justify-center px-0")} aria-label="KriyoPay admin home"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-forest text-white shadow-sm"><ShieldCheck size={19}/></span>{!compact&&<span><strong className="block text-[17px] tracking-tight text-foreground"><ProductName/></strong><span className="text-[9px] font-semibold uppercase tracking-[.2em] text-muted-foreground">Administration</span></span>}</Link>
    <Separator/>
    <div className={cn("mx-4 mt-5 flex items-center gap-2.5 rounded-xl border bg-secondary/60 p-3",compact&&"mx-3 justify-center p-2")}><span className="grid size-7 shrink-0 place-items-center rounded-lg bg-white text-forest"><Building2 size={15}/></span>{!compact&&<div><p className="text-xs font-semibold">Administration workspace</p><p className="mt-0.5 text-[10px] text-muted-foreground">Company access and operations</p></div>}</div>
    <nav aria-label="Admin navigation" className="flex-1 overflow-y-auto px-3 py-4">{["Workspace","Billing & revenue","Governance"].map(group=>{
      const items=allowed.filter(item=>item.group===group);return items.length?<div key={group} className="mb-5">{!compact&&<p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[.13em] text-muted-foreground">{group}</p>}{items.map(item=>{
        const active=item.href===path||(item.href!=="/admin-console"&&path.startsWith(item.href));
        const link=<Link href={item.href} onClick={()=>setMobile(false)} aria-current={active?"page":undefined} aria-label={compact?item.label:undefined} className={cn("mb-1 flex h-10 items-center gap-3 rounded-lg px-3 text-[13px] font-medium text-slate-600 transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",active&&"bg-forest font-semibold text-white shadow-sm hover:bg-forest hover:text-white",compact&&"justify-center px-0")}><item.icon size={17} className="shrink-0"/>{!compact&&<><span className="flex-1">{item.label}</span>{active&&<ChevronRight size={14} className="opacity-70"/>}</>}</Link>;
        return compact?<Tooltip key={item.href}><TooltipTrigger asChild>{link}</TooltipTrigger><TooltipContent side="right">{item.label}</TooltipContent></Tooltip>:<div key={item.href}>{link}</div>;
      })}</div>:null;
    })}{!staff&&!error&&Array.from({length:6},(_,i)=><Skeleton key={i} className="my-3 h-9 w-full"/>)}</nav>
    <div className={cn("m-4 rounded-xl border border-emerald-100 bg-emerald-50/70 p-3",compact&&"mx-3 p-2")}><div className="flex items-center gap-2 text-forest"><ShieldCheck size={15}/>{!compact&&<span className="text-xs font-semibold">Controlled access</span>}</div>{!compact&&<p className="mt-1.5 text-[10px] leading-4 text-slate-500">Actions and access follow your staff role.</p>}</div>
    <Separator/><Button variant="ghost" className={cn("m-3 justify-start gap-3 text-muted-foreground",compact&&"justify-center px-0")} onClick={()=>void logout()} aria-label="Sign out"><LogOut size={16}/>{!compact&&"Sign out"}</Button>
  </div>;}
  return <TooltipProvider delayDuration={150}><div className="admin-portal min-h-screen bg-[#F5F7F5] text-foreground">
    <aside className={cn("fixed inset-y-0 left-0 z-40 hidden border-r border-border product-sidebar transition-[width] duration-200 lg:block",collapsed?"w-[76px]":"w-[244px]")}>{sidebar(collapsed)}</aside>
    <Sheet open={mobile} onOpenChange={setMobile}><SheetContent side="left" className="product-sidebar w-[280px] p-0"><SheetTitle className="sr-only">Admin navigation</SheetTitle><SheetDescription className="sr-only">Navigate your authorized administration pages.</SheetDescription>{sidebar()}</SheetContent></Sheet>
    <div className={cn("min-w-0 transition-[padding] duration-200",collapsed?"lg:pl-[76px]":"lg:pl-[244px]")}>
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border bg-white/95 px-4 backdrop-blur-md md:px-7">
        <div className="flex min-w-0 items-center gap-3"><Button size="icon" variant="ghost" className="hidden text-muted-foreground lg:inline-flex" onClick={toggle} aria-label={collapsed?"Expand sidebar":"Collapse sidebar"}>{collapsed?<PanelLeftOpen size={18}/>:<PanelLeftClose size={18}/>}</Button><Button size="icon" variant="ghost" className="lg:hidden" onClick={()=>setMobile(true)} aria-label="Open navigation"><Menu size={19}/></Button><Separator orientation="vertical" className="hidden h-5 lg:block"/><span className="hidden text-xs text-muted-foreground sm:inline">Administration</span><ChevronRight size={13} className="hidden text-muted-foreground sm:block"/><span className="truncate text-sm font-medium">{current?.label||"Company details"}</span></div>
        <div className="flex items-center gap-3"><Button variant="outline" className="hidden w-56 justify-between rounded-lg font-normal text-muted-foreground shadow-none md:flex" onClick={()=>setSearchOpen(true)}><span className="flex items-center gap-2"><Search size={15}/>Find a page…</span><kbd className="flex items-center gap-0.5 rounded border bg-secondary px-1 text-[10px]"><Command size={10}/>K</kbd></Button><Button size="icon" variant="ghost" className="md:hidden" onClick={()=>setSearchOpen(true)} aria-label="Search admin pages"><Search size={18}/></Button><ThemeToggle/><Badge variant="outline" className="hidden gap-1.5 border-emerald-200 bg-emerald-50 text-forest sm:flex"><ShieldCheck size={11}/>Staff access</Badge><Separator orientation="vertical" className="h-6"/><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" className="gap-2 px-1.5" aria-label="Open account menu"><span className="grid size-8 place-items-center rounded-full border border-emerald-200 bg-mint text-[11px] font-bold text-forest">{staff?.email.slice(0,2).toUpperCase()||"KP"}</span><ChevronDown size={13} className="text-muted-foreground"/></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-64"><DropdownMenuLabel><p className="truncate text-xs">{staff?.email||"Checking access…"}</p><p className="mt-1 text-[10px] font-normal text-muted-foreground">{staff?.role.replaceAll("_"," ")}</p></DropdownMenuLabel><DropdownMenuSeparator/>{staff?.role==="SUPER_ADMIN"&&<DropdownMenuItem asChild><Link href="/admin-console/security"><Settings className="mr-2 size-4"/>Security settings</Link></DropdownMenuItem>}<DropdownMenuItem onSelect={()=>void logout()}><LogOut className="mr-2 size-4"/>Sign out</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div>
      </header>
      <main className="admin-content w-full min-w-0 px-4 py-6 md:px-7 lg:px-8 lg:py-7">{error?<div role="alert" className="mx-auto mt-12 max-w-lg rounded-2xl border bg-white p-8"><ShieldCheck className="mb-4 text-forest"/><h1 className="text-xl font-semibold">Admin access unavailable</h1><p className="my-3 text-sm leading-6 text-muted-foreground">{error}</p><Button variant="outline" onClick={()=>setAttempt(value=>value+1)}>Retry connection</Button></div>:staff?<AdminIdentityContext.Provider value={staff}>{children}</AdminIdentityContext.Provider>:<div className="space-y-6"><Skeleton className="h-12 w-72"/><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({length:4},(_,i)=><Skeleton key={i} className="h-32 rounded-xl"/>)}</div><Skeleton className="h-80 rounded-xl"/></div>}</main>
      <footer className="flex items-center justify-between border-t border-border px-5 py-4 text-[10px] text-muted-foreground md:px-8"><span><ProductName/> · Administration</span><span>Access controlled · Actions recorded</span></footer>
    </div>
    <Dialog open={searchOpen} onOpenChange={setSearchOpen}><DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-lg"><div className="border-b p-5"><DialogTitle className="text-base">Find an admin page</DialogTitle><DialogDescription className="mt-1 text-xs">Search the pages available to your staff role.</DialogDescription><Input autoFocus placeholder="Companies, payments, security…" className="mt-4" value={query} onChange={event=>setQuery(event.target.value)}/></div><div className="max-h-80 overflow-y-auto p-2">{allowed.filter(item=>(item.label+item.description).toLowerCase().includes(query.toLowerCase())).map(item=><Link key={item.href} href={item.href} onClick={()=>setSearchOpen(false)} className="flex items-center gap-3 rounded-lg p-3 hover:bg-accent focus:bg-accent focus:outline-none"><span className="grid size-9 place-items-center rounded-lg border"><item.icon size={17}/></span><span className="flex-1"><span className="block text-sm font-medium">{item.label}</span><span className="text-[11px] text-muted-foreground">{item.description}</span></span><ArrowUpRight size={14} className="text-muted-foreground"/></Link>)}{!allowed.some(item=>(item.label+item.description).toLowerCase().includes(query.toLowerCase()))&&<p className="p-8 text-center text-sm text-muted-foreground">No matching pages. Try another name.</p>}</div></DialogContent></Dialog>
  </div></TooltipProvider>;
}
