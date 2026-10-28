"use client";
import NextLink from "next/link";
import { forwardRef, type HTMLAttributes, type ButtonHTMLAttributes, type InputHTMLAttributes, type SelectHTMLAttributes, type ComponentProps } from "react";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ValidatedForm, useFieldFeedback } from "@/components/form-validation";
import { cn } from "@/lib/utils";
export { Table as UiTable, TableHeader as UiTableHead, TableBody as UiTableBody, TableRow as UiTableRow, TableHead as UiTh, TableCell as UiTd } from "@/components/ui/table";
export const UiForm = ValidatedForm;
export const UiBox = forwardRef<HTMLDivElement,HTMLAttributes<HTMLDivElement>>(function UiBox(props,ref){return <div ref={ref} {...props}/>;});
export function UiMain(props:HTMLAttributes<HTMLElement>){return <main {...props}/>;}
export function UiNav(props:HTMLAttributes<HTMLElement>){return <nav {...props}/>;}
export function UiSection({className,...props}:HTMLAttributes<HTMLElement>){return <section className={cn(className?.includes("bg-white")&&"rounded-xl border border-border bg-card shadow-sm",className)} {...props}/>;}
export function UiArticle({className,...props}:HTMLAttributes<HTMLElement>){return <article className={cn("rounded-xl border border-border bg-card shadow-sm",className)} {...props}/>;}
export function UiText(props:HTMLAttributes<HTMLParagraphElement>){return <p {...props}/>;}
export function UiH1({className,...props}:HTMLAttributes<HTMLHeadingElement>){return <h1 className={cn("text-2xl font-semibold tracking-tight text-foreground md:text-[28px]",className)} {...props}/>;}
export function UiH2({className,...props}:HTMLAttributes<HTMLHeadingElement>){return <h2 className={cn("text-base font-semibold tracking-tight",className)} {...props}/>;}
export function UiStrong(props:HTMLAttributes<HTMLElement>){return <strong {...props}/>;}
export function UiSmall(props:HTMLAttributes<HTMLElement>){return <small {...props}/>;}
export function UiSpan({className,children,...props}:HTMLAttributes<HTMLSpanElement>){return className?.includes("rounded-full")&&!className.includes("grid")?<Badge variant="secondary" className={className} {...props}>{children}</Badge>:<span className={className} {...props}>{children}</span>;}
export function UiLabel({className,...props}:HTMLAttributes<HTMLLabelElement>&{htmlFor?:string}){return <Label className={cn("block text-xs font-medium text-foreground",className)} {...props}/>;}
export const UiButton=forwardRef<HTMLButtonElement,ButtonHTMLAttributes<HTMLButtonElement>>(function UiButton({className,type="submit",...props},ref){
  const variant=/bg-(?:rose|red)/.test(className||"")?"destructive":/bg-(?:forest|emerald-[6789])/.test(className||"")?"default":className?.includes("border")?"outline":"ghost";
  return <Button ref={ref} type={type} variant={variant} className={cn("rounded-lg",className)} {...props}/>;
});
export const UiInput=forwardRef<HTMLInputElement,InputHTMLAttributes<HTMLInputElement>&{helperText?:string;error?:boolean}>(function UiInput({name,className,helperText,error,onChange,onInvalid,...props},ref){
  const feedback=useFieldFeedback(name),invalid=Boolean(error||feedback.error);
  if(props.type==="hidden")return <input ref={ref} name={name} {...props}/>;
  if(props.type==="checkbox")return <input ref={ref} name={name} className={cn("size-4 accent-forest",className)} {...props} onChange={onChange}/>;
  return <><Input ref={ref} name={name} {...props} className={cn("rounded-lg bg-white",invalid&&"border-red-500",className)} aria-invalid={invalid||undefined} onChange={event=>{feedback.clear();onChange?.(event);}} onInvalid={event=>{feedback.invalid(event.currentTarget);onInvalid?.(event);}}/>{(feedback.error||helperText)&&<span className={cn("mt-1 block text-xs",invalid?"text-red-700":"text-muted-foreground")}>{feedback.error||helperText}</span>}</>;
});
export const UiSelect=forwardRef<HTMLSelectElement,SelectHTMLAttributes<HTMLSelectElement>>(function UiSelect({className,onChange,name,...props},ref){const feedback=useFieldFeedback(name);return <><select ref={ref} name={name} className={cn("h-10 rounded-lg border border-input bg-white px-3 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",className)} {...props} aria-invalid={Boolean(feedback.error)||undefined} onChange={event=>{feedback.clear();onChange?.(event);}} onInvalid={event=>feedback.invalid(event.currentTarget)}/>{feedback.error&&<span className="mt-1 block text-xs text-red-700">{feedback.error}</span>}</>;});
export function UiAlert({className,role,...props}:HTMLAttributes<HTMLDivElement>){return <div role={role||"status"} className={cn("rounded-xl border bg-secondary px-4 py-3 text-sm leading-6",className)} {...props}/>;}
export const AppLink=forwardRef<HTMLAnchorElement,ComponentProps<typeof NextLink>>(function AppLink({className,...props},ref){return <NextLink ref={ref} className={cn("transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",className)} {...props}/>;});
export function UiModal({children,onClose}:{children:React.ReactNode;onClose?:()=>void;className?:string}){return <Dialog open onOpenChange={open=>{if(!open)onClose?.();}}><DialogContent className="max-h-[90dvh] overflow-y-auto p-0 sm:max-w-xl"><DialogTitle className="sr-only">Review payment</DialogTitle><DialogDescription className="sr-only">Review the payment details before submitting your action.</DialogDescription>{children}</DialogContent></Dialog>;}
export function AdminEmpty({title,description}:{title:string;description:string}){return <Card className="flex min-h-44 flex-col items-center justify-center border-dashed p-8 text-center"><AlertCircle className="mb-3 size-6 text-muted-foreground"/><h3 className="text-sm font-semibold">{title}</h3><p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">{description}</p></Card>;}
