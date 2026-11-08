from partners.services import frontend_link
from partners.instance import product_name
from django.conf import settings
from django.core.mail import send_mail

from celery import shared_task
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta

from accounts.models import Membership
from notifications.models import Notification, NotificationPreference
from invoices.models import Invoice
from .models import FleetFollowUp, FleetReminderDelivery, FleetTrip, FleetTripLocation, FleetTripLocationSample, TripExpenseLine
from .models import DriverSalaryRecord, FleetDriver


@shared_task
def prune_fleet_location_history(batch_size=5000):
    """Delete an auditable, bounded batch of expired raw GPS history and stale projections."""
    import os
    try:
        retention_days = int(os.environ.get("FLEET_GPS_HISTORY_RETENTION_DAYS", "90"))
    except (TypeError, ValueError):
        retention_days = 90
    if not 30 <= retention_days <= 3650:
        retention_days = 90
    try:
        batch_size = max(1, min(int(batch_size), 10000))
    except (TypeError, ValueError):
        batch_size = 5000
    cutoff = timezone.now() - timedelta(days=retention_days)
    sample_ids = list(FleetTripLocationSample.objects.filter(captured_at__lt=cutoff)
        .order_by("captured_at").values_list("id", flat=True)[:batch_size])
    if sample_ids:
        FleetTripLocationSample.objects.filter(id__in=sample_ids).delete()
    latest_ids = list(FleetTripLocation.objects.filter(captured_at__lt=cutoff)
        .order_by("captured_at").values_list("id", flat=True)[:batch_size])
    if latest_ids:
        FleetTripLocation.objects.filter(id__in=latest_ids).delete()
    remaining = FleetTripLocationSample.objects.filter(captured_at__lt=cutoff).exists() or FleetTripLocation.objects.filter(captured_at__lt=cutoff).exists()
    return {"retention_days": retention_days, "cutoff": cutoff.isoformat(),
        "samples_deleted": len(sample_ids), "latest_locations_deleted": len(latest_ids), "more_pending": remaining}


def _send_once(tenant, user, key, reminder_date, title, body, link, category="fleet", channels=None):
    from accounts.workspace_access import workspace_is_operational
    if not workspace_is_operational(tenant):
        return False
    preference = NotificationPreference.objects.filter(tenant=tenant, user=user).first()
    if preference and not preference.preferences.get(category, True):
        return False
    with transaction.atomic():
        delivery, created = FleetReminderDelivery.objects.get_or_create(
            tenant=tenant,
            recipient=user,
            reminder_key=key,
            reminder_date=reminder_date,
        )
        if not created:
            return False
        for channel in channels or ["IN_APP"]:
            notification = Notification.objects.create(
                tenant=tenant, recipient=user, channel=channel,
                status="UNREAD" if channel == "IN_APP" else "PENDING",
                payload={"title": title, "body": body, "link": link, "category": category},
            )
            if channel == "EMAIL":
                sent = send_mail(title, f"{body}\n\nOpen {product_name()}: {frontend_link(link)}", settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
                if sent:
                    notification.status = "SENT"
                    notification.save(update_fields=["status"])
    return True


@shared_task
def maintain_fleet_exceptions():
    from types import SimpleNamespace
    from tenants.models import Tenant
    from .models import FleetExceptionCase
    from .exceptions import sync_cases
    from .access import fleet_enabled
    from accounts.workspace_access import workspace_is_operational
    from .tracking_episodes import expire_stale_tracking_episodes
    episode_maintenance = expire_stale_tracking_episodes()
    created = notified = 0
    for tenant in Tenant.objects.filter(is_deleted=False).iterator():
        if not workspace_is_operational(tenant) or not fleet_enabled(tenant):continue
        memberships = list(Membership.objects.filter(tenant=tenant, is_active=True).exclude(role="DRIVER").select_related("user"))
        reviewer=next((member for member in memberships if member.role in {"OWNER","FINANCE","FLEET","APPROVER"}),None)
        if not reviewer:
            continue
        created += sync_cases(SimpleNamespace(tenant=tenant, membership=reviewer, user=reviewer.user))
        controls = tenant.settings.get("fleet_controls", {})
        channels = controls.get("channels", ["IN_APP"])
        hours = int(controls.get("escalation_hours", 24))
        escalation_roles=set(controls.get("recipient_roles",["OWNER","FINANCE","APPROVER"]))
        now = timezone.now()
        tracking_categories={"LONG_SITE_DWELL","STOP_OUTSIDE_SITE","PROLONGED_STOP","ROUTE_DEVIATION"}
        for case in FleetExceptionCase.objects.filter(tenant=tenant, category__in=tracking_categories,
                status__in=["OPEN","CONFIRMED"], created_at__gte=now-timedelta(minutes=10)).select_related("owner"):
            recipients={member.user_id:member.user for member in memberships
                if member.user_id==case.owner_id or (not case.owner_id and member.role in escalation_roles)}
            for user in recipients.values():
                notified+=int(_send_once(tenant,user,f"case:{case.id}:created",timezone.localdate(),
                    "New fleet tracking alert",f"{case.category}: {case.evidence.get('message','')}",
                    "/fleet/exception-center",channels=channels))
        for case in FleetExceptionCase.objects.filter(tenant=tenant, status__in=["OPEN", "CONFIRMED"], due_at__lte=now).select_related("owner"):
            escalated = now >= case.due_at + timedelta(hours=hours)
            recipients = {member.user_id: member.user for member in memberships
                if (escalated and member.role in escalation_roles) or member.user_id == case.owner_id or (not case.owner_id and member.role in escalation_roles)}
            for user in recipients.values():
                notified += int(_send_once(tenant, user, f"case:{case.id}:{'escalated' if escalated else 'due'}",
                    timezone.localdate(), "Fleet exception requires action", f"{case.category}: {case.evidence.get('message', '')}",
                    "/fleet/exception-center", channels=channels))
    return {"created": created, "notified": notified, **episode_maintenance}


@shared_task
def refresh_fleet_routes():
    import os
    from accounts.workspace_access import workspace_is_operational
    if not os.environ.get("GOOGLE_MAPS_ROUTES_API_KEY"):
        return {"status":"NOT_CONFIGURED"}
    results=[]
    trips=FleetTrip.objects.filter(status="IN_PROGRESS",tenant__is_deleted=False,tenant__settings__fleet_controls__route_eta_enabled=True,
        latest_phone_location__captured_at__gte=timezone.now()-timedelta(minutes=2)).select_related("tenant","transport_order").order_by(F("route_attempted_at").asc(nulls_first=True))[:100]
    for trip in trips:
        if workspace_is_operational(trip.tenant) and trip.tenant.settings.get("fleet_controls",{}).get("route_eta_enabled",False):
            refresh_fleet_route.delay(str(trip.id))
            results.append({"trip_id":str(trip.id),"status":"QUEUED"})
    return {"results":results}


@shared_task
def refresh_fleet_route(trip_id):
    from .routing import refresh_route
    from accounts.workspace_access import workspace_is_operational
    trip=FleetTrip.objects.filter(id=trip_id,status="IN_PROGRESS",tenant__is_deleted=False).select_related("tenant","transport_order").first()
    return refresh_route(trip) if trip and workspace_is_operational(trip.tenant) else {"status":"TRIP_NOT_ACTIVE"}


@shared_task
def maintain_customer_notices():
    from .customer_notifications import queue_customer_notices,recover_stale_notices
    from .models import ShipmentNotice
    queued=queue_customer_notices()
    recovered=recover_stale_notices()
    ids=list(ShipmentNotice.objects.filter(status="PENDING",next_attempt_at__lte=timezone.now()).values_list("id",flat=True)[:100])
    for notice_id in ids:send_customer_notice.delay(str(notice_id))
    return {"new_notices":queued,"send_jobs":len(ids),"uncertain_jobs_recovered":recovered}


@shared_task
def send_customer_notice(notice_id):
    from .customer_notifications import process_notices
    return {"processed":process_notices(notice_id)}


@shared_task
def send_fleet_reminders():
    from accounts.workspace_access import workspace_is_operational
    now = timezone.now()
    reminder_date = timezone.localdate(now)
    review_roles = [Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.APPROVER]
    follow_up_roles = [Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.APPROVER, Membership.Role.PURCHASE, "FLEET"]
    review_count = follow_up_count = 0

    # Turn incomplete trip closeouts and fuel/mileage anomalies into assigned,
    # trackable work items before reminder escalation begins.
    automatic_followups = 0
    trips_to_check = FleetTrip.objects.filter(status__in=[FleetTrip.Status.COMPLETED,
        FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED]).select_related("tenant", "vehicle", "driver")
    for trip in trips_to_check.iterator(chunk_size=200):
        if not workspace_is_operational(trip.tenant):
            continue
        controls = trip.tenant.settings.get("fleet_controls", {})
        due_at = now
        issues = []
        if trip.odometer_start is None or trip.odometer_end is None:
            issues.append(("MISSING_ODOMETER", f"Trip {trip.trip_number} needs both pickup and delivery odometer readings."))
        if trip.delivery_at and not trip.delivery_proof_id and not trip.delivery_signature_name.strip():
            issues.append(("MISSING_DELIVERY_PROOF", f"Trip {trip.trip_number} needs a delivery photo or recipient signature."))
        expenses = list(trip.expense_lines.all())
        for expense in expenses:
            if expense.status != TripExpenseLine.ReviewStatus.REJECTED and not expense.is_estimated and not expense.receipt_id:
                issues.append(("MISSING_RECEIPT", f"Trip {trip.trip_number}: upload a receipt for {expense.description} (₹{expense.amount})."))
        if trip.odometer_start is not None and trip.odometer_end is not None:
            distance = trip.odometer_end - trip.odometer_start
            fuel_litres = sum((item.quantity_litres or Decimal("0")) for item in expenses
                if item.category == TripExpenseLine.Category.FUEL and item.status != TripExpenseLine.ReviewStatus.REJECTED and not item.is_estimated)
            expected = trip.vehicle.expected_km_per_litre
            if expected and distance > 0 and fuel_litres > 0:
                try:
                    tolerance = Decimal(str(controls.get("fuel_efficiency_tolerance_percent", "20")))
                except Exception:
                    tolerance = Decimal("20")
                minimum = expected * (Decimal("1") - tolerance / Decimal("100"))
                efficiency = distance / fuel_litres
                if efficiency < minimum:
                    issues.append(("FUEL_EFFICIENCY", f"Trip {trip.trip_number} returned {efficiency:.1f} km/L against the configured {expected} km/L baseline; review fuel receipts and odometer readings."))
            elif expected and distance > 0:
                issues.append(("MISSING_FUEL_DATA", f"Trip {trip.trip_number} needs fuel litres and a receipt to compare mileage against the truck baseline."))
        for category, description in issues:
            if FleetFollowUp.objects.filter(tenant=trip.tenant, trip=trip, category=category, description=description).exists():
                continue
            FleetFollowUp.objects.create(tenant=trip.tenant, trip=trip, category=category,
                description=description[:240], due_at=due_at)
            automatic_followups += 1

    # A draft-only preparation can run at the start of each month. It applies
    # effective salary policies and approved trip earnings; no payments are sent.
    auto_prepared = 0
    if reminder_date.day == 1:
        from .views import prepare_driver_settlements
        prior_month = date(reminder_date.year - int(reminder_date.month == 1),
            12 if reminder_date.month == 1 else reminder_date.month - 1, 1)
        for tenant_id in FleetDriver.objects.filter(status=FleetDriver.Status.ACTIVE).values_list("tenant_id", flat=True).distinct().iterator():
            from tenants.models import Tenant
            tenant = Tenant.objects.filter(pk=tenant_id, is_deleted=False).first()
            if not tenant or not workspace_is_operational(tenant) or not tenant.settings.get("fleet_controls", {}).get("auto_prepare_settlements", True):
                continue
            result = prepare_driver_settlements(tenant, prior_month)
            auto_prepared += result["created"]
            for issue in result["discrepancies"]:
                description = f"{issue['driver']}: {issue['reason']}"[:240]
                if not FleetFollowUp.objects.filter(tenant=tenant, category="SALARY_POLICY", description=description).exists():
                    FleetFollowUp.objects.create(tenant=tenant, category="SALARY_POLICY", description=description, due_at=now)
            from audit.models import AuditLog


            if result["created"] or result["discrepancies"]:
                AuditLog.objects.create(tenant=tenant, actor=None, action="FLEET_DRIVER_SETTLEMENTS_AUTO_PREPARED",
                    object_type="DriverSalaryRecord", object_id=prior_month.strftime("%Y-%m"),
                    metadata={"period": prior_month.strftime("%Y-%m"), "policy_version": result["policy_version"],
                        "created": result["created"], "discrepancies": result["discrepancies"], "money_movement_enabled": False})

    waiting_trips = FleetTrip.objects.filter(
        status=FleetTrip.Status.SUBMITTED,
        submitted_at__isnull=False,
    ).select_related("tenant")
    for trip in waiting_trips.iterator():
        controls = trip.tenant.settings.get("fleet_controls", {})
        roles = controls.get("recipient_roles", review_roles)
        channels = controls.get("channels", ["IN_APP"])
        interval = max(1, int(controls.get("escalation_hours", 24)))
        age = now - trip.submitted_at
        stage = int(age.total_seconds() // (interval * 3600))
        if stage < 1: continue
        recipients = Membership.objects.filter(tenant_id=trip.tenant_id, is_active=True, role__in=roles).select_related("user")
        for member in recipients.iterator():
            if _send_once(
                trip.tenant,
                member.user,
                f"trip-review:{trip.id}:stage-{stage}",
                reminder_date,
                "Trip waiting for review",
                f"Trip {trip.trip_number} has been waiting for review for more than 24 hours.",
                "/fleet", channels=channels,
            ):
                review_count += 1

    overdue_follow_ups = FleetFollowUp.objects.filter(
        status__in=[FleetFollowUp.Status.OPEN, FleetFollowUp.Status.IN_PROGRESS],
        due_at__isnull=False,
        due_at__lte=now,
    ).select_related("tenant", "trip")
    for follow_up in overdue_follow_ups.iterator():
        controls = follow_up.tenant.settings.get("fleet_controls", {})
        roles = controls.get("recipient_roles", follow_up_roles)
        channels = controls.get("channels", ["IN_APP"])
        interval = max(1, int(controls.get("escalation_hours", 24)))
        stage = max(1, int((now - follow_up.due_at).total_seconds() // (interval * 3600)))
        if stage < 1: continue
        recipients = Membership.objects.filter(tenant_id=follow_up.tenant_id, is_active=True, role__in=roles).select_related("user")
        recipient_users = {member.user_id: member.user for member in recipients}
        if follow_up.trip_id and follow_up.trip.driver.user_id:
            driver_user = follow_up.trip.driver.user
            recipient_users[driver_user.id] = driver_user
        trip_ref = f" (trip {follow_up.trip.trip_number})" if follow_up.trip_id else ""
        for recipient in recipient_users.values():
            if _send_once(
                follow_up.tenant,
                recipient,
            f"follow-up:{follow_up.id}:stage-{stage}",
                reminder_date,
                "Fleet follow-up is overdue",
                f"{follow_up.description}{trip_ref} is overdue. Please review and resolve it.",
                "/fleet/alerts", channels=channels,
            ):
                follow_up_count += 1

    missing_pod_count = 0  # Proof gaps now use the same assigned follow-up and escalation path.

    overdue_invoice_count = salary_balance_count = 0
    finance_roles = [Membership.Role.OWNER, Membership.Role.FINANCE]
    overdue_invoices = Invoice.objects.filter(
        due_date__lt=reminder_date,
        payment_status__in=["UNPAID", "PARTIALLY_PAID"],
    ).exclude(status=Invoice.Status.REJECTED).select_related("tenant", "vendor")
    for invoice in overdue_invoices.iterator():
        controls = invoice.tenant.settings.get("fleet_controls", {})
        roles = controls.get("recipient_roles", finance_roles)
        channels = controls.get("channels", ["IN_APP"])
        interval = max(1, int(controls.get("escalation_hours", 24)))
        stage = int((now.date() - invoice.due_date).days * 24 // interval)
        if stage < 1: continue
        recipients = Membership.objects.filter(tenant_id=invoice.tenant_id, is_active=True, role__in=roles).select_related("user")
        for member in recipients.iterator():
            if _send_once(invoice.tenant, member.user, f"invoice-overdue:{invoice.id}:stage-{stage}", reminder_date,
                "Invoice payment is overdue", f"Invoice {invoice.invoice_number or invoice.id} is past its due date ({invoice.due_date}).",
                "/payments", category="payables", channels=channels):
                overdue_invoice_count += 1

    month_start = reminder_date.replace(day=1)
    salary_records = DriverSalaryRecord.objects.filter(period_start__lt=month_start, status__in=[DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID]).select_related("tenant", "driver")
    for record in salary_records.iterator():
        paid = record.payments.aggregate(total=Sum("amount"))["total"] or 0
        recovered = record.advance_recoveries.aggregate(total=Sum("amount"))["total"] or 0
        remaining = record.gross_earnings_amount - paid - recovered
        if remaining <= 0:
            continue
        controls = record.tenant.settings.get("fleet_controls", {})
        roles = controls.get("recipient_roles", [*finance_roles, "FLEET"])
        channels = controls.get("channels", ["IN_APP"])
        interval = max(1, int(controls.get("escalation_hours", 24)))
        stage = max(1, int((reminder_date - month_start).days * 24 // interval))
        recipients = Membership.objects.filter(tenant_id=record.tenant_id, is_active=True, role__in=roles).select_related("user")
        for member in recipients.iterator():
            if _send_once(record.tenant, member.user, f"salary-balance:{record.id}:stage-{stage}", reminder_date,
                "Driver salary remains unpaid", f"₹{remaining:.2f} remains for {record.driver.name} for {record.period_start:%B %Y}.",
                "/fleet/driver-salaries", category="payables", channels=channels):
                salary_balance_count += 1

    return {"trip_review_reminders": review_count, "overdue_follow_up_reminders": follow_up_count,
            "missing_pod_reminders": missing_pod_count, "overdue_invoice_reminders": overdue_invoice_count,
            "salary_balance_reminders": salary_balance_count, "automatic_followups_created": automatic_followups,
            "salary_drafts_auto_prepared": auto_prepared}


@shared_task(bind=True, max_retries=3, acks_late=True, reject_on_worker_lost=True)
def extract_logistics_document(self, record_id):
    from django.db import transaction
    from fleet.models import FleetLogisticsDocument
    from django.conf import settings
    from audit.models import AuditLog
    from accounts.workspace_access import workspace_is_operational
    record = FleetLogisticsDocument.objects.select_related("document").get(pk=record_id)
    if record.status != FleetLogisticsDocument.Status.EXTRACTING:
        return {"status": "IGNORED"}
    if not workspace_is_operational(record.tenant):
        return {"status": "WORKSPACE_UNAVAILABLE"}
    try:
        from admin_console.services import has_feature
        if not has_feature(record.tenant, "ai_extraction"):
            record.status = FleetLogisticsDocument.Status.NEEDS_REVIEW
            record.warnings = ["AI extraction is disabled for this company. Link the source document and review the fields manually."]
            record.save(update_fields=["status", "warnings"])
            return {"status": "NEEDS_REVIEW", "reason": "FEATURE_DISABLED"}
        if settings.EXTRACTION_PROVIDER == "manual":
            record.status = FleetLogisticsDocument.Status.NEEDS_REVIEW
            record.warnings = ["Automatic extraction is disabled. Link the source document to its trip/order and confirm the fields manually."]
            record.save(update_fields=["status", "warnings"])
            return {"status": "NEEDS_REVIEW"}
        from vendors.services import get_extraction_provider
        output = get_extraction_provider().extract_logistics(record.document, record.kind)
        with transaction.atomic():
            record = FleetLogisticsDocument.objects.select_for_update().get(pk=record_id)
            if record.status != FleetLogisticsDocument.Status.EXTRACTING:
                return {"status": "STALE_IGNORED"}
            fields = output.get("fields", {})
            trip = None
            trip_number = str(fields.get("trip_number", "")).strip()
            order_number = str(fields.get("order_number", "")).strip()
            if trip_number:
                from fleet.models import FleetTrip
                trip = FleetTrip.objects.filter(tenant=record.tenant, trip_number__iexact=trip_number).first()
            order = None
            if order_number:
                from fleet.models import TransportOrder
                order = TransportOrder.objects.filter(tenant=record.tenant, order_number__iexact=order_number).first()
            if trip:
                record.trip = trip
                record.transport_order = trip.transport_order
            elif order:
                record.transport_order = order
                record.trip = FleetTrip.objects.filter(tenant=record.tenant, transport_order=order).first()
            record.extracted_fields = fields
            record.confidence = output.get("confidence", {})
            record.warnings = output.get("warnings", [])
            if record.kind == FleetLogisticsDocument.Kind.EWAY_BILL and fields.get("valid_until"):
                from datetime import date
                try:
                    if date.fromisoformat(str(fields["valid_until"])[:10]) < timezone.localdate():
                        record.warnings.append("Extracted validity date appears to be in the past. Verify the original document before dispatch.")
                except ValueError:
                    record.warnings.append("Could not validate the extracted e-way bill expiry date; review it manually.")
            low_confidence = [name for name, value in record.confidence.items() if isinstance(value, (int, float)) and value < 0.7]
            if low_confidence:
                record.warnings.append("Low-confidence fields need review: " + ", ".join(low_confidence[:12]))
            record.status = FleetLogisticsDocument.Status.NEEDS_REVIEW
            record.save(update_fields=["trip", "transport_order", "extracted_fields", "confidence", "warnings", "status"])
        AuditLog.objects.create(tenant=record.tenant, actor=record.document.uploaded_by, action="FLEET_DOCUMENT_EXTRACTED",
            object_type="FleetLogisticsDocument", object_id=str(record.id), metadata={"kind": record.kind,
                "linked_trip": str(record.trip_id) if record.trip_id else None,
                "linked_order": str(record.transport_order_id) if record.transport_order_id else None})
        return {"status": "NEEDS_REVIEW", "document_id": str(record.id)}
    except Exception as error:
        record.status = FleetLogisticsDocument.Status.FAILED
        record.warnings = [str(error)[:300]]
        record.save(update_fields=["status", "warnings"])
        return {"status": "FAILED", "document_id": str(record.id)}


@shared_task
def notify_fleet_eta_risks():
    """Notify workspace dispatch roles when the saved route estimate misses its promised time."""
    from accounts.workspace_access import workspace_is_operational
    now = timezone.now()
    today = timezone.localdate(now)
    count = 0
    trips = FleetTrip.objects.filter(status=FleetTrip.Status.IN_PROGRESS, predicted_arrival_at__isnull=False,
        transport_order__delivery_due_at__isnull=False,
        predicted_arrival_at__gt=F("transport_order__delivery_due_at")).select_related("tenant", "vehicle", "transport_order")
    for trip in trips.iterator(chunk_size=200):
        if not workspace_is_operational(trip.tenant):
            continue
        controls = trip.tenant.settings.get("fleet_controls", {})
        roles = controls.get("recipient_roles", [Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.APPROVER])
        channels = controls.get("channels", ["IN_APP"])
        late_minutes = max(1, int((trip.predicted_arrival_at - trip.transport_order.delivery_due_at).total_seconds() // 60))
        body = (f"Trip {trip.trip_number} ({trip.vehicle.registration_number}) is estimated to arrive about "
            f"{late_minutes} minute(s) after its delivery deadline based on historical route duration. Confirm with the driver.")
        members = Membership.objects.filter(tenant_id=trip.tenant_id, is_active=True, role__in=roles).select_related("user")
        for member in members.iterator():
            if _send_once(trip.tenant, member.user, f"eta-risk:{trip.id}", today,
                "Delivery may miss its deadline", body, "/fleet/live-tracking", channels=channels):
                count += 1
    return {"notifications_created": count}
