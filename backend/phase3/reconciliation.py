"""Deterministic matching evidence and reviewed bank reconciliation. No money moves here."""
import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from audit.models import AuditLog
from tenants.models import Tenant
from payments.models import Payment
from fleet.models import TransportCollection, DriverSalaryPayment
from settlements.models import SourceAccount
from .models import (BankTransaction, ReconciliationRun, ReconciliationCandidate,
    ReconciliationReview, ReconciliationGroup, ReconciliationGroupTarget, ReconciliationGroupBank)
from .services import queue_webhook_event

RULE_VERSION = "bank-exact-v2"
RELATIONS = {"VENDOR_PAYMENT": "payment", "CUSTOMER_COLLECTION": "transport_collection", "DRIVER_SALARY_PAYMENT": "driver_salary_payment"}


class Conflict(APIException):
    status_code = 409
    default_detail = "Records changed. Refresh and review again."


def identifier(value, label="ID"):
    try: return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError): raise ValidationError(f"{label} must be a UUID.") from None


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKC", str(value or "")).casefold() if c.isalnum())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def account_for(row, tenant):
    account = row.statement.source_account
    if (not account or not account.active or account.kind != "BANK" or account.scope != "TENANT"
            or account.tenant_id != tenant.pk or row.statement.currency != account.currency):
        raise Conflict("Verify this statement's active workspace bank account and source currency before matching.")
    return account


def lock_accounts(rows):
    accounts = {item.pk: item for item in SourceAccount.objects.select_for_update().filter(
        pk__in={row.statement.source_account_id for row in rows if row.statement.source_account_id}).order_by("id")}
    for row in rows:
        if row.statement.source_account_id: row.statement.source_account = accounts[row.statement.source_account_id]


def bank_snapshot(row):
    return {"id": str(row.pk), "revision": row.revision, "date": row.transaction_date.isoformat(),
        "amount": str(row.amount), "description": row.description, "reference": row.reference,
        "account_id": str(row.statement.source_account_id), "currency": row.statement.currency,
        "status": row.status, "group_id": str(row.reconciliation_group_id) if row.reconciliation_group_id else None}


def targets(tenant, kind):
    if kind == "VENDOR_PAYMENT": return Payment.objects.filter(tenant=tenant, cancelled_at__isnull=True)
    if kind == "CUSTOMER_COLLECTION": return TransportCollection.objects.filter(tenant=tenant)
    if kind == "DRIVER_SALARY_PAYMENT":
        return DriverSalaryPayment.objects.filter(tenant=tenant, salary_record__tenant=tenant,
            salary_record__status__in=["APPROVED", "PARTIALLY_PAID", "PAID", "SETTLED"]).exclude(reversals__status="APPROVED")
    raise ValidationError("Select a supported internal record type.")


def target_snapshot(kind, item):
    if kind == "VENDOR_PAYMENT":
        ref, day, label = item.reference_number, item.paid_at, item.vendor.name if item.vendor else "Vendor payment"
    elif kind == "CUSTOMER_COLLECTION": ref, day, label = item.reference, item.received_date, item.invoice.customer.name
    else: ref, day, label = item.payment_reference, item.payment_date, item.salary_record.driver.name
    return {"target_type": kind, "target_id": str(item.pk), "amount": str(item.amount), "paid_at": day.isoformat(),
        "payment_reference": ref or "", "vendor": label, "account_id": str(item.source_account_id), "currency": item.currency}


def claimed(tenant, kind, target_id, except_bank=None, except_group=None):
    relation = RELATIONS[kind]
    legacy = BankTransaction.objects.filter(tenant=tenant, **{relation+"_id": target_id}).exclude(status="UNMATCHED")
    if except_bank: legacy = legacy.exclude(pk=except_bank)
    groups = ReconciliationGroupTarget.objects.filter(group__tenant=tenant, active=True, **{relation+"_id": target_id})
    if except_group: groups = groups.exclude(group_id=except_group)
    return legacy.exists() or groups.exists()


def candidate_input(tenant, row):
    account = account_for(row, tenant)
    if row.status != "UNMATCHED" or row.reconciliation_group_id:
        raise Conflict("Suggestions are available only for unmatched bank rows.")
    evidence, limited = [], False
    kinds = ["CUSTOMER_COLLECTION"] if row.amount > 0 else ["VENDOR_PAYMENT", "DRIVER_SALARY_PAYMENT"]
    for kind in kinds:
        relation = RELATIONS[kind]
        blocked = BankTransaction.objects.filter(tenant=tenant, **{relation+"__isnull": False}).exclude(status="UNMATCHED").values_list(relation+"_id", flat=True)
        group_blocked = ReconciliationGroupTarget.objects.filter(group__tenant=tenant, active=True).values_list(relation+"_id", flat=True).exclude(**{relation+"__isnull": True})
        day_field = {"VENDOR_PAYMENT": "paid_at", "CUSTOMER_COLLECTION": "received_date", "DRIVER_SALARY_PAYMENT": "payment_date"}[kind]
        related = {"VENDOR_PAYMENT": "vendor", "CUSTOMER_COLLECTION": "invoice__customer", "DRIVER_SALARY_PAYMENT": "salary_record__driver"}[kind]
        items = list(targets(tenant, kind).filter(source_account=account, currency=account.currency, amount=abs(row.amount),
            **{day_field+"__range": (row.transaction_date-timedelta(days=7), row.transaction_date+timedelta(days=7))})
            .exclude(pk__in=blocked).exclude(pk__in=group_blocked).select_related(related).order_by(day_field, "id")[:101])
        limited = limited or len(items) > 100
        for item in items[:100]:
            snapshot = target_snapshot(kind, item)
            delta = abs((date.fromisoformat(snapshot["paid_at"])-row.transaction_date).days)
            ref = normalize(snapshot["payment_reference"]); bank_ref = normalize(row.reference)
            exact = bool(len(bank_ref) >= 4 and bank_ref == ref)
            # No substring reference matching: overlapping account numbers are not transfer identifiers.
            counterparty = normalize(snapshot["vendor"])
            name_hit = bool(len(counterparty) >= 4 and counterparty in normalize(row.description))
            score = min(100, 50+(30 if delta <= 1 else 20 if delta <= 3 else 10)+(20 if exact else 0)+(10 if name_hit else 0))
            codes = ["SAME_ACCOUNT", "SAME_CURRENCY", "EXACT_AMOUNT", "SAME_DIRECTION", "DATE_WITHIN_7_DAYS"]
            reasons = ["Exact amount", f"Transaction date is {delta} day(s) away"]
            if exact: codes.append("EXACT_NORMALIZED_REFERENCE"); reasons.append("Exact normalized transfer reference")
            if name_hit: codes.append("COUNTERPARTY_IN_NARRATION"); reasons.append("Bank description includes the counterparty")
            evidence.append({**snapshot, "score": score, "confidence": "HIGH" if score >= 80 else "MEDIUM" if score >= 60 else "LOW",
                "reason_codes": codes, "reasons": reasons, "normalized_bank_reference": bank_ref,
                "normalized_target_reference": ref, "exact_reference": exact,
                "payment_id": str(item.pk) if kind == "VENDOR_PAYMENT" else None})
    evidence.sort(key=lambda item: (-int(item["exact_reference"]), -item["score"], item["paid_at"], item["target_type"], item["target_id"]))
    source = bank_snapshot(row)
    return source, evidence, limited, digest({"source": source, "candidates": evidence, "limited": limited})


@transaction.atomic
def suggestions(tenant, bank_id):
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    row = get_object_or_404(BankTransaction.objects.select_related("statement__source_account"), tenant=tenant, pk=identifier(bank_id))
    lock_accounts([row])
    try: source, evidence, limited, fingerprint = candidate_input(tenant, row)
    except Conflict:
        if row.status != "UNMATCHED": raise
        return {"transaction_id": str(row.pk), "suggestions": [], "provenance_required": True}
    # Every equally eligible option remains a human review choice, even when ranked first.
    ambiguous = len(evidence) > 1
    limited = limited or len(evidence) > 20
    run, created = ReconciliationRun.objects.get_or_create(transaction=row, fingerprint=fingerprint, rule_version=RULE_VERSION,
        defaults={"tenant": tenant, "source_snapshot": source, "ambiguous": ambiguous, "candidate_limit_reached": limited})
    if created:
        ReconciliationCandidate.objects.bulk_create([ReconciliationCandidate(run=run, rank=index+1,
            target_type=item["target_type"], target_id=item["target_id"], evidence=item) for index, item in enumerate(evidence[:20])])
    items = list(run.candidates.order_by("rank"))
    rejected = set(ReconciliationReview.objects.filter(tenant=tenant, candidate__in=items, action="REJECT").values_list("candidate_id", flat=True))
    return {"transaction_id": str(row.pk), "run_id": str(run.pk), "rule_version": RULE_VERSION,
        "generated_at": run.created_at.isoformat(),
        "ambiguous": ambiguous, "candidate_limit_reached": limited,
        "suggestions": [{**item.evidence, "candidate_id": str(item.pk), "rejected": item.pk in rejected} for item in items],
        "note": "Rule scores are evidence hints, not probabilities. Explicit matching and confirmation are required."}


def bank_data(row, tenant):
    try: account_for(row, tenant); verified = True
    except Conflict: verified = False
    return {**bank_snapshot(row), "statement": row.statement.filename, "statement_id": str(row.statement_id),
        "is_test_data": row.statement.is_test_data,
        "source_account_id": str(row.statement.source_account_id) if row.statement.source_account_id else None,
        "source_verified": verified, **{relation+"_id": str(getattr(row, relation+"_id")) if getattr(row, relation+"_id") else None for relation in RELATIONS.values()}}


def list_bank(tenant, query):
    base = BankTransaction.objects.filter(tenant=tenant)
    counts = {key: 0 for key, _ in BankTransaction.Status.choices}
    counts.update({row["status"]: row["total"] for row in base.values("status").annotate(total=Count("id"))})
    rows = base
    status = query.get("status", "ALL"); direction = query.get("direction", "ALL")
    if status not in {"ALL", *counts} or direction not in {"ALL", "IN", "OUT"}: raise ValidationError("Invalid status or direction filter.")
    if status != "ALL": rows = rows.filter(status=status)
    if direction != "ALL": rows = rows.filter(amount__gt=0) if direction == "IN" else rows.filter(amount__lt=0)
    if query.get("account_id"): rows = rows.filter(statement__source_account_id=identifier(query["account_id"], "Account"))
    dates = {}
    for key in ("from", "to"):
        if query.get(key):
            try: dates[key] = date.fromisoformat(query[key])
            except (ValueError, TypeError): raise ValidationError("Use ISO dates for date filters.") from None
    if len(dates) == 2 and dates["from"] > dates["to"]: raise ValidationError("End date must follow start date.")
    if "from" in dates: rows = rows.filter(transaction_date__gte=dates["from"])
    if "to" in dates: rows = rows.filter(transaction_date__lte=dates["to"])
    search = query.get("search", "").strip()
    if len(search) > 120: raise ValidationError("Search is limited to 120 characters.")
    if search: rows = rows.filter(Q(description__icontains=search)|Q(reference__icontains=search)|Q(statement__filename__icontains=search))
    if query.get("target_id"):
        kind = query.get("target_type", "VENDOR_PAYMENT")
        if kind not in RELATIONS: raise ValidationError("Invalid target type.")
        target_id = identifier(query["target_id"])
        relation = RELATIONS[kind]
        group_ids = ReconciliationGroupTarget.objects.filter(group__tenant=tenant, active=True, **{relation+"_id": target_id}).values_list("group_id", flat=True)
        rows = rows.filter(Q(**{relation+"_id": target_id})|Q(reconciliation_group_id__in=group_ids))
    if query.get("transaction_id"): rows = rows.filter(pk=identifier(query["transaction_id"]))
    try: page = int(query.get("page", 1)); size = int(query.get("page_size", 25))
    except (ValueError, TypeError): raise ValidationError("Invalid page or page size.") from None
    if page < 1 or size not in {10, 25, 50, 100}: raise ValidationError("Page must be positive; page size is 10, 25, 50 or 100.")
    sort = query.get("sort", "-date")
    sorts = {"date": "transaction_date", "amount": "amount", "description": "description", "reference": "reference", "status": "status"}
    if sort.lstrip("-") not in sorts: raise ValidationError("Invalid sorting column.")
    ordering = ("-" if sort.startswith("-") else "")+sorts[sort.lstrip("-")]
    total = rows.count()
    data = rows.select_related("statement__source_account").order_by(ordering, "id")[(page-1)*size:page*size]
    return {"transactions": [bank_data(row, tenant) for row in data], "count": total, "counts": counts,
        "page": page, "page_size": size, "has_next": page*size < total}


def history(tenant, bank_id, query):
    row = get_object_or_404(BankTransaction, tenant=tenant, pk=identifier(bank_id))
    events = ReconciliationReview.objects.filter(tenant=tenant).filter(Q(transaction=row)|Q(group__bank_members__transaction=row)).distinct()
    try: page = int(query.get("history_page", 1))
    except (TypeError, ValueError): raise ValidationError("Invalid history page.") from None
    if page < 1: raise ValidationError("History page must be positive.")
    count = events.count()
    return {"count": count, "page": page, "events": [{"id": str(item.pk), "action": item.action, "reason": item.reason,
        "actor": item.actor.email if item.actor else "Former user", "at": item.created_at.isoformat(),
        "evidence": item.evidence, "candidate_id": str(item.candidate_id) if item.candidate_id else None}
        for item in events.select_related("actor").order_by("-created_at", "-id")[(page-1)*25:page*25]]}


def request_identity(tenant, data):
    key = identifier(data["request_key"], "Request key") if data.get("request_key") else None
    hashed = digest(dict(data))
    prior = ReconciliationReview.objects.filter(tenant=tenant, request_key=key).first() if key else None
    if prior and prior.request_hash != hashed: raise Conflict("This request key was already used for different evidence.")
    return key, hashed, prior.result if prior else None


def reason_for(data, required=False):
    reason = data.get("reason", "")
    if not isinstance(reason, str) or len(reason.strip()) > 500 or required and not reason.strip():
        raise ValidationError("Provide a review/correction reason of up to 500 characters.")
    return reason.strip() or "Explicit human review of the bank record and internal payment."


def event(tenant, actor, data, action, reason, result, evidence, row=None, group=None, candidate=None):
    key, hashed, _ = request_identity(tenant, data)
    review = ReconciliationReview.objects.create(tenant=tenant, actor=actor, transaction=row, group=group, candidate=candidate,
        action=action, reason=reason, evidence=evidence, result=result, request_key=key, request_hash=hashed)
    AuditLog.objects.create(tenant=tenant, actor=actor, action="BANK_REVIEW_"+action, object_type="ReconciliationReview",
        object_id=str(review.pk), metadata={"transaction_id": str(row.pk) if row else None, "group_id": str(group.pk) if group else None, "reason": reason})


def check_revision(row, data, key="expected_revision"):
    if key in data and (type(data[key]) is not int or data[key] != row.revision): raise Conflict("This record changed after you opened it. Refresh and review again.")


@transaction.atomic
def single_action(tenant, actor, data):
    if not isinstance(data, Mapping): raise ValidationError("Send an object with named fields.")
    Tenant.objects.select_for_update().get(pk=tenant.pk)  # Same lock order as group operations; no remote calls under lock.
    _, _, replay = request_identity(tenant, data)
    if replay is not None: return replay
    row = get_object_or_404(BankTransaction.objects.select_for_update(), tenant=tenant, pk=identifier(data.get("transaction_id"), "Transaction"))
    lock_accounts([row])
    action = data.get("action")
    if not isinstance(action, str) or action not in {"match", "reconcile", "unmatch", "reject_candidate"}: raise ValidationError("Invalid reconciliation action.")
    check_revision(row, data)
    if row.reconciliation_group_id: raise Conflict("Review or clear the complete allocation group instead of changing one bank row.")
    before = bank_snapshot(row)
    reason = reason_for(data, required=action in {"unmatch", "reject_candidate"})
    candidate = None
    if data.get("candidate_id"):
        candidate = get_object_or_404(ReconciliationCandidate.objects.select_related("run"), pk=identifier(data["candidate_id"], "Candidate"), run__tenant=tenant, run__transaction=row)
        _, _, _, current = candidate_input(tenant, row)
        if current != candidate.run.fingerprint or candidate.run.rule_version != RULE_VERSION: raise Conflict("Candidate evidence is stale. Find candidates again.")
    if action == "reject_candidate":
        if not candidate: raise ValidationError("Select a saved candidate to reject.")
        if not data.get("request_key"): raise ValidationError("A stable request key is required for candidate feedback.")
        result = {"id": str(row.pk), "status": row.status, "revision": row.revision, "rejected": str(candidate.pk)}
        event(tenant, actor, data, "REJECT", reason, result, candidate.evidence, row=row, candidate=candidate)
        return result
    if action == "match" and row.status != "UNMATCHED": raise Conflict("Clear the current match before selecting another record.")
    target_kind, target = None, None
    if action in {"match", "reconcile"}:
        account = account_for(row, tenant)
        if action == "reconcile":
            target_kind = next((kind for kind, relation in RELATIONS.items() if getattr(row, relation+"_id")), None)
            target_id = getattr(row, RELATIONS[target_kind]+"_id") if target_kind else None
        else:
            target_kind = data.get("target_type", "VENDOR_PAYMENT" if data.get("payment_id") else "")
            if not isinstance(target_kind, str) or target_kind not in RELATIONS: raise ValidationError("Select a supported transaction type.")
            target_id = data.get("target_id") or data.get("payment_id")
        target_id = identifier(target_id, "Target")
        target = get_object_or_404(targets(tenant, target_kind).select_for_update(of=("self",)), pk=target_id)
        if candidate and (candidate.target_type != target_kind or candidate.target_id != target.pk): raise Conflict("The selected candidate does not describe this target.")
        if candidate and any(candidate.evidence.get(key) != value for key, value in target_snapshot(target_kind, target).items()): raise Conflict("The target evidence changed. Find candidates again.")
        if candidate and candidate.reviews.filter(action="REJECT").exists(): raise Conflict("This candidate was rejected. Review the record manually or regenerate changed evidence.")
        if action == "match" and not candidate and ReconciliationReview.objects.filter(tenant=tenant, transaction=row, action="REJECT",
                candidate__target_type=target_kind, candidate__target_id=target.pk).exists() and not data.get("reason", "").strip():
            raise Conflict("Provide an explicit reason when manually overriding a prior rejection.")
        if target.source_account_id != account.pk or target.currency != account.currency: raise Conflict("Verify both records against the same active bank account and currency.")
        if claimed(tenant, target_kind, target.pk, except_bank=row.pk): raise Conflict("This record is already claimed by another bank row or allocation group.")
        if (row.amount > 0) != (target_kind == "CUSTOMER_COLLECTION") or abs(row.amount) != target.amount: raise Conflict("Amount and transaction direction must agree exactly.")
        if action == "match":
            for relation in RELATIONS.values(): setattr(row, relation, None)
            setattr(row, RELATIONS[target_kind], target); row.status = "MATCHED"
        elif row.status != "MATCHED": raise Conflict("Match the bank transaction before confirming it.")
        else: row.status = "RECONCILED"; row.reconciled_at = timezone.now()
    else:
        for relation in RELATIONS.values(): setattr(row, relation, None)
        row.status = "UNMATCHED"; row.reconciled_at = None
    row.revision += 1; row.reviewed_by = actor; row.save()
    result = {"id": str(row.pk), "status": row.status, "revision": row.revision, "target_type": target_kind,
        "target_id": str(target.pk) if target else None, "payment_id": str(row.payment_id) if row.payment_id else None}
    evidence = {"before": before, "after": bank_snapshot(row)}
    if target: evidence["target"] = target_snapshot(target_kind, target)
    if candidate: evidence["candidate"] = candidate.evidence; evidence["rule_version"] = candidate.run.rule_version
    event(tenant, actor, data, {"match": "ACCEPT", "reconcile": "CONFIRM", "unmatch": "CLEAR"}[action], reason, result, evidence, row=row, candidate=candidate)
    if action == "reconcile": queue_webhook_event(tenant, "bank_transaction.reconciled", {"transaction_id": str(row.pk), "target_type": target_kind, "target_id": str(target.pk), "amount": str(row.amount)})
    return result


def group_data(group):
    return {"id": str(group.pk), "status": group.status, "revision": group.revision, "currency": group.currency,
        "source_account_id": str(group.source_account_id), "reference": group.reference, "evidence": group.evidence}


def validate_group(tenant, banks, target_specs, components, group=None):
    if not banks or len(banks) > 10 or not target_specs or len(target_specs) > 10 or len(banks) > 1 and len(target_specs) > 1:
        raise ValidationError("Choose 1–10 bank rows and 1–10 targets; only one side can contain multiple records.")
    if len(banks) == 1 and len(target_specs) == 1: raise ValidationError("Use the single-record match workflow.")
    # Internal payment amounts already represent cash. Nonzero gateway components need a separate supported settlement path.
    keys = {"fees", "fee_tax", "refunds", "adjustments"}
    if not isinstance(components, dict) or set(components) != keys or any(value != "0.00" for value in components.values()):
        raise ValidationError("Explicit zero fees, fee_tax, refunds and adjustments are required for internal-payment groups. Gateway netting is unsupported.")
    account = account_for(banks[0], tenant)
    positive = banks[0].amount > 0
    reference = normalize(banks[0].reference)
    if len(reference) < 4: raise ValidationError("Groups require an exact shared transfer reference of at least four normalized characters.")
    bank_days = []
    for row in banks:
        if not row.amount or account_for(row, tenant).pk != account.pk or (row.amount > 0) != positive or normalize(row.reference) != reference:
            raise Conflict("All group bank rows need the same account, currency, direction and exact transfer reference.")
        if group:
            if row.reconciliation_group_id != group.pk or row.status != "MATCHED": raise Conflict("Group bank state changed.")
        elif row.status != "UNMATCHED" or row.reconciliation_group_id or any(getattr(row, relation+"_id") for relation in RELATIONS.values()):
            raise Conflict("Every bank row must be unclaimed and unmatched.")
        bank_days.append(row.transaction_date)
    items = []
    seen = set()
    for spec in target_specs:
        if not isinstance(spec, dict): raise ValidationError("Each target needs target_type and target_id.")
        kind = spec.get("target_type")
        if not isinstance(kind, str) or kind not in RELATIONS: raise ValidationError("Invalid group target type.")
        pk = identifier(spec.get("target_id"), "Target")
        if (kind, pk) in seen: raise ValidationError("Repeated target IDs are not allowed.")
        seen.add((kind, pk))
        item = get_object_or_404(targets(tenant, kind).select_for_update(of=("self",)), pk=pk)
        snapshot = target_snapshot(kind, item)
        if item.source_account_id != account.pk or item.currency != account.currency or (kind == "CUSTOMER_COLLECTION") != positive or item.amount <= 0:
            raise Conflict("Group targets must share bank account, currency and direction.")
        if normalize(snapshot["payment_reference"]) != reference or any(abs((date.fromisoformat(snapshot["paid_at"])-day).days) > 7 for day in bank_days):
            raise Conflict("An amount total alone is insufficient: every target needs the same transfer reference and a bank date within seven days.")
        if claimed(tenant, kind, pk, except_group=group.pk if group else None): raise Conflict("A target is already linked to a bank row or another active group.")
        items.append((kind, item, snapshot))
    bank_total = sum((abs(row.amount) for row in banks), Decimal(0))
    target_total = sum((item.amount for _, item, _ in items), Decimal(0))
    if bank_total != target_total: raise Conflict("Group totals must agree exactly; tolerance and implicit adjustments are not supported.")
    return account, items, {"bank_ids": [str(row.pk) for row in banks], "banks": [bank_snapshot(row) for row in banks],
        "targets": [snapshot for _, _, snapshot in items], "bank_total": str(bank_total), "target_total": str(target_total),
        "components": components, "reason_codes": ["SAME_ACCOUNT", "SAME_CURRENCY", "SAME_DIRECTION", "EXACT_GROUP_TOTAL", "EXACT_NORMALIZED_REFERENCE", "DATE_WITHIN_7_DAYS"], "rule_version": RULE_VERSION}


@transaction.atomic
def group_action(tenant, actor, data):
    if not isinstance(data, Mapping): raise ValidationError("Send a named-field object.")
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    if not data.get("request_key"): raise ValidationError("A stable request_key UUID is required for group actions.")
    _, _, replay = request_identity(tenant, data)
    if replay is not None: return replay
    reason = reason_for(data, required=True)
    action = data.get("action")
    if not isinstance(action, str): raise ValidationError("Invalid group action.")
    if action in {"group_match", "group_preview"}:
        ids = data.get("bank_ids"); specs = data.get("targets")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or not isinstance(specs, list) or not 1 <= len(specs) <= 10: raise ValidationError("Choose up to ten bank rows and targets.")
        ids = [identifier(value, "Bank row") for value in ids]
        if len(set(ids)) != len(ids): raise ValidationError("Repeated bank IDs are not allowed.")
        banks = list(BankTransaction.objects.select_for_update().filter(tenant=tenant, pk__in=ids).order_by("id"))
        if len(banks) != len(ids): raise ValidationError("A bank row is unavailable in this workspace.")
        lock_accounts(banks)
        account, items, evidence = validate_group(tenant, banks, specs, data.get("components"))
        evidence_hash = digest(evidence)
        if action == "group_preview": return {"preview": evidence, "evidence_hash": evidence_hash, "currency": account.currency}
        if data.get("expected_evidence_hash") and data["expected_evidence_hash"] != evidence_hash: raise Conflict("Group evidence changed since preview. Preview it again.")
        group = ReconciliationGroup.objects.create(tenant=tenant, source_account=account, currency=account.currency,
            reference=banks[0].reference, evidence=evidence, created_by=actor)
        ReconciliationGroupBank.objects.bulk_create([ReconciliationGroupBank(group=group, transaction=row) for row in banks])
        ReconciliationGroupTarget.objects.bulk_create([ReconciliationGroupTarget(group=group, snapshot=snapshot, **{RELATIONS[kind]: item}) for kind, item, snapshot in items])
        for row in banks:
            row.reconciliation_group = group; row.status = "MATCHED"; row.reviewed_by = actor; row.revision += 1; row.save()
    elif action in {"group_confirm", "group_clear"}:
        group = get_object_or_404(ReconciliationGroup.objects.select_for_update(), tenant=tenant, pk=identifier(data.get("group_id"), "Group"))
        if "expected_revision" not in data: raise ValidationError("Group revision is required.")
        check_revision(group, data)
        banks = list(BankTransaction.objects.select_for_update().filter(tenant=tenant, reconciliation_group=group).order_by("id"))
        lock_accounts(banks)
        if group.status == "CLEARED" or not banks: raise Conflict("This group was already cleared.")
        if action == "group_confirm":
            if group.status != "MATCHED": raise Conflict("Only matched groups can be confirmed.")
            specs = [{"target_type": item.snapshot["target_type"], "target_id": item.snapshot["target_id"]} for item in group.targets.filter(active=True)]
            _, _, current = validate_group(tenant, banks, specs, group.evidence["components"], group=group)
            # Compare all financial/reference fields; revision/status changes from group creation are expected.
            original_banks = [{k:v for k,v in item.items() if k not in {"revision", "status", "group_id"}} for item in group.evidence["banks"]]
            current_banks = [{k:v for k,v in item.items() if k not in {"revision", "status", "group_id"}} for item in current["banks"]]
            if original_banks != current_banks or sorted(group.evidence["targets"], key=lambda x:x["target_id"]) != sorted(current["targets"], key=lambda x:x["target_id"]): raise Conflict("Group evidence changed; clear it and review a new group.")
            group.status = "RECONCILED"
            for row in banks: row.status = "RECONCILED"; row.reconciled_at = timezone.now()
        else:
            group.status = "CLEARED"
            group.targets.filter(active=True).update(active=False)
            for row in banks: row.status = "UNMATCHED"; row.reconciliation_group = None; row.reconciled_at = None
        group.revision += 1; group.save(update_fields=["status", "revision"])
        for row in banks: row.reviewed_by = actor; row.revision += 1; row.save()
    else: raise ValidationError("Invalid group action.")
    result = group_data(group)
    event(tenant, actor, data, str(action).upper(), reason, result, {"group": result}, group=group)
    if action == "group_confirm":
        for row in banks: queue_webhook_event(tenant, "bank_transaction.reconciled", {"transaction_id": str(row.pk), "group_id": str(group.pk), "amount": str(row.amount)})
    return result
