import hashlib
import json
import secrets
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import Membership,User
from tenants.models import Tenant
from audit.models import AuditLog
from .models import (FleetCustomer,FleetDriver,FleetVehicle,FleetTrip,TransportOrder,
    FleetExceptionCase,FleetDock,DockAppointment,ReturnLoadOffer,ShipmentAccessLink,ShipmentNotice,
    FleetTripLocation,FleetMaintenanceRecord,FleetStopEpisode,FleetRouteSnapshot,FleetRouteProviderAttempt)


@pytest.fixture
def workspace(db):
    tenant=Tenant.objects.create(name="Operations",workspace_key="operations-test")
    user=User.objects.create_user(username="ops-test",email="ops@example.test",password="test-pass")
    Membership.objects.create(tenant=tenant,user=user,role="OWNER")
    client=APIClient();client.force_authenticate(user=user);client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    customer=FleetCustomer.objects.create(tenant=tenant,name="Customer",dock_free_minutes=60,detention_rate_per_hour=100)
    vehicle=FleetVehicle.objects.create(tenant=tenant,registration_number="TEST123",normalized_registration="TEST123",capacity=10)
    driver=FleetDriver.objects.create(tenant=tenant,name="Driver")
    order=TransportOrder.objects.create(tenant=tenant,customer=customer,order_number="O-1",origin="Hub A",destination="Hub B",agreed_amount=1000,status="DELIVERED")
    trip=FleetTrip.objects.create(tenant=tenant,trip_number="T-1",vehicle=vehicle,driver=driver,transport_order=order,status="COMPLETED",delivery_at=timezone.now(),delivery_signature_name="Receiver")
    return tenant,user,client,customer,vehicle,driver,order,trip


def test_exception_review_rejects_foreign_assignment_stale_decision_and_keeps_history(workspace):
    tenant,user,client,*_=workspace
    case=FleetExceptionCase.objects.create(tenant=tenant,source_key="fuel:test",category="FUEL",evidence={"message":"Review fuel"})
    path=f"/api/v1/fleet/exceptions/{case.id}"
    foreign=User.objects.create_user(username="foreign",email="foreign@example.test")
    response=client.patch(path,{"action":"assign","note":"Assign review","owner_id":str(foreign.id),"due_at":timezone.now().isoformat(),"expected_updated_at":case.updated_at.isoformat()},format="json")
    assert response.status_code==400
    version=case.updated_at.isoformat()
    response=client.patch(path,{"action":"confirm","note":"Receipt verified","expected_updated_at":version},format="json")
    assert response.status_code==200,response.data
    stale=client.patch(path,{"action":"dismiss","note":"Stale decision","expected_updated_at":version},format="json")
    assert stale.status_code==409
    assert client.get(path).data["history"][0]["details"]["note"]=="Receipt verified"
    other=Tenant.objects.create(name="Other",workspace_key="other-test")
    foreign_case=FleetExceptionCase.objects.create(tenant=other,source_key="foreign",category="FUEL")
    assert client.get(f"/api/v1/fleet/exceptions/{foreign_case.id}").status_code==404
    export=client.get("/api/v1/fleet/exceptions?export=csv")
    assert export.status_code==200
    assert "foreign" not in export.content.decode()


def test_trip_edit_cannot_reassign_a_resource_used_by_an_active_trip(workspace):
    tenant, user, client, customer, vehicle, driver, order, trip = workspace
    other_vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="TEST456", normalized_registration="TEST456", capacity=10)
    other_driver = FleetDriver.objects.create(tenant=tenant, name="Second Driver")
    active = FleetTrip.objects.create(tenant=tenant, trip_number="T-2", vehicle=other_vehicle, driver=other_driver, status=FleetTrip.Status.DRAFT)
    response = client.patch(f"/api/v1/fleet/trips/{trip.id}", {
        "vehicle_id": str(other_vehicle.id), "driver_id": str(other_driver.id),
    }, format="json")
    assert response.status_code == 409, response.data
    trip.refresh_from_db()
    assert trip.vehicle_id == vehicle.id and trip.driver_id == driver.id


def test_portal_is_scoped_revocable_and_hides_driver_and_gps(workspace):
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    created=client.post("/api/v1/fleet/shipment-links",{"trip_id":str(trip.id)},format="json")
    assert created.status_code==201,created.data
    token=created.data["url"].rsplit("/",1)[-1]
    public=APIClient();path=f"/api/v1/fleet/public/shipment/{token}"
    result=public.get(path)
    assert result.status_code==200
    assert not {"driver","latitude","longitude","vehicle"}&set(result.data)
    assert result["Cache-Control"]=="no-store"
    issue=public.post(path,{"description":"Delivery package damaged"},format="json")
    assert issue.status_code==201
    assert FleetExceptionCase.objects.get(id=issue.data["reference"]).tenant_id==tenant.id
    case=FleetExceptionCase.objects.get(id=issue.data["reference"])
    resolved=client.patch(f"/api/v1/fleet/exceptions/{case.id}",{"action":"resolve","note":"Private operator review","public_resolution":"Replacement delivery arranged.","expected_updated_at":case.updated_at.isoformat()},format="json")
    assert resolved.status_code==200,resolved.data
    visible=public.get(path).data["issues"][0]
    assert visible["resolution"]=="Replacement delivery arranged." and "review_note" not in visible
    assert public.get(path+"/invoice").status_code==404
    client.delete("/api/v1/fleet/shipment-links",{"id":created.data["id"]},format="json")
    assert public.get(path).status_code==404
    assert client.post("/api/v1/fleet/shipment-links",{"trip_id":"bad-id"},format="json").status_code==400


def test_detention_terms_are_snapshotted_and_billing_is_idempotent(workspace):
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    dock=FleetDock.objects.create(tenant=tenant,site_name="Hub",code="1",name="Bay")
    row=DockAppointment.objects.create(tenant=tenant,dock=dock,order=order,starts_at=timezone.now(),ends_at=timezone.now()+timedelta(hours=1),idempotency_key=secrets.token_hex(16))
    url=f"/api/v1/fleet/dock-appointments/{row.id}"
    assert client.post(url+"/arrive",{},format="json").status_code==200
    row.refresh_from_db();assert row.free_minutes_snapshot==60 and row.rate_snapshot==100
    customer.detention_rate_per_hour=500;customer.save()
    row.checked_in_at=timezone.now()-timedelta(hours=3);row.save()
    assert client.post(url+"/start",{},format="json").status_code==200
    assert client.post(f"/api/v1/fleet/detention/{row.id}/finish-loading",{},format="json").status_code==200
    assert client.post(url+"/complete",{"delay_reason":"Loading bay unavailable"},format="json").status_code==200
    row.refresh_from_db();assert row.loading_started_at and row.loading_finished_at
    first=client.post(f"/api/v1/fleet/detention/{row.id}/prepare-billing",{"reason":"Customer detention terms"},format="json")
    assert first.status_code==200,first.data
    second=client.post(f"/api/v1/fleet/detention/{row.id}/prepare-billing",{},format="json")
    assert second.data["detention_revenue_id"]==first.data["detention_revenue_id"]
    row.refresh_from_db();assert row.detention_revenue.amount==Decimal("200")
    blocked=client.post("/api/v1/fleet/customer-invoices",{"trip_id":str(trip.id)},format="json")
    assert blocked.status_code==409
    row.detention_revenue.status="APPROVED";row.detention_revenue.save()
    invoiced=client.post("/api/v1/fleet/customer-invoices",{"trip_id":str(trip.id)},format="json")
    assert invoiced.status_code==201,invoiced.data
    assert Decimal(invoiced.data["amount"])==1200


def test_return_load_booking_blocks_double_assignment_and_preserves_cancelled_history(workspace):
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    target=TransportOrder.objects.create(tenant=tenant,customer=customer,order_number="O-2",origin="Hub B",destination="Hub C",agreed_amount=1500,load_quantity=5)
    path=f"/api/v1/fleet/return-loads/{trip.id}/{target.id}"
    offered=client.post(path+"/offer",{"proposed_amount":"1600"},format="json");assert offered.status_code==201
    booking=client.post(path+"/confirm",{"customer_accepted":True,"suitability_confirmed":True},format="json")
    assert booking.status_code==201,booking.data
    duplicate=client.post(path+"/confirm",{"customer_accepted":True,"suitability_confirmed":True},format="json")
    assert duplicate.status_code==409
    direct=client.post("/api/v1/fleet/trips",{"trip_number":"DOUBLE","vehicle_id":str(vehicle.id),"driver_id":str(driver.id)},format="json")
    assert direct.status_code==409,direct.data
    cancelled=client.post(f"/api/v1/fleet/booking-history/{offered.data['id']}/cancel",{"reason":"Customer rescheduled"},format="json")
    assert cancelled.status_code==200,cancelled.data
    target.refresh_from_db();assert target.status=="OPEN"
    assert FleetTrip.objects.get(id=booking.data["trip_id"]).status=="CANCELLED"
    assert client.post(path+"/offer",{"proposed_amount":"1700"},format="json").status_code==201
    assert ReturnLoadOffer.objects.filter(order=target).count()==2


def test_customer_notice_deduplication_and_unknown_send_is_not_retried(workspace,monkeypatch):
    from .customer_notifications import queue_customer_notices,process_notices
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    for _ in range(2):
        ShipmentAccessLink.objects.create(tenant=tenant,trip=trip,token_hash=hashlib.sha256(secrets.token_bytes(16)).hexdigest(),expires_at=timezone.now()+timedelta(days=1),notify_email="customer@example.test",consent_note="Customer form consent")
    assert queue_customer_notices()==1
    monkeypatch.setattr("fleet.customer_notifications.send_notice",lambda notice:("UNKNOWN","Provider timeout",""))
    assert process_notices()==1
    assert process_notices()==0
    notice=ShipmentNotice.objects.get();assert notice.status=="UNKNOWN"
    denied=client.post("/api/v1/fleet/customer-notifications",{"notice_id":str(notice.id),"reason":"Check"},format="json")
    assert denied.status_code==409
    assert AuditLog.objects.filter(object_type="ShipmentNotice",action="CUSTOMER_NOTICE_ATTEMPT").count()==1
    from .customer_notifications import recover_stale_notices
    ShipmentNotice.objects.filter(id=notice.id).update(status="PROCESSING",updated_at=timezone.now()-timedelta(minutes=6))
    assert recover_stale_notices()==1
    notice.refresh_from_db();assert notice.status=="UNKNOWN"
    assert recover_stale_notices()==0


def test_route_missing_configuration_and_stubbed_google_response(workspace,monkeypatch):
    from .routing import refresh_route
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    monkeypatch.delenv("GOOGLE_MAPS_ROUTES_API_KEY",raising=False)
    assert refresh_route(trip)["status"]=="NOT_CONFIGURED"
    tenant.settings={"fleet_controls":{"route_eta_enabled":True}};tenant.save()
    trip.tenant=tenant;trip.status="IN_PROGRESS";trip.save()
    FleetTripLocation.objects.create(tenant=tenant,trip=trip,reported_by=user,latitude=19.1,longitude=72.9,accuracy_m=10,captured_at=timezone.now(),client_event_id=secrets.token_hex(16))
    monkeypatch.setenv("GOOGLE_MAPS_ROUTES_API_KEY","test-only-key")
    class FakeResponse:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):return json.dumps({"routes":[{"duration":"600s","distanceMeters":10000,"polyline":{"encodedPolyline":"???_ibE"}}]}).encode()
    with patch("fleet.routing.urlopen",return_value=FakeResponse()):
        result=refresh_route(trip)
    assert result["status"]=="UPDATED" and result["route_version"]==1,result
    assert FleetRouteSnapshot.objects.filter(tenant=tenant,trip=trip).count()==1
    trip.refresh_from_db();assert trip.eta_source=="GOOGLE_TRAFFIC" and trip.route_distance_m==10000
    history=client.get(f"/api/v1/fleet/trips/{trip.id}/eta-history")
    assert history.status_code==200 and history.data["eta_source"]=="GOOGLE_TRAFFIC"
    assert history.data["history"][0]["status"]=="UPDATED"


def test_route_provider_budget_and_failure_circuit(workspace,monkeypatch):
    from urllib.error import URLError
    from .routing import refresh_route
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    tenant.settings={"fleet_controls":{"route_eta_enabled":True}};tenant.save()
    trip.tenant=tenant;trip.status="IN_PROGRESS";trip.save()
    FleetTripLocation.objects.create(tenant=tenant,trip=trip,reported_by=user,latitude=19.1,longitude=72.9,
        accuracy_m=10,captured_at=timezone.now(),client_event_id=secrets.token_hex(16))
    monkeypatch.setenv("GOOGLE_MAPS_ROUTES_API_KEY","test-only-key")
    monkeypatch.setenv("GOOGLE_ROUTES_DAILY_REQUEST_BUDGET","10")
    with patch("fleet.routing.urlopen",side_effect=URLError("quota")) as provider:
        for _ in range(3):
            FleetTrip.objects.filter(id=trip.id).update(route_attempted_at=timezone.now()-timedelta(minutes=2))
            trip.refresh_from_db()
            assert refresh_route(trip)["status"]=="PROVIDER_ERROR"
        FleetTrip.objects.filter(id=trip.id).update(route_attempted_at=timezone.now()-timedelta(minutes=2))
        trip.refresh_from_db()
        blocked=refresh_route(trip)
    assert blocked["status"]=="CIRCUIT_OPEN" and blocked["retry_after_seconds"]>0
    assert provider.call_count==3
    attempts=list(FleetRouteProviderAttempt.objects.filter(tenant=tenant).order_by("requested_at"))
    assert len(attempts)==3 and all(row.status=="FAILED" for row in attempts)


def test_route_provider_budget_stops_additional_calls(workspace,monkeypatch):
    from .routing import refresh_route
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    tenant.settings={"fleet_controls":{"route_eta_enabled":True}};tenant.save()
    trip.tenant=tenant;trip.status="IN_PROGRESS";trip.save()
    FleetTripLocation.objects.create(tenant=tenant,trip=trip,reported_by=user,latitude=19.1,longitude=72.9,
        accuracy_m=10,captured_at=timezone.now(),client_event_id=secrets.token_hex(16))
    monkeypatch.setenv("GOOGLE_MAPS_ROUTES_API_KEY","test-only-key")
    monkeypatch.setenv("GOOGLE_ROUTES_DAILY_REQUEST_BUDGET","1")
    class FakeResponse:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):return json.dumps({"routes":[{"duration":"600s","distanceMeters":10000}]}).encode()
    with patch("fleet.routing.urlopen",return_value=FakeResponse()) as provider:
        assert refresh_route(trip)["status"]=="UPDATED"
        FleetTrip.objects.filter(id=trip.id).update(route_attempted_at=timezone.now()-timedelta(minutes=2))
        trip.refresh_from_db()
        result=refresh_route(trip)
    assert result["status"]=="BUDGET_EXCEEDED" and result["retry_after_seconds"]>0
    assert provider.call_count==1
    assert FleetRouteProviderAttempt.objects.filter(tenant=tenant).count()==1


def test_open_breakdown_blocks_assignment_and_return_to_service_unblocks(workspace):
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    repair=FleetMaintenanceRecord.objects.create(tenant=tenant,vehicle=vehicle,category="REPAIR",description="Brake repair",service_date=timezone.localdate(),failure_code="BRAKES",breakdown_at=timezone.now()-timedelta(hours=2))
    payload={"trip_number":"NEW","vehicle_id":str(vehicle.id),"driver_id":str(driver.id)}
    assert client.post("/api/v1/fleet/trips",payload,format="json").status_code==409
    assert client.post(f"/api/v1/fleet/maintenance/{repair.id}/return-to-service",{"reason":"Inspection passed"},format="json").status_code==200
    assert client.post("/api/v1/fleet/trips",payload,format="json").status_code==201


def test_vehicle_type_and_capacity_conversion(workspace):
    from .compatibility import load_compatibility
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    vehicle.capacity=Decimal("10");vehicle.capacity_unit="TONNE";vehicle.vehicle_type="TRAILER"
    order.load_quantity=Decimal("9000");order.load_unit="kg";order.required_vehicle_type="TRAILER"
    assert load_compatibility(vehicle,order)[0] is True
    order.load_quantity=Decimal("11000")
    assert load_compatibility(vehicle,order)[0] is False
    order.load_quantity=Decimal("9000");order.required_vehicle_type="REFRIGERATED"
    assert load_compatibility(vehicle,order)[0] is False


def test_whatsapp_webhook_requires_signature_and_does_not_regress_delivery(workspace,monkeypatch):
    import hmac
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    link=ShipmentAccessLink.objects.create(tenant=tenant,trip=trip,token_hash=hashlib.sha256(b"webhook-test").hexdigest(),expires_at=timezone.now()+timedelta(days=1))
    notice=ShipmentNotice.objects.create(link=link,event_key="status:test",delivery_key=hashlib.sha256(b"test-notice").hexdigest(),channel="WHATSAPP",status="ACCEPTED",provider_reference="test-provider-id")
    monkeypatch.setenv("WHATSAPP_APP_SECRET","test-secret")
    public=APIClient();path="/api/v1/fleet/public/whatsapp-status"
    payload={"entry":[{"changes":[{"value":{"statuses":[{"id":"test-provider-id","status":"delivered"}]}}]}]}
    body=json.dumps(payload).encode()
    assert public.post(path,body,content_type="application/json").status_code==403
    signature="sha256="+hmac.new(b"test-secret",body,hashlib.sha256).hexdigest()
    assert public.post(path,body,content_type="application/json",HTTP_X_HUB_SIGNATURE_256=signature).status_code==200
    notice.refresh_from_db();assert notice.status=="DELIVERED"
    payload["entry"][0]["changes"][0]["value"]["statuses"][0]["status"]="sent"
    body=json.dumps(payload).encode();signature="sha256="+hmac.new(b"test-secret",body,hashlib.sha256).hexdigest()
    public.post(path,body,content_type="application/json",HTTP_X_HUB_SIGNATURE_256=signature)
    notice.refresh_from_db();assert notice.status=="DELIVERED"


def test_assigned_reviewer_can_review_and_changed_evidence_reopens_closed_case(workspace,monkeypatch):
    from types import SimpleNamespace
    from rest_framework.response import Response
    from .exceptions import sync_cases
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    reviewer=User.objects.create_user(username="reviewer",email="reviewer@example.test")
    membership=Membership.objects.create(tenant=tenant,user=reviewer,role="APPROVER")
    signal={"id":"fuel:sample","kind":"FUEL_COST_PER_KM_ANOMALY","message":"Cost per km 50","amount":"50"}
    monkeypatch.setattr("fleet.views.FleetAlerts.get",lambda self,req:Response({"alerts":[signal]}))
    monkeypatch.setattr("fleet.views.FleetRevenueLeakage.get",lambda self,req:Response({"items":[]}))
    request=SimpleNamespace(tenant=tenant,membership=membership,user=reviewer)
    sync_cases(request)
    case=FleetExceptionCase.objects.get(source_key="alert:fuel:sample")
    client.force_authenticate(user=reviewer)
    response=client.patch(f"/api/v1/fleet/exceptions/{case.id}",{"action":"dismiss","note":"Receipt checked","expected_updated_at":case.updated_at.isoformat()},format="json")
    assert response.status_code==200,response.data
    signal["amount"]="100";signal["message"]="Cost per km 100"
    sync_cases(request);case.refresh_from_db()
    assert case.status=="OPEN"
    assert AuditLog.objects.filter(object_type="FleetExceptionCase",object_id=str(case.id),action="FLEET_EXCEPTION_SOURCE_CHANGED").exists()


def test_contextual_fuel_signal_requires_matching_vehicle_lane_and_load_history(workspace):
    from .models import TripExpenseLine
    from .anomalies import contextual_fuel_alerts
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    for index in range(7):
        o=TransportOrder.objects.create(tenant=tenant,customer=customer,order_number=f"FUEL-{index}",origin="A",destination="B",load_quantity=5,load_unit="TONNE",status="DELIVERED")
        t=FleetTrip.objects.create(tenant=tenant,trip_number=f"FUEL-{index}",vehicle=vehicle,driver=driver,transport_order=o,origin="A",destination="B",
            status="APPROVED",delivery_at=timezone.now()-timedelta(days=7-index),odometer_start=1000,odometer_end=1100)
        TripExpenseLine.objects.create(tenant=tenant,trip=t,category="FUEL",description="Fuel",amount=1000,quantity_litres=30 if index==6 else 10,status="APPROVED")
    signals=contextual_fuel_alerts(tenant)
    assert len(signals)==1
    assert signals[0]["trip_number"]=="FUEL-6" and signals[0]["reference_sample_count"]==6


def test_revenue_review_distinguishes_partial_collection_from_confirmed_bank_reconciliation(workspace):
    from .models import TransportInvoice,TransportCollection
    from phase3.models import BankStatement,BankTransaction
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    invoice=TransportInvoice.objects.create(tenant=tenant,customer=customer,order=order,trip=trip,invoice_number="CUSTOMER-1",amount=1000,status="PARTIALLY_PAID")
    collection=TransportCollection.objects.create(tenant=tenant,invoice=invoice,amount=300,method="BANK",reference="BANK-REF")
    statement=BankStatement.objects.create(tenant=tenant,filename="bank.csv",content_hash=hashlib.sha256(b"bank-test").hexdigest())
    bank=BankTransaction.objects.create(tenant=tenant,statement=statement,transaction_date=timezone.localdate(),description="Collection",amount=300,fingerprint=hashlib.sha256(b"row-test").hexdigest(),transport_collection=collection,status="MATCHED")
    first=client.get("/api/v1/fleet/revenue-leakage");assert first.status_code==200
    kinds={row["issue"] for row in first.data["items"]}
    assert "PARTIAL_CUSTOMER_COLLECTION" in kinds and "COLLECTION_NOT_BANK_RECONCILED" in kinds
    bank.status="RECONCILED";bank.save()
    second=client.get("/api/v1/fleet/revenue-leakage")
    assert "COLLECTION_NOT_BANK_RECONCILED" not in {row["issue"] for row in second.data["items"]}


def test_real_exception_evidence_collection_is_idempotent_and_assigns_an_owner(workspace):
    tenant,user,client,*_=workspace
    first=client.post("/api/v1/fleet/exceptions",{},format="json")
    assert first.status_code==200 and first.data["created"]>0,first.data
    second=client.post("/api/v1/fleet/exceptions",{},format="json")
    assert second.status_code==200 and second.data["created"]==0,second.data
    assert not FleetExceptionCase.objects.filter(tenant=tenant,owner__isnull=True).exists()


def test_stop_detection_persists_continuous_accurate_samples(workspace):
    from types import SimpleNamespace
    from .routing import record_motion,distance_to_path
    tenant,user,client,customer,vehicle,driver,order,trip=workspace
    start=timezone.now()-timedelta(minutes=16)
    for minute in range(17):
        record_motion(trip,SimpleNamespace(latitude=Decimal("19.1"),longitude=Decimal("72.9"),accuracy_m=Decimal("10"),captured_at=start+timedelta(minutes=minute)))
    assert FleetExceptionCase.objects.filter(tenant=tenant,category="PROLONGED_STOP").count()==1
    episode=FleetStopEpisode.objects.get(tenant=tenant,trip=trip,ended_at__isnull=True)
    assert episode.sample_count==17 and episode.exception_case.category=="PROLONGED_STOP"
    assert distance_to_path((0,0.5),[(0,0),(0,1)])<1
    assert distance_to_path((0.03,0.5),[(0,0),(0,1)])>2000
