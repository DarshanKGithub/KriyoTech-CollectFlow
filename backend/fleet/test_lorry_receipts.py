from datetime import date

import pytest
from rest_framework.test import APIClient

from accounts.models import Membership, User
from audit.models import AuditLog
from tenants.models import Tenant
from .models import FleetDriver, FleetTrip, FleetVehicle, FleetCustomer, LorryReceipt, TransportOrder


@pytest.mark.django_db
def test_lorry_receipt_issue_assigns_tenant_scoped_numbers_and_links_trip():
    tenant = Tenant.objects.create(name="LR Workspace", workspace_key="lr-workspace")
    user = User.objects.create_user(username="fleet@lr.test", email="fleet@lr.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.FLEET)
    customer = FleetCustomer.objects.create(tenant=tenant, name="Northwind Foods")
    order = TransportOrder.objects.create(tenant=tenant, customer=customer, order_number="ORDER-100", origin="Pune", destination="Mumbai", cargo_description="Packaged foods", agreed_amount="18500.00")
    driver = FleetDriver.objects.create(tenant=tenant, name="Asha Driver")
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="MH12AB1234", normalized_registration="MH12AB1234")
    trip = FleetTrip.objects.create(tenant=tenant, trip_number="TRIP-100", transport_order=order, driver=driver, vehicle=vehicle)

    client = APIClient(); client.force_authenticate(user=user)
    client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    payload = {
        "order_id": str(order.id), "lr_date": date.today().isoformat(),
        "consignor_name": "Northwind Pune", "consignee_name": "Northwind Mumbai",
        "goods_description": "Packaged foods", "package_count": 20, "weight_kg": "740.500",
        "freight_amount": "18500.00", "payment_type": "TO_BE_BILLED",
    }
    first = client.post("/api/v1/fleet/lorry-receipts", payload, format="json")
    second = client.post("/api/v1/fleet/lorry-receipts", payload, format="json")

    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    assert first.data["lr_number"].startswith(f"LR-{date.today().year}-")
    assert second.data["lr_number"] != first.data["lr_number"]
    assert first.data["trip_number"] == trip.trip_number
    assert first.data["vehicle"] == vehicle.registration_number
    assert LorryReceipt.objects.filter(tenant=tenant).count() == 2
    assert AuditLog.objects.filter(tenant=tenant, action="LORRY_RECEIPT_ISSUED").count() == 2


@pytest.mark.django_db
def test_lorry_receipt_rejects_cross_tenant_order_and_driver_cannot_issue():
    tenant = Tenant.objects.create(name="LR Workspace A", workspace_key="lr-workspace-a")
    other = Tenant.objects.create(name="LR Workspace B", workspace_key="lr-workspace-b")
    owner = User.objects.create_user(username="owner@lr.test", email="owner@lr.test", password="example-pass")
    driver = User.objects.create_user(username="driver@lr.test", email="driver@lr.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=owner, role=Membership.Role.OWNER)
    Membership.objects.create(tenant=tenant, user=driver, role=Membership.Role.DRIVER)
    customer = FleetCustomer.objects.create(tenant=other, name="Other tenant")
    order = TransportOrder.objects.create(tenant=other, customer=customer, order_number="OTHER-1", origin="A", destination="B")
    payload = {"order_id": str(order.id), "consignor_name": "A", "consignee_name": "B", "goods_description": "Goods", "freight_amount": "100.00"}

    owner_client = APIClient(); owner_client.force_authenticate(user=owner)
    cross_tenant = owner_client.post("/api/v1/fleet/lorry-receipts", payload, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert cross_tenant.status_code == 400
    assert not LorryReceipt.objects.exists()

    driver_client = APIClient(); driver_client.force_authenticate(user=driver)
    denied = driver_client.post("/api/v1/fleet/lorry-receipts", payload, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert denied.status_code == 403


@pytest.mark.django_db
def test_lorry_receipt_cancellation_requires_reason_and_is_audited():
    tenant = Tenant.objects.create(name="LR Workspace", workspace_key="lr-cancel")
    user = User.objects.create_user(username="owner@lr-cancel.test", email="owner@lr-cancel.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
    customer = FleetCustomer.objects.create(tenant=tenant, name="Customer")
    order = TransportOrder.objects.create(tenant=tenant, customer=customer, order_number="ORDER-C", origin="A", destination="B")
    client = APIClient(); client.force_authenticate(user=user)
    issued = client.post("/api/v1/fleet/lorry-receipts", {"order_id": str(order.id), "consignor_name": "A", "consignee_name": "B", "goods_description": "Parts", "freight_amount": "0", "payment_type": "PAID"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert issued.status_code == 201, issued.data

    url = f"/api/v1/fleet/lorry-receipts/{issued.data['id']}/cancel"
    invalid = client.post(url, {"reason": "no"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert invalid.status_code == 400
    cancelled = client.post(url, {"reason": "Order was entered twice"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["status"] == LorryReceipt.Status.CANCELLED
    assert AuditLog.objects.filter(tenant=tenant, action="LORRY_RECEIPT_CANCELLED").count() == 1
