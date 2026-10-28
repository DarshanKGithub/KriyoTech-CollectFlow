import { AdminDataTable } from "../data-table";
export default function Page(){return <AdminDataTable title="Usage" description="Tenant usage snapshots and configured period limits." endpoint="/admin/usage" columns={["tenant_name","metric","period_start","period_end","used_count","limit_value","updated_at"]}/>}
