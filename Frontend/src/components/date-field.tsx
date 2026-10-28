"use client";

import dayjs from "dayjs";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";

/** Controlled ISO date value; submitted field names stay in YYYY-MM-DD format. */
export function DateField({value,onChange,name,required=false,disabled=false,className,label}: {
  value: string; onChange: (value: string) => void; name?: string; required?: boolean;
  disabled?: boolean; className?: string; label?: string;
}) {
  return <><DatePicker value={value ? dayjs(value) : null} onChange={date=>onChange(date ? date.isValid() ? date.format("YYYY-MM-DD") : "INVALID" : "")}
    format="DD/MM/YYYY" disabled={disabled} label={label} className={className?.split(/\s+/).filter(token=>!/^(?:border|rounded|bg-|px-|py-|text-|font-|outline|focus:)/.test(token)).join(" ")}
    slotProps={{textField:{size:"small",fullWidth:true,required,helperText:value==="INVALID"?"Enter a valid date":undefined},field:{clearable:!required}}}/>
    {name&&<input type="hidden" name={name} value={value}/>}</>;
}
