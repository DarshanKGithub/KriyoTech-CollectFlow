import { OperationalPage } from "@/components/operational-page";
import { ImportControls } from "@/components/import-controls";
import { ServiceAcceptance } from "@/components/service-acceptance";
import { ProcurementControls } from "@/components/procurement-controls";
export default function GRNsPage(){return <><ImportControls kind="grns"/><ProcurementControls kind="grn"/><OperationalPage title="Goods received notes" description="Receipt records linked to purchase order lines." path="/grns"/><ServiceAcceptance/></>}
