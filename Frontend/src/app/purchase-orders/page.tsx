import { OperationalPage } from "@/components/operational-page";
import { ImportControls } from "@/components/import-controls";
import { ProcurementControls } from "@/components/procurement-controls";
export default function PurchaseOrdersPage(){return <><ImportControls kind="purchase-orders"/><ProcurementControls kind="po"/><OperationalPage title="Purchase orders" description="Purchase orders available for invoice matching." path="/purchase-orders"/></>}
