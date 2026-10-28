import { AdminDataTable } from "../data-table";
export default function Page(){return <AdminDataTable title="Admin audit log" description="Append-only record of internal control-plane changes." endpoint="/admin/audit-logs" columns={["created_at","actor_email","actor_role","action","tenant_name","object_type","object_id","reason","metadata"]}/>}
