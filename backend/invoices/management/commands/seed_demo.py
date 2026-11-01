"""Create a repeatable, synthetic KriyoPay demo workspace for local/client demos."""

import uuid
import hashlib
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Membership, User
from admin_console.models import Feature, TenantFeatureOverride
from exceptions_app.models import InvoiceException
from fleet.models import (
    DockAppointment,
    DriverPayPolicy,
    DriverSalaryPayment,
    DriverSalaryRecord,
    FleetCustomer,
    FleetDock,
    FleetDriver,
    FleetExceptionCase,
    FleetFollowUp,
    FleetGeofence,
    FleetGeofenceEvent,
    FleetGeofenceVersion,
    FleetGpsDevice,
    FleetMaintenanceRecord,
    ShipmentAccessLink,
    ShipmentNotice,
    FleetTrip,
    FleetTripLocation,
    FleetTripLocationSample,
    FleetVehicle,
    ReturnLoadOffer,
    TransportCollection,
    TransportInvoice,
    TransportOrder,
    TripExpenseLine,
    TripRevenueLine,
)
from procurement.models import GRN, GRNLine, PurchaseOrder, PurchaseOrderLine
from tenants.models import Tenant, default_branch_for
from vendors.models import Vendor
from invoices.models import Invoice, InvoiceLine


DEMO_OWNER_EMAIL = "owner@kriyopay.demo"
DEMO_OWNER_PASSWORD = "KriyoDemo!2026"
DEMO_DRIVER_EMAIL = "driver@kriyopay.demo"
DEMO_DRIVER_PASSWORD = "DriveDemo!2026"
DEMO_WORKSPACE_KEY = "kriyo-demo"
DEMO_COMPANY_NAME = "KriyoPay Demo Logistics"
DEMO_PORTAL_NOTE = "SYNTHETIC DEMO ONLY · no real customer consent or delivery"


def demo_user(email, password, *, first_name, last_name, tenant, role):
    user = User.objects.filter(email=email).first()
    if user and not user.memberships.filter(tenant=tenant).exists():
        raise CommandError(f"Reserved demo account {email} already belongs to another workspace; refusing to change it.")
    if not user:
        user = User.objects.create_user(email=email, username=email, password=password,
            first_name=first_name, last_name=last_name)
    else:
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        user.set_password(password)
        user.save(update_fields=["first_name", "last_name", "is_active", "password"])
    membership, _ = Membership.objects.get_or_create(tenant=tenant, user=user, defaults={"role": role})
    if membership.role != role or not membership.is_active:
        membership.role = role
        membership.is_active = True
        membership.save(update_fields=["role", "is_active"])
    return user


class Command(BaseCommand):
    help = "Create or refresh a synthetic KriyoPay company for product demonstrations"

    @transaction.atomic
    def handle(self, *args, **options):
        tenant, _ = Tenant.objects.get_or_create(
            workspace_key=DEMO_WORKSPACE_KEY,
            defaults={"name": DEMO_COMPANY_NAME, "settings": {"demo_workspace": True}},
        )
        tenant.name = DEMO_COMPANY_NAME
        tenant.is_deleted = False
        tenant.deleted_at = None
        tenant.settings = {**(tenant.settings or {}), "demo_workspace": True, "synthetic_data": True}
        tenant.save(update_fields=["name", "is_deleted", "deleted_at", "settings"])
        # Demo workspaces should expose the full UI catalog, including Fleet & Trips,
        # without changing entitlements for any other tenant.
        Feature.objects.get_or_create(
            key="fleet_management",
            defaults={"name": "Fleet & Trips", "description": "Fleet operations and transport management", "is_active": True},
        )
        for feature in Feature.objects.filter(is_active=True):
            TenantFeatureOverride.objects.update_or_create(
                tenant=tenant,
                feature=feature,
                defaults={"enabled": True, "reason": "Enabled for the synthetic KriyoPay client demo", "expires_at": None},
            )
        branch = default_branch_for(tenant.id)
        branch.name = "Bengaluru Operations"
        branch.save(update_fields=["name"])

        owner = demo_user(DEMO_OWNER_EMAIL, DEMO_OWNER_PASSWORD, first_name="KriyoPay", last_name="Demo Owner",
            tenant=tenant, role=Membership.Role.OWNER)
        driver_login = demo_user(DEMO_DRIVER_EMAIL, DEMO_DRIVER_PASSWORD, first_name="Arjun", last_name="Demo Driver",
            tenant=tenant, role=Membership.Role.DRIVER)

        self.seed_payables(tenant, owner)
        fleet_counts = self.seed_fleet(tenant, owner, driver_login)
        self.stdout.write(self.style.SUCCESS(
            f"Demo company ready: {tenant.name} [{tenant.workspace_key}] · branch {branch.name}\n"
            f"Owner login: {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}\n"
            f"Driver login: {DEMO_DRIVER_EMAIL} / {DEMO_DRIVER_PASSWORD}\n"
            f"Fleet: {fleet_counts['vehicles']} vehicles, {fleet_counts['drivers']} drivers, "
            f"{fleet_counts['orders']} orders, {fleet_counts['trips']} trips, "
            f"{fleet_counts['invoices']} transport invoices, {fleet_counts['locations']} live locations."
        ))
        if fleet_counts.get("portal_url"):
            self.stdout.write(f"Customer portal demo link: {fleet_counts['portal_url']}")
        self.stdout.write(self.style.WARNING("Synthetic demo data only. Do not use these credentials in production."))

    def seed_payables(self, tenant, user):
        vendor_names = ["Aarav Industrial Supplies", "Shree Ganesh Metals", "Precision Parts Co.",
            "Mehta Packaging Works", "National Bearings Ltd."]
        vendors = []
        for i, name in enumerate(vendor_names, 1):
            vendor, _ = Vendor.objects.get_or_create(tenant=tenant, external_code=f"V{i:02}", defaults={
                "name": name, "gstin": f"27ABCDE1234F{i}Z1", "approved": i != 5,
            })
            vendors.append(vendor)
        orders = []
        today = timezone.localdate()
        for i in range(10):
            vendor = vendors[i % len(vendors)]
            po, _ = PurchaseOrder.objects.get_or_create(tenant=tenant, number=f"PO-DEMO-{i+1:03}", defaults={
                "vendor": vendor, "order_date": today - timedelta(days=25-i),
            })
            line, _ = PurchaseOrderLine.objects.get_or_create(tenant=tenant, purchase_order=po, line_no=1, defaults={
                "item_code": f"ITEM-{i+1:03}", "description": f"Industrial component {i+1}",
                "quantity": Decimal("100"), "uom": "EA", "rate": Decimal("1000.00"),
                "taxable_value": Decimal("100000.00"), "gst_rate": Decimal("18"),
            })
            grn, _ = GRN.objects.get_or_create(tenant=tenant, number=f"GRN-DEMO-{i+1:03}", defaults={
                "vendor": vendor, "purchase_order": po, "received_at": today - timedelta(days=14-i),
            })
            GRNLine.objects.get_or_create(tenant=tenant, grn=grn, purchase_order_line=line, defaults={
                "item_code": line.item_code, "description": line.description,
                "quantity_received": Decimal("35") if i == 8 else Decimal("100"), "uom": "EA",
            })
            orders.append((po, line))
        statuses = [Invoice.Status.MATCHED, Invoice.Status.EXCEPTION, Invoice.Status.REVIEW_REQUIRED,
            Invoice.Status.APPROVAL_PENDING, Invoice.Status.APPROVED]
        for i in range(20):
            po, po_line = orders[i % 10]
            number = "INV-DUP-001" if i in (0, 19) else f"INV-DEMO-{i+1:03}"
            invoice, created = Invoice.objects.get_or_create(tenant=tenant, invoice_number=number, vendor=po.vendor, defaults={
                "po_number": po.number, "invoice_date": today - timedelta(days=i), "status": statuses[i % len(statuses)],
                "taxable_total": Decimal("100000.00"), "gst_total": Decimal("18000.00"),
                "invoice_total": Decimal("118000.00"), "uploaded_by": user,
            })
            if created:
                InvoiceLine.objects.create(tenant=tenant, invoice=invoice, line_no=1, item_code=po_line.item_code,
                    description=po_line.description, quantity=Decimal("50") if i == 8 else Decimal("100"),
                    uom="EA", rate=Decimal("1124.00") if i == 6 else Decimal("1000.00"),
                    taxable_value=Decimal("100000.00"), gst_rate=Decimal("18"), gst_amount=Decimal("18000.00"))
            if i in {1, 6, 8, 11, 14, 17, 19}:
                code = "RATE_VARIANCE" if i == 6 else "MISSING_GRN" if i == 8 else "DUPLICATE_INVOICE" if i == 19 else ["TAX_MISMATCH", "QTY_OVER_INVOICE", "VENDOR_NOT_APPROVED", "MANUAL_REVIEW"][([1, 11, 14, 17].index(i))]
                InvoiceException.objects.get_or_create(tenant=tenant, invoice=invoice, code=code, defaults={"details": {"seeded": True}})

    def seed_fleet(self, tenant, owner, driver_login):
        now = timezone.now()
        today = timezone.localdate()
        vehicles = []
        vehicle_data = [
            ("KA 03 AB 1201", "Tata 407", "LCV", "3.5", "TONNE", "6.2"),
            ("KA 03 AB 1202", "Ashok Leyland Partner", "LCV", "4.0", "TONNE", "5.8"),
            ("KA 03 AB 1203", "BharatBenz 1617R", "RIGID", "9.0", "TONNE", "4.6"),
            ("KA 03 AB 1204", "Eicher Pro 2049", "RIGID", "7.5", "TONNE", "5.2"),
            ("KA 03 AB 1205", "Tata Ace Gold", "LCV", "1.0", "TONNE", "12.0"),
            ("KA 03 AB 1206", "Eicher Pro 3015", "RIGID", "12.0", "TONNE", "4.2"),
            ("KA 03 AB 1207", "Mahindra Bolero Pik-up", "LCV", "1.5", "TONNE", "10.0"),
            ("KA 03 AB 1208", "Tata Signa 3525", "TRAILER", "25.0", "TONNE", "3.4"),
        ]
        for registration, model, kind, capacity, unit, efficiency in vehicle_data:
            normalized = "".join(ch for ch in registration.upper() if ch.isalnum())
            vehicle, _ = FleetVehicle.objects.get_or_create(tenant=tenant, normalized_registration=normalized, defaults={
                "registration_number": registration, "make_model": model, "vehicle_type": kind,
                "capacity": Decimal(capacity), "capacity_unit": unit, "expected_km_per_litre": Decimal(efficiency),
                "ownership_type": "OWNED", "status": FleetVehicle.Status.ACTIVE,
            })
            vehicles.append(vehicle)

        driver_data = [
            ("Arjun Rao", "+91 90000 10001", "DRV-DEMO-001", driver_login),
            ("Meera Nair", "+91 90000 10002", "DRV-DEMO-002", None),
            ("Ravi Kumar", "+91 90000 10003", "DRV-DEMO-003", None),
            ("Sana Sheikh", "+91 90000 10004", "DRV-DEMO-004", None),
            ("Vikram Das", "+91 90000 10005", "DRV-DEMO-005", None),
            ("Priya Iyer", "+91 90000 10006", "DRV-DEMO-006", None),
            ("Imran Ali", "+91 90000 10007", "DRV-DEMO-007", None),
            ("Kiran Patel", "+91 90000 10008", "DRV-DEMO-008", None),
        ]
        drivers = []
        for name, phone, reference, linked_user in driver_data:
            driver, _ = FleetDriver.objects.get_or_create(tenant=tenant, reference_code=reference, defaults={
                "name": name, "contact_phone": phone, "user": linked_user, "status": FleetDriver.Status.ACTIVE,
            })
            if linked_user and driver.user_id != linked_user.id:
                driver.user = linked_user
                driver.save(update_fields=["user"])
            drivers.append(driver)

        customer_data = [
            ("Deccan Fresh Foods", "Bengaluru", "+91 80200 11001"),
            ("Cauvery Auto Components", "Mysuru", "+91 82100 11002"),
            ("Coromandel Retail Group", "Chennai", "+91 44200 11003"),
            ("Nandi Pharma Distribution", "Hyderabad", "+91 40200 11004"),
            ("Western Ghats Coffee Co.", "Mangaluru", "+91 82400 11005"),
            ("Southline Electricals", "Coimbatore", "+91 42200 11006"),
        ]
        customers = []
        for index, (name, city, phone) in enumerate(customer_data, 1):
            customer, _ = FleetCustomer.objects.get_or_create(tenant=tenant, name=name, defaults={
                "contact_name": ["Nisha Rao", "Karthik Shetty", "Anand Kumar", "Farah Khan", "Dev Menon", "Latha Reddy"][index-1],
                "email": f"logistics{index}@{['deccanfresh','cauveryauto','coromandel','nandipharma','westerncoffee','southline'][index-1]}.demo",
                "phone": phone, "gstin": f"29DEMOX123{index}A1Z5", "billing_address": f"{city}, India",
                "dock_free_minutes": 60, "detention_rate_per_hour": Decimal("850.00"),
            })
            customers.append(customer)

        trip_specs = [
            ("BLR-CHN", 0, 0, "Bengaluru, KA", "Chennai, TN", Decimal("58000"), "IN_PROGRESS"),
            ("BLR-MYS", 1, 1, "Bengaluru, KA", "Mysuru, KA", Decimal("24500"), "IN_PROGRESS"),
            ("HYD-BLR", 2, 2, "Hyderabad, TS", "Bengaluru, KA", Decimal("46500"), "IN_PROGRESS"),
            ("BLR-CBE", 3, 3, "Bengaluru, KA", "Coimbatore, TN", Decimal("42000"), "APPROVED"),
            ("MYS-MNG", 4, 4, "Mysuru, KA", "Mangaluru, KA", Decimal("31500"), "APPROVED"),
            ("CHN-BLR", 5, 5, "Chennai, TN", "Bengaluru, KA", Decimal("53500"), "APPROVED"),
            ("BLR-HYD", 6, 6, "Bengaluru, KA", "Hyderabad, TS", Decimal("62500"), "APPROVED"),
            ("BLR-CHN", 7, 0, "Bengaluru, KA", "Chennai, TN", Decimal("59000"), "SUBMITTED"),
            ("MYS-CBE", 1, 1, "Mysuru, KA", "Coimbatore, TN", Decimal("27800"), "COMPLETED"),
            ("BLR-MNG", 2, 2, "Bengaluru, KA", "Mangaluru, KA", Decimal("38800"), "DRAFT"),
        ]
        orders = []
        trips = []
        live_paths = [
            [(12.9716, 77.5946), (13.0080, 77.6750), (13.0710, 77.8420), (13.1540, 78.1080), (13.2300, 78.3370)],
            [(12.2958, 76.6394), (12.3740, 76.7420), (12.5070, 76.9020), (12.6620, 77.1010), (12.7790, 77.2600)],
            [(17.3850, 78.4867), (17.1720, 78.4150), (16.9630, 78.3220), (16.7360, 78.2280), (16.5400, 78.1680)],
        ]
        for index, (route_code, vehicle_index, driver_index, origin, destination, rate, trip_status) in enumerate(trip_specs):
            customer = customers[index % len(customers)]
            pickup_at = now - timedelta(hours=2 + index) if trip_status in {"IN_PROGRESS", "APPROVED", "SUBMITTED", "COMPLETED"} else None
            delivered = trip_status in {"APPROVED", "SUBMITTED", "COMPLETED"}
            due_at = (pickup_at or now) + timedelta(hours=7)
            order, _ = TransportOrder.objects.get_or_create(tenant=tenant, order_number=f"ORD-DEMO-{index+1:03}", defaults={
                "customer": customer, "origin": origin, "destination": destination,
                "pickup_due_at": due_at - timedelta(hours=1), "delivery_due_at": due_at,
                "cargo_description": ["Chilled produce", "Automotive spares", "Packaged essentials", "Pharmaceutical cartons"][index % 4],
                "required_vehicle_type": vehicles[vehicle_index].vehicle_type, "load_quantity": Decimal("2.5"),
                "load_unit": "TONNE", "agreed_amount": rate, "customer_reference": f"PO-{customer.id.hex[:6].upper()}-{index+21}",
                "status": TransportOrder.Status.IN_TRANSIT if trip_status == "IN_PROGRESS" else TransportOrder.Status.DELIVERED if delivered else TransportOrder.Status.ASSIGNED,
                "created_by": owner,
            })
            orders.append(order)
            if trip_status == "DRAFT":
                trip_start = None
                end_at = delivery_at = None
            elif trip_status == "IN_PROGRESS":
                trip_start = pickup_at
                end_at = delivery_at = None
            else:
                trip_start = pickup_at or now - timedelta(days=index + 1)
                end_at = trip_start + timedelta(hours=5 + index % 3)
                delivery_at = end_at
            trip, _ = FleetTrip.objects.get_or_create(tenant=tenant, trip_number=f"KP-DEMO-{2026}{index+1:03}", defaults={
                "vehicle": vehicles[vehicle_index], "driver": drivers[driver_index], "transport_order": order,
                "customer_reference": order.customer_reference, "origin": origin, "destination": destination,
                "starts_at": trip_start, "pickup_at": trip_start, "loaded_at": trip_start + timedelta(minutes=45) if trip_start else None,
                "ends_at": end_at, "delivery_at": delivery_at,
                "predicted_arrival_at": now + timedelta(hours=2 + index) if trip_status == "IN_PROGRESS" else delivery_at,
                "eta_source": "HISTORICAL_ROUTE_MEDIAN" if trip_status == "IN_PROGRESS" else "",
                "route_distance_m": 330000 + index * 18000,
                "odometer_start": Decimal("128400") + index * Decimal("1140"),
                "odometer_end": Decimal("128730") + index * Decimal("1140") if delivered else None,
                "delivery_signature_name": f"{customer.contact_name} · Demo POD" if delivered else "",
                "status": trip_status, "submitted_by": owner if trip_status == "SUBMITTED" else None,
                "submitted_at": now - timedelta(hours=1) if trip_status == "SUBMITTED" else None,
                "reviewed_by": owner if trip_status == "APPROVED" else None,
                "reviewed_at": now - timedelta(days=1) if trip_status == "APPROVED" else None,
                "review_note": "Demo record approved for client walkthrough." if trip_status == "APPROVED" else "",
                "created_by": owner,
            })
            trips.append(trip)
            revenue_status = TripRevenueLine.ReviewStatus.APPROVED if trip_status == "APPROVED" else TripRevenueLine.ReviewStatus.SUBMITTED if trip_status == "SUBMITTED" else TripRevenueLine.ReviewStatus.DRAFT
            TripRevenueLine.objects.get_or_create(tenant=tenant, trip=trip, description="Agreed freight charge", defaults={
                "amount": rate, "status": revenue_status,
            })
            for category, description, amount, litres, budget in [
                ("FUEL", "Diesel purchase · synthetic demo entry", Decimal("7900.00") if index == 3 else Decimal("6400.00") + index * Decimal("250.00"), Decimal("82.00") if index == 3 else Decimal("58.00") + index * Decimal("2"), Decimal("4200.00") if index == 3 else Decimal("7000.00")),
                ("TOLL", "FASTag tolls · demo", Decimal("1850.00") + index * Decimal("110.00"), None, Decimal("2500.00")),
                ("ALLOWANCE", "Driver trip allowance", Decimal("900.00"), None, Decimal("1200.00")),
            ]:
                expense_status = TripExpenseLine.ReviewStatus.APPROVED if trip_status == "APPROVED" else TripExpenseLine.ReviewStatus.SUBMITTED if trip_status == "SUBMITTED" else TripExpenseLine.ReviewStatus.DRAFT
                key = uuid.uuid5(uuid.NAMESPACE_URL, f"kriyo-demo-expense-{trip.trip_number}-{category}")
                TripExpenseLine.objects.get_or_create(tenant=tenant, idempotency_key=key, defaults={
                    "trip": trip, "category": category, "description": description, "amount": amount,
                    "budgeted_amount": budget, "quantity_litres": litres, "incurred_at": today - timedelta(days=index),
                    "payee": "Demo Fuel & Fleet Services", "payment_reference": f"DEMO-{index+1:03}-{category}",
                    "status": expense_status, "created_by": owner,
                })

        # A few unassigned orders keep dispatch and return-load views useful.
        for index in range(4):
            customer = customers[(index + 2) % len(customers)]
            TransportOrder.objects.get_or_create(tenant=tenant, order_number=f"ORD-DEMO-{len(trip_specs)+index+1:03}", defaults={
                "customer": customer, "origin": ["Bengaluru, KA", "Mysuru, KA", "Chennai, TN", "Hyderabad, TS"][index],
                "destination": ["Pune, MH", "Coimbatore, TN", "Mangaluru, KA", "Vijayawada, AP"][index],
                "pickup_due_at": now + timedelta(hours=5 + index * 3), "delivery_due_at": now + timedelta(days=1 + index),
                "cargo_description": "Retail replenishment cartons", "required_vehicle_type": "RIGID",
                "load_quantity": Decimal("4.0"), "load_unit": "TONNE", "agreed_amount": Decimal("36500") + index * Decimal("2400"),
                "customer_reference": f"DEMO-BOOKING-{index+1:03}", "status": TransportOrder.Status.OPEN, "created_by": owner,
            })

        # Current phone GPS, short route history, and sample hardware devices are all synthetic.
        for index in range(3):
            trip = trips[index]
            driver = drivers[index]
            for point_index, (latitude, longitude) in enumerate(live_paths[index]):
                captured = now - timedelta(minutes=(len(live_paths[index]) - point_index - 1) * 8)
                event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"kriyo-demo-gps-{trip.trip_number}-{point_index}")
                sample, _ = FleetTripLocationSample.objects.get_or_create(tenant=tenant, client_event_id=event_id, defaults={
                    "trip": trip, "reported_by": driver.user, "source_provider": "PHONE", "latitude": Decimal(str(latitude)),
                    "longitude": Decimal(str(longitude)), "accuracy_m": Decimal("18.00"),
                    "speed_kmh": Decimal("46.00") if point_index else Decimal("12.00"), "heading_degrees": Decimal("92.00"),
                    "captured_at": captured,
                })
            latitude, longitude = live_paths[index][-1]
            location_event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"kriyo-demo-current-gps-{trip.trip_number}")
            location, _ = FleetTripLocation.objects.update_or_create(tenant=tenant, trip=trip, defaults={
                "reported_by": driver.user, "source_provider": "PHONE", "latitude": Decimal(str(latitude)),
                "longitude": Decimal(str(longitude)), "accuracy_m": Decimal("18.00"), "speed_kmh": Decimal("46.00"),
                "heading_degrees": Decimal("92.00"), "captured_at": now, "client_event_id": location_event_id,
            })
            FleetGpsDevice.objects.get_or_create(provider="DEMO_TRACKER", device_id=f"KP-DEMO-GPS-{index+1:03}", defaults={
                "tenant": tenant, "vehicle": vehicles[index], "active": True, "created_by": owner,
            })

        # Sites and dwell/arrival events for the geofence walkthrough.
        geofence, _ = FleetGeofence.objects.get_or_create(tenant=tenant, name="Bengaluru Distribution Hub", defaults={
            "site_type": FleetGeofence.SiteType.WAREHOUSE, "active": True, "current_version": 1,
            "dwell_alert_minutes": 45, "created_by": owner,
        })
        FleetGeofenceVersion.objects.get_or_create(geofence=geofence, version=1, defaults={
            "shape": FleetGeofence.Shape.CIRCLE,
            "geometry": {"center": [77.5946, 12.9716], "radius_m": 650},
            "reason": "Synthetic Bengaluru demo site boundary", "created_by": owner,
        })
        geofence_sample = FleetTripLocationSample.objects.filter(tenant=tenant, trip=trips[0]).order_by("captured_at").first()
        if geofence_sample:
            FleetGeofenceEvent.objects.get_or_create(tenant=tenant, trip=trips[0], geofence=geofence,
                source_sample=geofence_sample, event_type=FleetGeofenceEvent.EventType.ARRIVAL, defaults={
                    "version": 1, "latitude": geofence_sample.latitude, "longitude": geofence_sample.longitude,
                    "occurred_at": geofence_sample.captured_at,
                })
        dock, _ = FleetDock.objects.get_or_create(tenant=tenant, site_name="Bengaluru Distribution Hub", code="DOCK-A", defaults={
            "name": "Dock A", "parallel_capacity": 2, "active": True,
        })
        open_orders = list(TransportOrder.objects.filter(tenant=tenant, status=TransportOrder.Status.OPEN).order_by("order_number")[:2])
        for index, order in enumerate(open_orders):
            start = now + timedelta(hours=3 + index * 2)
            DockAppointment.objects.get_or_create(tenant=tenant, order=order, appointment_type=DockAppointment.AppointmentType.PICKUP,
                defaults={"dock": dock, "starts_at": start, "ends_at": start + timedelta(hours=1),
                    "status": DockAppointment.Status.BOOKED,
                    "idempotency_key": uuid.uuid5(uuid.NAMESPACE_URL, f"kriyo-demo-dock-{order.order_number}"),
                    "notes": "Demo dispatch calendar booking", "created_by": owner})

        for index, vehicle in enumerate(vehicles[:4]):
            FleetMaintenanceRecord.objects.get_or_create(tenant=tenant, vehicle=vehicle,
                description="Demo preventive maintenance" if index != 2 else "Demo brake inspection", defaults={
                    "category": FleetMaintenanceRecord.Category.SERVICE if index != 2 else FleetMaintenanceRecord.Category.BRAKES,
                    "failure_code": "BRAKE_WEAR" if index == 2 else "", "description": "Demo preventive maintenance" if index != 2 else "Demo brake inspection",
                    "service_date": today - timedelta(days=12 + index * 6), "odometer_km": Decimal("128100") + index * Decimal("760"),
                    "cost": Decimal("8400.00") + index * Decimal("1250.00"), "vendor": "Bengaluru Fleet Care · Demo",
                    "next_due_date": today + timedelta(days=30 - index * 4), "next_due_odometer_km": Decimal("135000") + index * Decimal("500"),
                    "notes": "Synthetic maintenance record for the demo workspace.", "created_by": owner,
                })

        # Revenue, invoices, collections, and operator review queues.
        approved_trips = [trip for trip in trips if trip.status == FleetTrip.Status.APPROVED]
        invoices = []
        invoice_statuses = [TransportInvoice.Status.ISSUED, TransportInvoice.Status.PARTIALLY_PAID,
            TransportInvoice.Status.PAID, TransportInvoice.Status.ISSUED]
        for index, trip in enumerate(approved_trips):
            order = trip.transport_order
            amount = order.agreed_amount or Decimal("42000.00")
            invoice, _ = TransportInvoice.objects.get_or_create(tenant=tenant, invoice_number=f"KPL-DEMO-{index+1:04}", defaults={
                "customer": order.customer, "order": order, "trip": trip, "invoice_date": today - timedelta(days=index+2),
                "due_date": today + timedelta(days=14-index*2), "amount": amount, "status": invoice_statuses[index % len(invoice_statuses)],
                "issued_at": now - timedelta(days=index+1) if index != 2 else now - timedelta(days=3),
                "issued_by": owner, "created_by": owner,
                "notes": "Synthetic demo invoice · not a tax invoice",
            })
            invoices.append(invoice)
            if invoice.status == TransportInvoice.Status.PARTIALLY_PAID:
                TransportCollection.objects.get_or_create(tenant=tenant, invoice=invoice, reference="DEMO-UPI-001", defaults={
                    "amount": (amount * Decimal("0.55")).quantize(Decimal("0.01")), "received_date": today - timedelta(days=1),
                    "method": TransportCollection.Method.UPI, "created_by": owner, "notes": "Synthetic partial collection",
                })
            elif invoice.status == TransportInvoice.Status.PAID:
                TransportCollection.objects.get_or_create(tenant=tenant, invoice=invoice, reference="DEMO-NEFT-002", defaults={
                    "amount": amount, "received_date": today - timedelta(days=2), "method": TransportCollection.Method.BANK,
                    "created_by": owner, "notes": "Synthetic full collection",
                })

        # Salary policies and a partially settled monthly record.
        month_start = today.replace(day=1)
        for index, driver in enumerate(drivers):
            DriverPayPolicy.objects.get_or_create(tenant=tenant, driver=driver, effective_from=month_start - timedelta(days=60), defaults={
                "basis": DriverPayPolicy.Basis.MONTHLY, "rate": Decimal("32000.00") + index * Decimal("1500.00"), "created_by": owner,
            })
        salary, _ = DriverSalaryRecord.objects.get_or_create(tenant=tenant, driver=drivers[0], period_start=month_start,
            settlement_number=1, defaults={"salary_amount": Decimal("36000.00"), "status": DriverSalaryRecord.Status.APPROVED,
                "submitted_by": owner, "submitted_at": now - timedelta(days=4), "approved_by": owner,
                "approved_at": now - timedelta(days=3), "created_by": owner, "review_note": "Approved synthetic demo settlement."})
        payment_key = uuid.uuid5(uuid.NAMESPACE_URL, f"kriyo-demo-salary-payment-{salary.id}")
        DriverSalaryPayment.objects.get_or_create(tenant=tenant, idempotency_key=payment_key, defaults={
            "salary_record": salary, "amount": Decimal("22000.00"), "payment_date": today - timedelta(days=1),
            "payment_reference": "DEMO-NEFT-SAL-001", "notes": "Synthetic salary payment", "created_by": owner,
        })
        follow_trip = trips[7]
        FleetFollowUp.objects.get_or_create(tenant=tenant, trip=follow_trip, category="FUEL_RECEIPT",
            description="Review fuel receipt and litre quantity before approving trip costs", defaults={
                "due_at": now + timedelta(hours=6), "status": FleetFollowUp.Status.OPEN, "created_by": owner,
            })
        FleetExceptionCase.objects.get_or_create(tenant=tenant, source_key="DEMO-FUEL-ANOMALY-001", defaults={
            "category": "FUEL_ANOMALY", "evidence": {"seeded_demo": True, "trip_number": trips[3].trip_number,
                "vehicle": vehicles[3].registration_number, "message": "Fuel cost and litres exceed the configured trip budget; review the synthetic receipt.",
                "next_action": "Compare the receipt with the odometer distance and driver report."},
            "status": "OPEN", "owner": owner, "due_at": now + timedelta(hours=4),
        })

        # A public demo URL and intentionally failed notices illustrate the customer view
        # without sending email/WhatsApp or claiming a real customer granted consent.
        portal_trip = trips[0]
        ShipmentAccessLink.objects.filter(tenant=tenant, trip=portal_trip,
            consent_note__startswith="SYNTHETIC DEMO ONLY", revoked_at__isnull=True).update(revoked_at=now)
        portal_token = secrets.token_urlsafe(32)
        portal_link = ShipmentAccessLink.objects.create(tenant=tenant, trip=portal_trip,
            token_hash=hashlib.sha256(portal_token.encode()).hexdigest(),
            notify_email="demo-recipient@deccanfresh.demo", notify_phone="+919000010001",
            consent_note=DEMO_PORTAL_NOTE, expires_at=now + timedelta(days=7), created_by=owner)
        for channel, recipient in (("EMAIL", portal_link.notify_email), ("WHATSAPP", portal_link.notify_phone)):
            event_key = "status:IN_TRANSIT"
            delivery_key = hashlib.sha256(f"{tenant.id}:{portal_trip.id}:{recipient.casefold()}:{event_key}:{channel}".encode()).hexdigest()
            ShipmentNotice.objects.get_or_create(delivery_key=delivery_key, defaults={
                "link": portal_link, "event_key": event_key, "channel": channel,
                "payload": {"recipient": recipient, "order_number": portal_trip.transport_order.order_number,
                    "status": "IN_TRANSIT", "eta": portal_trip.predicted_arrival_at.isoformat() if portal_trip.predicted_arrival_at else "Demo ETA"},
                "status": "FAILED", "attempts": 0,
                "last_error": "Synthetic demo only · no message was sent to a customer.",
            })

        # Return-load opportunities from approved trips to unassigned orders.
        free_orders = list(TransportOrder.objects.filter(tenant=tenant, status=TransportOrder.Status.OPEN).order_by("order_number"))
        for index, (source_trip, order) in enumerate(zip(approved_trips[:2], free_orders[:2])):
            ReturnLoadOffer.objects.get_or_create(tenant=tenant, source_trip=source_trip, order=order,
                defaults={"status": ReturnLoadOffer.Status.OFFERED, "proposed_amount": Decimal("28500.00") + index * Decimal("3200.00"),
                    "notes": "Synthetic return-load match for demonstration", "offered_by": owner})

        return {"vehicles": FleetVehicle.objects.filter(tenant=tenant).count(),
            "drivers": FleetDriver.objects.filter(tenant=tenant).count(), "orders": TransportOrder.objects.filter(tenant=tenant).count(),
            "trips": FleetTrip.objects.filter(tenant=tenant).count(), "invoices": TransportInvoice.objects.filter(tenant=tenant).count(),
            "locations": FleetTripLocation.objects.filter(tenant=tenant).count(),
            "portal_url": f"{settings.FRONTEND_URL.rstrip('/')}/portal/shipment/{portal_token}"}
