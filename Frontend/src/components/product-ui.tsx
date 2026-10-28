"use client";

import NextLink from "next/link";
import { ValidatedForm, useFieldFeedback } from "@/components/form-validation";
import { EntitySelect } from "@/components/entity-select";
import { Children, forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes, type HTMLAttributes, type AnchorHTMLAttributes, type ReactNode, useId } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Checkbox from "@mui/material/Checkbox";
import Switch from "@mui/material/Switch";
import Radio from "@mui/material/Radio";
import InputBase from "@mui/material/InputBase";
import NativeSelect from "@mui/material/NativeSelect";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import FormLabel from "@mui/material/FormLabel";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import Link from "@mui/material/Link";
import Dialog from "@mui/material/Dialog";
import Drawer from "@mui/material/Drawer";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import CircularProgress from "@mui/material/CircularProgress";
import TableCell from "@mui/material/TableCell";
import { ChevronDown } from "lucide-react";
export { default as UiTable } from "@mui/material/Table";
export { default as UiTableHead } from "@mui/material/TableHead";
export { default as UiTableBody } from "@mui/material/TableBody";
export { default as UiTableRow } from "@mui/material/TableRow";

// Keep layout utilities; MUI owns control borders, typography, focus and disabled states.
function layoutClasses(value = "") {
  return value.split(/\s+/).filter(token => !/^(?:(?:hover|focus|focus-visible|disabled):)*(?:border(?:-|$)|rounded(?:-|$)|bg-|text-|font-|px-|py-|p-|outline-|ring-|shadow)/.test(token)).join(" ");
}

export const UiBox = Box;
export function UiMain(props: HTMLAttributes<HTMLElement>) { return <Box component="main" {...props}/>; }
export function UiHeader(props: HTMLAttributes<HTMLElement>) { return <Box component="header" {...props}/>; }
export function UiAside(props: HTMLAttributes<HTMLElement>) { return <Box component="aside" {...props}/>; }
export function UiFooter(props: HTMLAttributes<HTMLElement>) { return <Box component="footer" {...props}/>; }
export function UiNav(props: HTMLAttributes<HTMLElement>) { return <Box component="nav" {...props}/>; }
export function UiSection(props: HTMLAttributes<HTMLElement>) {
  return props.className?.includes("bg-white") ? <Paper component="section" variant="outlined" {...props}/> : <Box component="section" {...props}/>;
}
export function UiArticle(props: HTMLAttributes<HTMLElement>) { return <Card component="article" variant="outlined" {...props}/>; }
export const UiForm = ValidatedForm;
export function UiLabel({color: _color,className,...props}: HTMLAttributes<HTMLLabelElement> & { htmlFor?: string }) { const color=className?.includes("text-white")?"#fff":"text.primary"; return <FormLabel component="label" className={className} {...props} sx={{ color, fontSize: 12, fontWeight: 600, "&.Mui-focused": { color } }}/>; }

export const UiButton = forwardRef<HTMLButtonElement,ButtonHTMLAttributes<HTMLButtonElement>>(function UiButton({className = "",type = "submit",children,color: _nativeColor,...props},ref) {
  const color = /rose|red-/.test(className) ? "error" : /emerald/.test(className) ? "success" : "primary";
  const variant = /bg-(?:forest|emerald-[6789]|rose-[6789]|slate-[789])/.test(className) ? "contained" : /border/.test(className) ? "outlined" : "text";
  return <Button ref={ref} type={type} color={color} variant={variant} size="small" disableElevation className={layoutClasses(className)} {...props}>{children}</Button>;
});
export const UiIconButton = forwardRef<HTMLButtonElement,ButtonHTMLAttributes<HTMLButtonElement>>(function UiIconButton({className = "",type = "submit",color: _nativeColor,...props},ref) {
  return <IconButton ref={ref} type={type} size="small" color="inherit" className={layoutClasses(className)} {...props}/>;
});

export const UiInput = forwardRef<HTMLInputElement,InputHTMLAttributes<HTMLInputElement> & { helperText?: ReactNode; error?: boolean }>(function UiInput({className, type="text", onChange, value, defaultValue, disabled, required, name, id, size: _size, helperText, error, onInvalid, onBlur, ...props},ref) {
  const feedback = useFieldFeedback(name);
  if (type === "hidden") return <input type="hidden" ref={ref} name={name} id={id} disabled={disabled} value={value} defaultValue={defaultValue} {...props}/>;
  if (type === "checkbox" || type === "radio") {
    const Component = type === "checkbox" ? /^(enabled|active|trial_enabled)$/.test(name || "") ? Switch : Checkbox : Radio;
    return <Component size="small" disabled={disabled} required={required} name={name} id={id} value={value} onChange={onChange}
      checked={props.checked} defaultChecked={props.defaultChecked} className={layoutClasses(className)} slotProps={{ input: { ...props, ref } }}/>;
  }
  if (type === "file") return <InputBase type="file" disabled={disabled} required={required} name={name} id={id} inputRef={ref} onChange={onChange}
    className={className} slotProps={{ input: props }} sx={{ display:className?.split(/\s+/).includes("hidden")?"none":undefined, fontSize: 12, maxWidth: "100%", "& input::file-selector-button": { border: 0, borderRadius: 6, padding: "8px 12px", marginRight: 8, background: "#e4f1eb", color: "#17634f", cursor: "pointer" } }}/>;
  return <TextField type={type} size="small" variant="outlined" disabled={disabled} required={required} name={name} id={id}
    inputRef={ref} onChange={event => { feedback.clear(); onChange?.(event as React.ChangeEvent<HTMLInputElement>); }} onBlur={event => { if (!event.target.validity.valid) feedback.invalid(event.target as HTMLInputElement); onBlur?.(event as React.FocusEvent<HTMLInputElement>); }}
    error={Boolean(error || feedback.error)} helperText={feedback.error || helperText} value={value} defaultValue={defaultValue} className={layoutClasses(className)}
    slotProps={{ htmlInput: { ...props, onInvalid: (event: React.InvalidEvent<HTMLInputElement>) => { event.preventDefault(); feedback.invalid(event.currentTarget); onInvalid?.(event); } } }} sx={{ minWidth: 0, verticalAlign: "middle" }}/>;
});

export const UiTextarea = forwardRef<HTMLTextAreaElement,TextareaHTMLAttributes<HTMLTextAreaElement>>(function UiTextarea({className, rows=3, onChange, value, defaultValue, disabled, required, name, id,onInvalid,...props},ref) {
  const feedback = useFieldFeedback(name);
  return <TextField multiline rows={rows} size="small" disabled={disabled} required={required} name={name} id={id} inputRef={ref}
    onChange={event => { feedback.clear(); onChange?.(event as React.ChangeEvent<HTMLTextAreaElement>); }} error={Boolean(feedback.error)} helperText={feedback.error || undefined} value={value} defaultValue={defaultValue} className={layoutClasses(className)} slotProps={{ htmlInput: { ...props, onInvalid: (event: React.InvalidEvent<HTMLTextAreaElement>) => { event.preventDefault(); feedback.invalid(event.currentTarget); onInvalid?.(event); } } }}/>;
});

export const UiSelect = forwardRef<HTMLSelectElement,SelectHTMLAttributes<HTMLSelectElement>>(function UiSelect({className,children,onChange,value,defaultValue,disabled,required,...props},ref) {
  const feedback=useFieldFeedback(props.name);
  if (!props.multiple && /vendor|supplier|customer|driver|vehicle|truck|purchase_order|^po_id$|transport_order/.test(`${props.name || ""} ${props["aria-label"] || ""}`.toLowerCase())) return <EntitySelect ref={ref} {...props} className={layoutClasses(className)} onChange={onChange} value={value} defaultValue={defaultValue} disabled={disabled} required={required}>{children}</EntitySelect>;
  return <FormControl size="small" error={Boolean(feedback.error)} disabled={disabled} required={required} className={layoutClasses(className)} sx={{ minWidth: 0, verticalAlign: "middle" }}>
    <NativeSelect value={value} defaultValue={defaultValue} onChange={event=>{feedback.clear();onChange?.(event);}} disableUnderline inputProps={{ ...props, inputRef: ref, onInvalid:(event:React.InvalidEvent<HTMLSelectElement>)=>{event.preventDefault();feedback.invalid(event.currentTarget);props.onInvalid?.(event);} }}
      sx={{ fontSize: 13, bgcolor: "background.paper", border: "1px solid", borderColor: "#cbd5e1", borderRadius: 1, "& select": { px: 1.5, py: 1.1, minHeight: "1.45em" }, "&:focus-within": { outline: "2px solid #17634f", outlineOffset: -1 }, "&.Mui-disabled": { opacity: 0.6 } }}>{children}</NativeSelect>
    {feedback.error&&<FormHelperText>{feedback.error}</FormHelperText>}
  </FormControl>;
});

type TextProps = HTMLAttributes<HTMLElement> & { children?: ReactNode };
export function UiText({className,...props}: TextProps) { return <Typography component="p" variant="body2" className={className} {...props}/>; }
export function UiSpan({className = "",children,color: _color,...props}: TextProps) {
  if (className.includes("rounded-full") && !/\bgrid\b|\bh-\d/.test(className)) return <Chip component="span" size="small" label={children} color={/rose|red-/.test(className)?"error":/emerald|green|mint|forest/.test(className)?"success":/amber|orange/.test(className)?"warning":/blue|sky/.test(className)?"info":"default"} className={layoutClasses(className)} {...props} sx={{ height: "auto", minHeight: 22, fontSize: 11, fontWeight: 600, "& .MuiChip-label": { px: 1, py: 0.3 } }}/>;
  return <Typography component="span" variant="inherit" className={className} {...props}>{children}</Typography>;
}
export function UiH1(props: TextProps) { return <Typography component="h1" variant="h4" {...props}/>; }
export function UiH2(props: TextProps) { return <Typography component="h2" variant="h6" {...props}/>; }
export function UiH3(props: TextProps) { return <Typography component="h3" variant="subtitle1" {...props}/>; }
export function UiH4(props: TextProps) { return <Typography component="h4" variant="subtitle2" {...props}/>; }
export function UiStrong(props: TextProps) { return <Typography component="strong" variant="inherit" sx={{ fontWeight: 700 }} {...props}/>; }
export function UiSmall(props: TextProps) { return <Typography component="small" variant="caption" {...props}/>; }
export function UiAlert({className = "",role,color: _color,...props}: HTMLAttributes<HTMLDivElement>) { return <Alert severity={/rose|red/.test(className) ? "error" : /amber|yellow/.test(className) ? "warning" : /emerald|green/.test(className) ? "success" : "info"} className={layoutClasses(className)} role={role || "status"} {...props}/>; }
export const UiLink = forwardRef<HTMLAnchorElement,AnchorHTMLAttributes<HTMLAnchorElement>>(function UiLink({className,...props},ref) { return <Link ref={ref} className={className} underline="hover" {...props}/>; });
export const AppLink = forwardRef<HTMLAnchorElement,React.ComponentProps<typeof NextLink>>(function AppLink({className,children,color: _color,href,...props},ref) {
  if (typeof href==="string" && /bg-forest|bg-emerald-[6789]/.test(className || "")) return <Button component={NextLink} ref={ref} href={href} variant="contained" className={layoutClasses(className)} {...props}>{children}</Button>;
  if (typeof href==="string" && /\bborder(?:\s|-line)/.test(className || "")) return <Button component={NextLink} ref={ref} href={href} variant="outlined" className={layoutClasses(className)} {...props}>{children}</Button>;
  return <Link component={NextLink} ref={ref} href={href} underline="hover" className={className} {...props}>{children}</Link>;
});
export function UiTh({align,...props}: React.ThHTMLAttributes<HTMLTableCellElement>) { return <TableCell component="th" variant="head" align={align === "char" ? "left" : align} {...props}/>; }
export function UiTd({align,...props}: React.TdHTMLAttributes<HTMLTableCellElement>) { return <TableCell component="td" align={align === "char" ? "left" : align} {...props}/>; }

export function UiSummary({children,...props}: HTMLAttributes<HTMLElement>) { return <AccordionSummary expandIcon={<ChevronDown size={16}/>} {...props}>{children}</AccordionSummary>; }
export function UiDetails({children,className,open,...props}: React.DetailsHTMLAttributes<HTMLDetailsElement>) {
  const [summary,...content] = Children.toArray(children);
  return <Accordion defaultExpanded={open} disableGutters className={className} sx={{ boxShadow: "none", border: "1px solid #e2e8f0", "&:before": { display: "none" } }} id={props.id}>{summary}<AccordionDetails>{content}</AccordionDetails></Accordion>;
}
type ModalProps = HTMLAttributes<HTMLDivElement> & { onClose?: () => void };
export function UiModal({children,onClose}: ModalProps) {
  const id = useId();
  return <Dialog open fullWidth maxWidth="md" onClose={onClose} aria-label="Record details" aria-describedby={id}><Box id={id} sx={{"& > form":{width:"100%",maxWidth:"none"}}}>{children}</Box></Dialog>;
}
export function UiReviewDrawer({children,onClose}: ModalProps) { return <Drawer open anchor="right" onClose={onClose} slotProps={{ paper: { role:"dialog", "aria-label":"Review invoice", "aria-modal":true, sx: { width: { xs: "100%", md: 820 }, maxWidth: "100%", p: 0 } } }}><Box sx={{ minWidth: 0,"& > form":{maxHeight:"none",minHeight:"100vh",maxWidth:"none",borderRadius:0} }}>{children}</Box></Drawer>; }
export function UiSpinner({size=16,className}: {size?:number;className?:string}) { return <CircularProgress size={size} color="inherit" className={className?.replace("animate-spin","")}/>; }

