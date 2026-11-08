"use client";
import { ProductName, usePartnerBrand } from "@/components/partner-brand";
import { authStorage, authSessionStorage, partnerHeaders } from "@/lib/partner";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Building2, Check, Eye, EyeOff, FileCheck2, LockKeyhole, ReceiptIndianRupee, ShieldCheck, Truck, ScanLine, CircleCheck, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/theme-toggle";
import { API_URL } from "@/lib/api";
import "./login.css";

type Workspace = {
    tenant: string;
    workspace_key: string;
    role: string;
};
export default function LoginPage() {
    const brand = usePartnerBrand();
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState("");
    const [sessionExpired, setSessionExpired] = useState(false);
    const [busy, setBusy] = useState(false);
    const [choices, setChoices] = useState<Workspace[]>([]);
    const [pendingTokens, setPendingTokens] = useState<{
        access: string;
        refresh: string;
    } | null>(null);
    useEffect(() => {
        setSessionExpired(new URLSearchParams(window.location.search).get("reason") === "session_expired");
    }, []);
    function nextPath(fallback: string) {
        const value = new URLSearchParams(window.location.search).get("next") || "";
        return value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/login") ? value : fallback;
    }
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setBusy(true);
        setError("");
        const form = new FormData(event.currentTarget);
        try {
            const response = await fetch(`${API_URL}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json", ...partnerHeaders() }, body: JSON.stringify({ email: form.get("email"), password: form.get("password") }) });
            if (!response.ok) {
                if (response.status === 404) throw new Error("The KriyoPay login service was not found. The frontend may be connected to another app's backend. Restart KriyoPay using start-dev.ps1.");
                if (response.status === 429) throw new Error("Too many sign-in attempts. Wait a moment before trying again.");
                if (response.status === 400 || response.status === 401) throw new Error("Email or password is incorrect for this workspace.");
                throw new Error("The sign-in service is unavailable. Please retry shortly.");
            }
            const data = await response.json();
            if (data.account_type === "ADMIN") {
                const adminData = data;
                authStorage.removeItem("kriyopay_workspace");
                if (adminData.mfa_setup_required || adminData.mfa_required) {
                    authStorage.removeItem("kriyopay_access");
                    authStorage.removeItem("kriyopay_refresh");
                    authSessionStorage.setItem("kriyopay_admin_mfa", JSON.stringify({ mode: adminData.mfa_setup_required ? "setup" : "verify", pendingToken: adminData.mfa_pending_token, role: adminData.role }));
                    window.location.assign("/admin-mfa");
                    return;
                }
                authStorage.setItem("kriyopay_access", adminData.access || data.access);
                authStorage.setItem("kriyopay_refresh", adminData.refresh || data.refresh);
                window.location.assign(nextPath("/admin-console"));
                return;
            }
            const memberships = await fetch(`${API_URL}/auth/workspaces`, { headers: { Authorization: `Bearer ${data.access}`, ...partnerHeaders() }, cache: "no-store" });
            if (!memberships.ok)
                throw new Error("Signed in, but KriyoPay could not load your company access. Please try again.");
            const workspaces: Workspace[] = await memberships.json();
            if (!workspaces.length)
                throw new Error("This account has no active company access. Ask your company administrator for an invitation.");
            setPendingTokens({ access: data.access, refresh: data.refresh });
            if (workspaces.length === 1) {
                enterWorkspace(workspaces[0], data.access, data.refresh);
                return;
            }
            setChoices(workspaces);
        }
        catch (err) {
            setError(err instanceof SyntaxError ? "The sign-in service returned an unreadable response. Check that KriyoPay's backend is running." : err instanceof TypeError ? "Could not reach KriyoPay. Start the backend and try again." : err instanceof Error ? err.message : "Could not sign in. Check that the API is available.");
        }
        finally {
            setBusy(false);
        }
    }
    function enterWorkspace(workspace: Workspace, access = pendingTokens?.access, refresh = pendingTokens?.refresh) {
        if (!access || !refresh)
            return;
        authStorage.setItem("kriyopay_access", access);
        authStorage.setItem("kriyopay_refresh", refresh);
        authStorage.setItem("kriyopay_workspace", workspace.workspace_key);
        window.location.assign(nextPath("/"));
    }
    return <main className="login-page">
      <header className="login-header">
        <Link href="/login" className="login-brand" aria-label="KriyoPay sign in"><span className="login-brand-icon"><ReceiptIndianRupee size={24}/></span><span><ProductName/><small>FINANCE. IN MOTION.</small></span></Link>
        <div className="login-header-actions"><span className="login-secure"><LockKeyhole size={13}/>Your workspace, protected</span><ThemeToggle/></div>
      </header>
      <div className="login-layout">
        <section className="login-story" aria-labelledby="login-story-title">
          <div className="login-eyebrow"><span/>YOUR BUSINESS WORKSPACE</div>
          <h1 id="login-story-title">Every invoice.<br/>Every journey.<br/><em>Under control.</em></h1>
          <p className="login-intro">Bring invoice reviews, approvals and transport operations into one clear workspace.</p>
          <div className="login-flow" aria-label="Illustration of the invoice workflow">
            <div className="login-flow-top"><span><ScanLine size={15}/>INVOICE TO PAYMENT</span><span className="login-example">Workflow preview</span></div>
            <div className="login-receipt"><div className="login-receipt-icon"><FileCheck2 size={24}/></div><div><strong>From paperwork to clarity</strong><p>Capture the details. Keep the context.</p></div><CircleCheck className="login-check" size={22}/></div>
            <div className="login-flow-steps">{[{icon:ScanLine,title:"Extract",text:"Capture invoice fields"},{icon:ShieldCheck,title:"Review",text:"Check and approve"},{icon:Check,title:"Record",text:"Track the payment"}].map((step,index)=><div key={step.title} className="login-flow-step"><span className="login-step-icon"><step.icon size={18}/></span><small>0{index+1}</small><strong>{step.title}</strong><p>{step.text}</p></div>)}</div>
            <div className="login-transport"><Truck size={18}/><span>Fleet & trips <small>Operations and driver finance, connected.</small></span><ArrowRight size={16}/></div>
          </div>
          <div className="login-trust"><span><ShieldCheck size={15}/>Approval controls</span><span><Building2 size={15}/>Company workspaces</span></div>
        </section>
        <section className="login-access" aria-labelledby="login-access-title"><div className="login-card">
          <span className="login-access-icon"><LockKeyhole size={22}/></span>
          <div className="login-eyebrow">{choices.length?"YOUR COMPANIES":`WELCOME TO ${brand.product_name.toUpperCase()}`}</div>
          <h2 id="login-access-title">{choices.length?"Choose your workspace":"Good to have you back."}</h2>
          <p className="login-card-description">{choices.length?"Select the company you want to work with.":"Sign in to pick up where you left off."}</p>
          {!choices.length?<>
            {sessionExpired&&<div role="status" className="login-notice">Your session expired. Sign in to continue where you left off.</div>}
            <form onSubmit={submit} className="login-form">
              <div><label htmlFor="login-email">Work email</label><Input id="login-email" name="email" type="email" autoComplete="username" required placeholder="you@company.com" className="login-input" disabled={busy}/></div>
              <div><div className="login-label-row"><label htmlFor="login-password">Password</label><Link href="/forgot-password">Forgot password?</Link></div><div className="login-password"><Input id="login-password" name="password" type={showPassword?"text":"password"} autoComplete="current-password" required placeholder="Enter your password" className="login-input" disabled={busy}/><button type="button" onClick={()=>setShowPassword(value=>!value)} aria-label={showPassword?"Hide password":"Show password"} aria-pressed={showPassword} disabled={busy}>{showPassword?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></div>
              {error&&<div role="alert" className="login-error">{error}</div>}
              <Button type="submit" disabled={busy} className="login-submit">{busy?<><LoaderCircle size={17} className="animate-spin"/>Signing in…</>:<>Sign in to your workspace<ArrowRight size={17}/></>}</Button>
            </form>
            <div className="login-account-note"><ShieldCheck size={18}/><p><strong>One sign-in. The right workspace.</strong><span>Company members and Super Admins sign in here. Your selected product and account role determine where you go.</span></p></div>
            <p className="login-invite-note">New to your team? Ask your company administrator for an invitation.</p>
          </>:<div className="login-workspaces">{choices.map(workspace=><button type="button" key={workspace.workspace_key} onClick={()=>enterWorkspace(workspace)}><span className="login-workspace-icon"><Building2 size={20}/></span><span><strong>{workspace.tenant}</strong><small>{workspace.role.replaceAll("_"," ")}</small></span><ArrowRight size={17}/></button>)}</div>}
        </div><p className="login-access-caption"><LockKeyhole size={12}/>Access follows your company role and permissions.</p></section>
      </div>
      <footer className="login-footer"><span>© {new Date().getFullYear()} <ProductName/></span><span>Clarity for finance. Control for operations.</span></footer>
    </main>;
}
