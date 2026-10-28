from datetime import date

import pytest
from rest_framework.test import APIClient

from accounts.models import Membership, User
from tenants.models import Tenant
from .models import DriverSalaryPayment, DriverSalaryRecord, FleetDriver, FleetTrip, FleetVehicle


@pytest.mark.django_db
def test_driver_trip_completion_to_salary_settlement_uses_separate_roles():
    tenant = Tenant.objects.create(name="Fleet workflow", workspace_key="fleet-workflow")
    driver_user = User.objects.create_user(username="driver@fleet.test", email="driver@fleet.test", password="example-pass")
    fleet_user = User.objects.create_user(username="ops@fleet.test", email="ops@fleet.test", password="example-pass")
    approver = User.objects.create_user(username="approver@fleet.test", email="approver@fleet.test", password="example-pass")
    finance = User.objects.create_user(username="finance@fleet.test", email="finance@fleet.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=driver_user, role="DRIVER")
    Membership.objects.create(tenant=tenant, user=fleet_user, role="FLEET")
    Membership.objects.create(tenant=tenant, user=approver, role="APPROVER")
    Membership.objects.create(tenant=tenant, user=finance, role="FINANCE")
    driver = FleetDriver.objects.create(tenant=tenant, name="Trip Driver", user=driver_user)
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="KA01AA1234", normalized_registration="KA01AA1234")
    trip = FleetTrip.objects.create(tenant=tenant, trip_number="TRIP-E2E-1", driver=driver, vehicle=vehicle, created_by=fleet_user)

    driver_client = APIClient(); driver_client.force_authenticate(user=driver_user)
    for action, payload in (("start", {"odometer_start": "1000"}), ("load", {}), ("complete", {"odometer_end": "1125", "delivery_signature_name": "Customer Receiver"}), ("submit", {})):
        response = driver_client.post(f"/api/v1/fleet/trips/{trip.id}/{action}", payload, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == FleetTrip.Status.SUBMITTED and trip.odometer_end == 1125

    approver_client = APIClient(); approver_client.force_authenticate(user=approver)
    approved = approver_client.post(f"/api/v1/fleet/trips/{trip.id}/approve", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert approved.status_code == 200, approved.data
    assert approved.data["status"] == FleetTrip.Status.APPROVED

    fleet_client = APIClient(); fleet_client.force_authenticate(user=fleet_user)
    created = fleet_client.post("/api/v1/fleet/driver-salaries", {"driver_id": str(driver.id), "period_start": date.today().replace(day=1).isoformat(), "salary_amount": "1250.00"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert created.status_code == 201, created.data
    salary_id = created.data["id"]
    submitted = fleet_client.post(f"/api/v1/fleet/driver-salaries/{salary_id}/submit", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert submitted.status_code == 200, submitted.data
    salary_approved = approver_client.post(f"/api/v1/fleet/driver-salaries/{salary_id}/approve", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert salary_approved.status_code == 200, salary_approved.data

    finance_client = APIClient(); finance_client.force_authenticate(user=finance)
    paid = finance_client.post(f"/api/v1/fleet/driver-salaries/{salary_id}/payments", {"amount": "1250.00", "payment_reference": "BANK-E2E-1"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert paid.status_code == 201, paid.data
    assert paid.data["status"] == DriverSalaryRecord.Status.PAID
    assert DriverSalaryPayment.objects.filter(tenant=tenant, salary_record_id=salary_id).count() == 1
