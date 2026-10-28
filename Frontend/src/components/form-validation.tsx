"use client";

import { createContext, forwardRef, useContext, useEffect, useRef, useState, type FormHTMLAttributes } from "react";
import Box from "@mui/material/Box";

type Errors = Record<string, string>;
const ValidationContext = createContext<{ errors: Errors; epoch: number; clear: (name: string) => void }>({ errors: {}, epoch: 0, clear: () => {} });

export function applyFieldErrors(form: HTMLFormElement, payload: unknown) {
  const errors: Errors = {};
  function visit(value: unknown, path: string) {
    if (Array.isArray(value) && value.every(item => typeof item === "string")) errors[path] = value.join(" ");
    else if (value && typeof value === "object") Object.entries(value).forEach(([key, item]) => visit(item, path ? `${path}.${key}` : key));
    else if (typeof value === "string" && path) errors[path] = value;
  }
  const body = payload as { error?: { details?: unknown }; details?: unknown } | null;
  visit(body?.error?.details || body?.details || payload, "");
  form.dispatchEvent(new CustomEvent("kriyopay:field-errors", { detail: errors }));
}

export function useFieldFeedback(name?: string) {
  const context = useContext(ValidationContext);
  const [localError, setLocalError] = useState("");
  useEffect(() => setLocalError(""), [context.epoch]);
  return {
    error: (name && context.errors[name]) || localError,
    invalid: (element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement) => setLocalError(element.validationMessage || "Check this value."),
    clear: () => { setLocalError(""); if (name) context.clear(name); },
  };
}

export const ValidatedForm = forwardRef<HTMLFormElement, FormHTMLAttributes<HTMLFormElement>>(function ValidatedForm({ children, onSubmit, onReset, ...props }, forwardedRef) {
  const ref = useRef<HTMLFormElement | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const form = ref.current;
    if (!form) return;
    const listener = (event: Event) => {
      const next = (event as CustomEvent<Errors>).detail;
      setErrors(next);
      requestAnimationFrame(() => {
        const field = Array.from(form.querySelectorAll<HTMLElement>("input, textarea, select")).find(item => item.offsetParent !== null && (("name" in item && next[String(item.name)]) || next[item.dataset.fieldName || ""]));
        if (field instanceof HTMLElement) { field.focus(); field.scrollIntoView({ block: "center", behavior: "auto" }); }
      });
    };
    form.addEventListener("kriyopay:field-errors", listener);
    return () => form.removeEventListener("kriyopay:field-errors", listener);
  }, []);
  return <ValidationContext.Provider value={{ errors, epoch, clear: name => setErrors(current => { if (!current[name]) return current; const next = { ...current }; delete next[name]; return next; }) }}>
    <Box component="form" {...props} noValidate ref={(element: HTMLFormElement | null) => { ref.current = element; if (typeof forwardedRef === "function") forwardedRef(element); else if (forwardedRef) forwardedRef.current = element; }}
      onReset={event => { setErrors({}); setEpoch(current=>current+1); onReset?.(event); }}
      onSubmit={event => {
        if (!props.noValidate && !event.currentTarget.checkValidity()) {
          event.preventDefault();
          const invalid = event.currentTarget.querySelector<HTMLElement>(":invalid");
          invalid?.focus(); invalid?.scrollIntoView({ block: "center", behavior: "auto" });
          return;
        }
        onSubmit?.(event);
      }}>{children}</Box>
  </ValidationContext.Provider>;
});
