"use client";

import { PageSkeleton } from "@/components/content-skeleton";
import { WorkflowFeedback } from "@/components/workflow-feedback";
import { UiBox, UiButton, UiForm, UiH1, UiHeader, UiInput, UiLabel, UiMain, UiSection, UiSelect, UiText } from "@/components/product-ui";
import { apiFetch } from "@/lib/api";
import { useCallback, useEffect, useState, type FormEvent } from "react";

type Dock = { id:string; site_name:string; code:string; name:string; parallel_capacity:number };
type Order = { id:string; order_number:string; customer:{name:string}; origin:string; destination:string; status:string };
type Appointment = { id:string; dock_id:string; dock_name:string; site_name:string; order_id:string; order_number:string; customer:string; origin:string; destination:string; appointment_type:"PICKUP"|"DELIVERY"; starts_at:string; ends_at:string; status:string; checked_in_at:string|null; checked_out_at:string|null; loading_started_at:string|null; loading_finished_at:string|null; delay_reason:string; wait_minutes:number|null; free_minutes:number; chargeable_minutes:number; detention_estimate:string; detention_status:"OVER_FREE_TIME"|"WITHIN_FREE_TIME"|"NOT_CHECKED_IN"; notes:string };
const localInput = (date:Date) => { const adjusted=new Date(date.getTime()-date.getTimezoneOffset()*60000); return adjusted.toISOString().slice(0,16); };
const initialStart=()=>{const date=new Date();date.setHours(date.getHours()+1,0,0,0);return localInput(date);};
const appointmentStatus = (value:string) => value.toLowerCase().replaceAll("_"," ").replace(/\b\w/g, letter=>letter.toUpperCase());

export default function DockSchedulePage(){
    const [docks,setDocks]=useState<Dock[]>([]);
    const [orders,setOrders]=useState<Order[]>([]);
    const [appointments,setAppointments]=useState<Appointment[]>([]);
    const [loading,setLoading]=useState(true);
    const [busy,setBusy]=useState(false);
    const [message,setMessage]=useState("");
    const [startsAt,setStartsAt]=useState(initialStart);
    const [endsAt,setEndsAt]=useState(()=>{const date=new Date();date.setHours(date.getHours()+2,0,0,0);return localInput(date);});
    const [appointmentType,setAppointmentType]=useState<"PICKUP"|"DELIVERY">("PICKUP");
    const [detentionAppointment,setDetentionAppointment]=useState("");
    const [delayReason,setDelayReason]=useState("");
    async function detentionAction(action:string){setBusy(true);try{const r=await apiFetch(`/fleet/detention/${detentionAppointment}/${action}`,{method:"POST",body:JSON.stringify({reason:delayReason})});const d=await r.json();if(!r.ok)throw new Error(d.error);await load();setMessage(action==="prepare-billing"?"Detention revenue draft prepared. Submit the trip for independent approval before customer billing.":"Detention record updated.");}catch(e){setMessage(e instanceof Error?e.message:"Could not update detention.");}finally{setBusy(false);}}

    const load=useCallback(async()=>{
        setBusy(true);
        try{
            const [dockResponse,orderResponse,appointmentResponse]=await Promise.all([apiFetch("/fleet/docks"),apiFetch("/fleet/orders"),apiFetch("/fleet/dock-appointments")]);
            const [dockData,orderData,appointmentData]=await Promise.all([dockResponse.json(),orderResponse.json(),appointmentResponse.json()]);
            if(!dockResponse.ok||!orderResponse.ok||!appointmentResponse.ok)throw new Error(dockData.error||orderData.error||appointmentData.error||"Could not load the dock schedule.");
            setDocks(dockData);setOrders(orderData);setAppointments(appointmentData);setMessage("");
        }catch(error){setMessage(error instanceof Error?error.message:"Could not load the dock schedule.");}
        finally{setBusy(false);setLoading(false);}
    },[]);
    useEffect(()=>{void load();},[load]);

    async function createDock(event:FormEvent<HTMLFormElement>){
        event.preventDefault();const formElement=event.currentTarget;setBusy(true);setMessage("");
        const form=new FormData(event.currentTarget);
        try{const response=await apiFetch("/fleet/docks",{method:"POST",body:JSON.stringify({site_name:form.get("site_name"),code:form.get("code"),name:form.get("name"),parallel_capacity:Number(form.get("parallel_capacity"))})});const data=await response.json();if(!response.ok)throw new Error(data.error||"Could not add the dock.");formElement.reset();await load();setMessage("Dock added to this workspace.");}
        catch(error){setMessage(error instanceof Error?error.message:"Could not add the dock.");}finally{setBusy(false);}
    }

    async function bookAppointment(event:FormEvent<HTMLFormElement>){
        event.preventDefault();const formElement=event.currentTarget;setBusy(true);setMessage("");
        const form=new FormData(event.currentTarget);const start=new Date(startsAt);const end=new Date(endsAt);
        if(!Number.isFinite(start.getTime())||!Number.isFinite(end.getTime())||end<=start){setBusy(false);setMessage("Choose a valid end time after the start time.");return;}
        try{const response=await apiFetch("/fleet/dock-appointments",{method:"POST",body:JSON.stringify({dock_id:form.get("dock_id"),order_id:form.get("order_id"),appointment_type:form.get("appointment_type"),starts_at:start.toISOString(),ends_at:end.toISOString(),idempotency_key:crypto.randomUUID(),notes:form.get("notes")})});const data=await response.json();if(!response.ok)throw new Error(data.error||"Could not book this dock appointment.");formElement.reset();setStartsAt(initialStart());const nextEnd=new Date(Date.now()+2*60*60*1000);setEndsAt(localInput(nextEnd));await load();setMessage("Dock appointment booked.");}
        catch(error){setMessage(error instanceof Error?error.message:"Could not book this dock appointment.");}finally{setBusy(false);}
    }

    async function updateAppointment(row:Appointment,action:"arrive"|"start"|"complete"|"cancel"){
        const response=await apiFetch(`/fleet/dock-appointments/${row.id}/${action}`,{method:"POST",body:JSON.stringify({})});const data=await response.json();
        if(!response.ok){setMessage(data.error||"Could not update the appointment.");return;}
        await load();setMessage(`Appointment ${action === "arrive" ? "checked in" : action === "start" ? "marked as loading" : action === "complete" ? "completed" : "cancelled"}.`);
    }

    if(loading)return <PageSkeleton variant="table" label="Loading warehouse schedule"/>;
    const schedulableOrders=orders.filter(order=>appointmentType==="PICKUP"?["OPEN","ASSIGNED"].includes(order.status):order.status==="IN_TRANSIT");
    const selectedDetention=appointments.find(row=>row.id===detentionAppointment);
    const detentionRows=appointments.filter(row=>row.detention_status==="OVER_FREE_TIME");
    const estimatedDetention=detentionRows.reduce((total,row)=>total+Number(row.detention_estimate||0),0);
    return <UiMain className="w-full min-w-0 space-y-5 px-5 py-8">
        <UiHeader className="flex flex-wrap items-end justify-between gap-3"><UiBox><UiText className="text-xs font-bold uppercase tracking-widest text-forest">Fleet · Warehouse</UiText><UiH1 className="mt-1 text-2xl font-bold">Dock schedule & queue</UiH1><UiText className="mt-1 max-w-3xl text-sm text-slate-500">Reserve dock time for pickup and delivery orders, then track truck arrival and loading progress.</UiText></UiBox><UiButton type="button" disabled={busy} onClick={()=>void load()} className="rounded-lg border border-line px-3 py-2 text-sm font-semibold">{busy?"Refreshing…":"Refresh schedule"}</UiButton></UiHeader>
        {message&&<WorkflowFeedback message={message} onRefresh={()=>void load()}/>}
        <UiSection className="rounded-xl border border-line p-4"><UiText className="font-semibold">Detention evidence & billing</UiText>{selectedDetention&&<UiText className="mt-2 text-xs text-slate-500">Loading started: {selectedDetention.loading_started_at?new Date(selectedDetention.loading_started_at).toLocaleString():"Not recorded"} · Loading finished: {selectedDetention.loading_finished_at?new Date(selectedDetention.loading_finished_at).toLocaleString():"Not recorded"} · Delay reason: {selectedDetention.delay_reason||"Not recorded"}</UiText>}<UiText className="mt-1 text-xs text-slate-500">Record loading finish separately from departure. Detention drafts use the rate and free-time terms captured at check-in; the trip approval workflow approves them for billing.</UiText><UiBox className="mt-3 flex flex-wrap gap-3"><UiSelect value={detentionAppointment} onChange={e=>setDetentionAppointment(e.target.value)} className="rounded-lg border border-line p-2"><option value="">Select appointment</option>{appointments.map(a=><option key={a.id} value={a.id}>{a.order_number} · {a.dock_name} · {a.status}</option>)}</UiSelect><UiInput value={delayReason} onChange={e=>setDelayReason(e.target.value)} placeholder="Delay reason / billing evidence" maxLength={500} className="rounded-lg border border-line p-2"/>{[ ["reason","Save delay reason"],["finish-loading","Loading finished"],["prepare-billing","Prepare detention draft"] ].map(([action,label])=><UiButton key={action} disabled={busy||!detentionAppointment||(action!=="finish-loading"&&!delayReason.trim())} onClick={()=>void detentionAction(action)}>{label}</UiButton>)}</UiBox></UiSection>
        <UiSection className="grid gap-3 rounded-xl border border-line bg-white p-4 sm:grid-cols-3"><UiBox><UiText className="text-xs text-slate-500">Appointments checked in</UiText><UiText className="mt-1 text-xl font-bold">{appointments.filter(row=>row.checked_in_at&&!row.checked_out_at).length}</UiText></UiBox><UiBox><UiText className="text-xs text-slate-500">Beyond free waiting time</UiText><UiText className="mt-1 text-xl font-bold">{detentionRows.length}</UiText></UiBox><UiBox><UiText className="text-xs text-slate-500">Estimated detention exposure</UiText><UiText className="mt-1 text-xl font-bold">₹{estimatedDetention.toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})}</UiText><UiText className="text-xs text-slate-500">Operational estimate; confirm the customer contract before billing.</UiText></UiBox></UiSection>
        <UiSection className="grid gap-5 rounded-xl border border-line bg-white p-5 xl:grid-cols-[1fr_2fr]">
            <UiBox><UiText className="text-sm font-bold">Add a dock</UiText><UiText className="mt-1 text-xs text-slate-500">Capacity is the maximum number of trucks this dock can handle at the same time.</UiText><UiForm onSubmit={event=>void createDock(event)} className="mt-3 grid gap-3 sm:grid-cols-2">
                <UiLabel className="text-xs font-semibold sm:col-span-2">Warehouse / site<UiInput name="site_name" required maxLength={160} className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm" placeholder="e.g. Mumbai North Hub"/></UiLabel>
                <UiLabel className="text-xs font-semibold">Dock code<UiInput name="code" required maxLength={40} className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm" placeholder="D-01"/></UiLabel>
                <UiLabel className="text-xs font-semibold">Dock name<UiInput name="name" required maxLength={120} className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm" placeholder="Main loading bay"/></UiLabel>
                <UiLabel className="text-xs font-semibold">Parallel capacity<UiInput name="parallel_capacity" required type="number" min="1" max="100" defaultValue="1" className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm"/></UiLabel>
                <UiBox className="flex items-end"><UiButton disabled={busy} className="w-full rounded-lg bg-forest px-3 py-2 text-sm font-semibold text-white">Add dock</UiButton></UiBox>
            </UiForm></UiBox>
            <UiBox><UiText className="text-sm font-bold">Book an appointment</UiText><UiText className="mt-1 text-xs text-slate-500">Overlapping reservations are checked against dock capacity. Orders already in a different workflow state cannot be booked.</UiText><UiForm onSubmit={event=>void bookAppointment(event)} className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <UiLabel className="text-xs font-semibold">Dock<UiSelect name="dock_id" required defaultValue="" className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="" disabled>Select dock</option>{docks.map(dock=><option key={dock.id} value={dock.id}>{dock.site_name} · {dock.code} · {dock.name}</option>)}</UiSelect></UiLabel>
                <UiLabel className="text-xs font-semibold">Order<UiSelect name="order_id" required defaultValue="" className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="" disabled>Select order</option>{schedulableOrders.map(order=><option key={order.id} value={order.id}>{order.order_number} · {order.customer.name} ({order.status})</option>)}</UiSelect></UiLabel>
                <UiLabel className="text-xs font-semibold">Appointment type<UiSelect name="appointment_type" value={appointmentType} onChange={event=>setAppointmentType(event.target.value as "PICKUP"|"DELIVERY")} className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="PICKUP">Pickup</option><option value="DELIVERY">Delivery</option></UiSelect></UiLabel>
                <UiLabel className="text-xs font-semibold">Start time<DateTimeInput value={startsAt} onChange={setStartsAt}/></UiLabel>
                <UiLabel className="text-xs font-semibold">End time<DateTimeInput value={endsAt} onChange={setEndsAt}/></UiLabel>
                <UiLabel className="text-xs font-semibold">Notes<UiInput name="notes" maxLength={500} className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm" placeholder="Optional handling instructions"/></UiLabel>
                <UiBox className="sm:col-span-2 xl:col-span-3"><UiButton disabled={busy||!docks.length||!schedulableOrders.length} className="rounded-lg bg-forest px-4 py-2 text-sm font-semibold text-white">Book dock time</UiButton></UiBox>
            </UiForm></UiBox>
        </UiSection>
        <UiBox className="grid gap-3">{appointments.length===0?<UiSection className="rounded-xl border border-line bg-white p-5"><UiText className="text-sm text-slate-500">No dock appointments yet. Add a dock, then book the first order time slot.</UiText></UiSection>:appointments.map(row=><UiSection key={row.id} className="rounded-xl border border-line bg-white p-4"><UiBox className="flex flex-wrap items-start justify-between gap-3"><UiBox><UiText className="font-semibold">{row.site_name} · {row.dock_name} · {row.order_number}</UiText><UiText className="mt-1 text-sm text-slate-600">{row.appointment_type.toLowerCase()} · {row.customer} · {row.origin} → {row.destination}</UiText><UiText className="mt-1 text-xs text-slate-500">{new Date(row.starts_at).toLocaleString()} – {new Date(row.ends_at).toLocaleTimeString()} · {appointmentStatus(row.status)}{row.wait_minutes!==null?` · ${row.wait_minutes} min on site`:""}</UiText>{row.wait_minutes!==null&&<UiText className={`mt-2 text-sm font-semibold ${row.detention_status==="OVER_FREE_TIME"?"text-amber-700":"text-slate-600"}`}>{row.chargeable_minutes>0?`${row.chargeable_minutes} min beyond ${row.free_minutes} min free · estimate ₹${Number(row.detention_estimate).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})}`:`Within ${row.free_minutes} min free time`}</UiText>}</UiBox><UiBox className="flex flex-wrap gap-2">{row.status==="BOOKED"&&<><UiButton type="button" disabled={busy} onClick={()=>void updateAppointment(row,"arrive")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Check in</UiButton><UiButton type="button" disabled={busy} onClick={()=>void updateAppointment(row,"cancel")} className="rounded-lg border border-line px-3 py-2 text-xs font-semibold">Cancel</UiButton></>}{row.status==="ARRIVED"&&<UiButton type="button" disabled={busy} onClick={()=>void updateAppointment(row,"start")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Start loading</UiButton>}{row.status==="LOADING"&&<UiButton type="button" disabled={busy} onClick={()=>void updateAppointment(row,"complete")} className="rounded-lg bg-forest px-3 py-2 text-xs font-semibold text-white">Complete</UiButton>}</UiBox></UiBox>{row.notes&&<UiText className="mt-3 rounded-lg bg-slate-50 p-2 text-xs text-slate-600">{row.notes}</UiText>}</UiSection>)}</UiBox>
    </UiMain>;
}

function DateTimeInput({value,onChange}:{value:string;onChange:(value:string)=>void}){
    return <UiInput type="datetime-local" required value={value} onChange={event=>onChange(event.target.value)} className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm"/>;
}
