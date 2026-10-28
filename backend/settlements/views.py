import uuid
from collections.abc import Mapping
from django.db import IntegrityError, transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework import serializers
from accounts.permissions import HasTenantMembership
from admin_console.permissions import IsAdminStaff
from .models import SourceAccount, ImportBatch, SettlementRecord
from .services import stage, review, audit


class AccountInput(serializers.ModelSerializer):
    class Meta:
        model = SourceAccount
        fields = ["name", "kind", "provider", "external_reference", "currency"]
        validators = []

    def validate(self, data):
        if (data["kind"] == "BANK") != (data["provider"] == "BANK"):
            raise ValidationError("Bank accounts use provider BANK; gateway accounts use RAZORPAY or OTHER.")
        return data


class Pages(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def page(request, queryset, payload):
    paginator = Pages()
    rows = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response([payload(row) for row in rows])


def account_data(row):
    return {"id": str(row.pk), "name": row.name, "scope": row.scope, "kind": row.kind,
            "provider": row.provider, "external_reference": row.external_reference, "currency": row.currency,
            "active": row.active, "live_sync_enabled": False}


def batch_data(row):
    return {"id": str(row.pk), "account_id": str(row.account_id), "filename": row.filename, "status": row.status,
            "row_count": row.row_count, "errors": row.errors, "warnings": row.warnings,
            "created_at": row.created_at, "reviewed_at": row.reviewed_at, "review_note": row.review_note,
            "source_sha256": row.content_hash}


class ScopedAPI(APIView):
    permission_classes = [HasTenantMembership]
    platform = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method in {"POST", "PATCH"} and not isinstance(request.data, Mapping):
            raise ValidationError("Send an object with named fields.")
        if not self.platform:
            membership = request.membership
            readers = {"OWNER", "FINANCE", "AUDITOR"}
            if membership.role not in readers or membership.branch_scope_enabled:
                raise PermissionDenied("Workspace-wide finance access is required.")
            if request.method not in {"GET", "HEAD", "OPTIONS"} and membership.role not in {"OWNER", "FINANCE"}:
                raise PermissionDenied("Finance write access is required.")

    def accounts(self, request):
        return SourceAccount.objects.filter(scope="PLATFORM", tenant__isnull=True) if self.platform else SourceAccount.objects.filter(
            scope="TENANT", tenant=request.tenant)

    def account(self, request, account_id, active=False):
        try: account_id = uuid.UUID(str(account_id))
        except (ValueError, TypeError): raise ValidationError("Select a source account UUID.") from None
        rows = self.accounts(request)
        if active:
            rows = rows.filter(active=True)
        return get_object_or_404(rows, pk=account_id)

    def batch(self, request, batch_id):
        return get_object_or_404(ImportBatch.objects.select_related("account").filter(account__in=self.accounts(request)), pk=batch_id)


class Accounts(ScopedAPI):
    def get(self, request):
        return Response({"accounts": [account_data(row) for row in self.accounts(request).order_by("name")[:200]],
                         "note": "Import-only source accounts. Live provider APIs and credential fallback are disabled."})

    def post(self, request):
        if set(request.data) - {"name", "kind", "provider", "external_reference", "currency"}:
            raise ValidationError("Use only the documented account fields; ownership is assigned by the server.")
        serializer = AccountInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                row = SourceAccount.objects.create(**serializer.validated_data, scope="PLATFORM" if self.platform else "TENANT",
                    tenant=None if self.platform else request.tenant, created_by=request.user)
                audit(row, request.user, "SOURCE_ACCOUNT_CREATED", row.pk)
        except IntegrityError:
            return Response({"error": "This source account already exists in this ownership scope."}, status=409)
        return Response(account_data(row), status=201)


class AccountState(ScopedAPI):
    def patch(self, request, account_id):
        if set(request.data) != {"active"} or not isinstance(request.data["active"], bool):
            raise ValidationError("Only an explicit boolean active state can be changed; source identity is immutable.")
        with transaction.atomic():
            row = self.account(request, account_id)
            row = SourceAccount.objects.select_for_update().get(pk=row.pk)
            row.active = request.data["active"]
            row.save(update_fields=["active"])
            audit(row, request.user, "SOURCE_ACCOUNT_STATE_CHANGED", row.pk, {"active": row.active})
        return Response(account_data(row))


class Imports(ScopedAPI):
    def get(self, request):
        rows = ImportBatch.objects.filter(account__in=self.accounts(request)).order_by("-created_at")
        if request.query_params.get("account_id"):
            rows = rows.filter(account=self.account(request, request.query_params["account_id"]))
        return page(request, rows, batch_data)

    def post(self, request):
        try:
            account_id = uuid.UUID(str(request.data.get("account_id")))
        except (ValueError, TypeError):
            raise ValidationError({"account_id": "Select a source account UUID."}) from None
        account = self.account(request, account_id, active=True)
        if account.kind != "GATEWAY":
            raise ValidationError("Settlement reports require a gateway account, not a bank account.")
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Choose a CSV or XLSX report."})
        try:
            batch, created = stage(account, upload, request.user)
        except SourceAccount.DoesNotExist:
            return Response({"error": "The account was disabled while uploading."}, status=409)
        return Response({**batch_data(batch), "duplicate_import": not created}, status=201 if created else 200)


class ImportDetail(ScopedAPI):
    def get(self, request, batch_id):
        batch = self.batch(request, batch_id)
        if request.query_params.get("rows") == "1":
            return page(request, batch.rows.order_by("row_number"), lambda row: {
                "row_number": row.row_number, "data": row.normalized, "fingerprint": row.fingerprint})
        return Response(batch_data(batch))

    def post(self, request, batch_id):
        batch = self.batch(request, batch_id)
        result = review(batch, request.user, request.data.get("decision"), request.data.get("note"),
                        request.data.get("acknowledge_warnings", False))
        return Response(batch_data(result))


class ImportSource(ScopedAPI):
    def get(self, request, batch_id):
        batch = self.batch(request, batch_id)
        try:
            file = batch.original_file.open("rb")
        except (FileNotFoundError, OSError):
            return Response({"error": "Source file is unavailable. Contact the operator; observations were preserved."}, status=404)
        return FileResponse(file, as_attachment=True, filename=batch.filename, content_type="application/octet-stream")


class Records(ScopedAPI):
    def get(self, request):
        rows = SettlementRecord.objects.filter(account__in=self.accounts(request)).select_related("source_row__batch").order_by("-created_at")
        if request.query_params.get("account_id"):
            rows = rows.filter(account=self.account(request, request.query_params["account_id"]))
        fields = ["id", "account_id", "record_type", "external_id", "currency", "settlement_reference", "payment_reference",
                  "gross", "fees", "fee_tax", "refunds", "adjustments", "net", "amount", "expected_date", "settled_date", "reverses_id"]
        return page(request, rows, lambda row: {**{key: (str(getattr(row, key)) if getattr(row, key) is not None and key in {"gross", "fees", "fee_tax", "refunds", "adjustments", "net", "amount"} else getattr(row, key)) for key in fields},
            "source_batch_id": str(row.source_row.batch_id), "source_row_number": row.source_row.row_number,
            "note": "Approved source observation; not a bank-confirmed settlement."})


class Template(ScopedAPI):
    def get(self, request):
        body = ("record_type,external_id,currency,gross,fees,fee_tax,refunds,adjustments,net,amount,settlement_reference,payment_reference,expected_date,settled_date,reverses_type,reverses_id\n")
        result = HttpResponse(body, content_type="text/csv")
        result["Content-Disposition"] = 'attachment; filename="settlement-template.csv"'
        return result


class Provenance(ScopedAPI):
    @transaction.atomic
    def post(self, request):
        if self.platform:
            raise PermissionDenied("Workspace operational records cannot be assigned platform accounts.")
        from phase3.models import BankStatement, BankTransaction
        from payments.models import Payment
        from fleet.models import TransportCollection, DriverSalaryPayment
        models = {"BANK_STATEMENT": BankStatement, "VENDOR_PAYMENT": Payment,
                  "CUSTOMER_COLLECTION": TransportCollection, "DRIVER_SALARY_PAYMENT": DriverSalaryPayment}
        kind = request.data.get("record_type")
        if not isinstance(kind, str) or kind not in models:
            raise ValidationError("Choose a supported operational record type.")
        try:
            account_id = uuid.UUID(str(request.data.get("account_id")))
            record_id = uuid.UUID(str(request.data.get("record_id")))
        except (ValueError, TypeError):
            raise ValidationError("Select valid account and record UUIDs.") from None
        account = self.account(request, account_id)
        account = get_object_or_404(SourceAccount.objects.select_for_update(), pk=account.pk, active=True)
        if account.kind != "BANK":
            raise ValidationError("Operational payments/statements require a bank source account.")
        if kind != "BANK_STATEMENT" and account.currency != "INR":
            raise ValidationError("The existing operational ledger supports INR only. No implicit FX conversion is permitted.")
        evidence = str(request.data.get("evidence", "")).strip()
        if not evidence or len(evidence) > 500:
            raise ValidationError("Describe the source evidence in up to 500 characters.")
        row = get_object_or_404(models[kind].objects.select_for_update(), tenant=request.tenant, pk=record_id)
        if row.source_account_id:
            if row.source_account_id != account.pk or row.currency != account.currency:
                return Response({"error": "Verified provenance is immutable; investigate a correction instead of overwriting it."}, status=409)
            return Response({"id": str(row.pk), "verified": True})
        relation = {"BANK_STATEMENT": "statement", "VENDOR_PAYMENT": "payment",
                    "CUSTOMER_COLLECTION": "transport_collection", "DRIVER_SALARY_PAYMENT": "driver_salary_payment"}[kind]
        if BankTransaction.objects.filter(tenant=request.tenant, **{relation: row}).exclude(status__in=["UNMATCHED", "DUPLICATE"]).exists():
            raise ValidationError("Explicitly unmatch linked bank rows before verifying previously unknown provenance.")
        row.source_account = account
        row.currency = account.currency
        row.provenance_note = evidence
        row.save(update_fields=["source_account", "currency", "provenance_note"])
        audit(account, request.user, "SOURCE_PROVENANCE_VERIFIED", row.pk, {"record_type": kind, "account_id": str(account.pk), "evidence": evidence})
        return Response({"id": str(row.pk), "verified": True})


class PlatformScope(ScopedAPI):
    platform = True
    permission_classes = [IsAdminStaff]
    allowed_roles = ["SUPER_ADMIN", "BILLING_ADMIN"]


class PlatformAccounts(Accounts, PlatformScope): pass
class PlatformAccountState(AccountState, PlatformScope): pass
class PlatformImports(Imports, PlatformScope): pass
class PlatformImportDetail(ImportDetail, PlatformScope): pass
class PlatformImportSource(ImportSource, PlatformScope): pass
class PlatformRecords(Records, PlatformScope): pass
class PlatformTemplate(Template, PlatformScope): pass
