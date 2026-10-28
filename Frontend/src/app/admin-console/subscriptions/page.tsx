import { AdminDataTable } from "../data-table";
export default function Page(){return <AdminDataTable title="Subscriptions" description="Trial, paid, overdue, and suspended account status." endpoint="/admin/subscriptions" columns={["tenant_name","plan_name","status","billing_cycle","starts_at","trial_ends_at","next_billing_at","auto_renew"]}/>}
