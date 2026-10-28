"use client";

import { Children, forwardRef, isValidElement, useEffect, useRef, useState, type SelectHTMLAttributes, type ReactNode } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import { useFieldFeedback } from "@/components/form-validation";

function text(value: ReactNode): string {
  return Children.toArray(value).map(child => isValidElement<{ children?: ReactNode }>(child) ? text(child.props.children) : String(child)).join("");
}

/** A searchable selector backed by the original select for native FormData and reset semantics. */
export const EntitySelect = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function EntitySelect({ children, className, onChange, value, defaultValue, required, disabled, id, ...props }, forwardedRef) {
  const select = useRef<HTMLSelectElement | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const [selected, setSelected] = useState(String(value ?? defaultValue ?? ""));
  const [search, setSearch] = useState("");
  const feedback = useFieldFeedback(props.name);
  const options = Children.toArray(children).filter(isValidElement).map(child => {
    const option = child.props as { value?: string | number; children?: ReactNode; disabled?: boolean };
    return { value: String(option.value ?? text(option.children)), label: text(option.children), disabled: Boolean(option.disabled) };
  });
  const resetState=useRef({options,clear:feedback.clear});resetState.current={options,clear:feedback.clear};
  const chosen = String(value ?? selected);
  const placeholder = options.find(option => !option.value)?.label || "Search and select";
  const label = props["aria-label"] || props.name?.replace(/_id$/, "").replaceAll("_", " ") || placeholder;
  const chosenLabel = options.find(option => option.value === chosen)?.label || "";
  useEffect(() => { if (chosen) setSearch(chosenLabel); }, [chosen, chosenLabel]);
  useEffect(() => {
    input.current?.setCustomValidity(required && !chosen ? "Choose a record from the list." : "");
  }, [required, chosen]);
  useEffect(() => {
    const form = select.current?.form;
    const reset = () => { setSelected(String(defaultValue ?? "")); setSearch(resetState.current.options.find(option => option.value === String(defaultValue ?? ""))?.label || ""); resetState.current.clear(); };
    form?.addEventListener("reset", reset);
    return () => form?.removeEventListener("reset", reset);
  }, [defaultValue]);
  return <span className={className} style={{ display: "inline-block", minWidth: 0 }}>
    <select {...props} ref={element => { select.current = element; if (typeof forwardedRef === "function") forwardedRef(element); else if (forwardedRef) forwardedRef.current = element; }}
      value={chosen} disabled={disabled} onChange={event => { setSelected(event.target.value); onChange?.(event); }} tabIndex={-1} aria-hidden="true" style={{ display: "none" }}>{!options.some(option=>option.value==="")&&<option value=""/>}{children}</select>
    <Autocomplete fullWidth size="small" inputValue={search} onInputChange={(_, text, reason) => {
      if (reason === "input") {
        setSearch(text);
        if (chosen && text !== chosenLabel) { setSelected(""); if (select.current) { select.current.value=""; select.current.dispatchEvent(new Event("change",{bubbles:true})); } }
      } else if (reason === "clear") setSearch("");
    }} options={options.filter(option => option.value)} value={options.find(option => option.value === chosen) || null}
      disabled={disabled} getOptionLabel={option => option.label} getOptionDisabled={option => option.disabled} isOptionEqualToValue={(a, b) => a.value === b.value}
      onChange={(_, option) => {
        const next = option?.value || "";
        setSelected(next); setSearch(option?.label || ""); feedback.clear();
        input.current?.setCustomValidity(required && !next ? "Choose a record from the list." : "");
        if (select.current) { select.current.value = next; select.current.dispatchEvent(new Event("change", { bubbles: true })); }
      }}
      renderInput={params => <TextField {...params} id={id} inputRef={input} placeholder={placeholder} required={required} error={Boolean(feedback.error)} helperText={feedback.error || undefined}
        onInvalid={event => { event.preventDefault(); feedback.invalid(event.target as HTMLInputElement); }}
        slotProps={{ ...params.slotProps, htmlInput: { ...params.slotProps.htmlInput, "aria-label": label, "data-field-name": props.name } }} />}
    />
  </span>;
});
