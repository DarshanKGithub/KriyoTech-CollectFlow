import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Sum, Prefetch
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.db.models import Q
from accounts.models import Membership, Invitation, User, BranchMembership
from accounts.permissions import HasTenantMembership
from tenants.models import Tenant, Branch
from documents.models import Document
from audit.models import AuditLog
from matching.services import run_matching
from approvals.models import Approval, ApprovalRule, ApprovalStep, ApprovalDelegation, AutoApprovalRule
from exceptions_app.models import InvoiceException
from exports_app.services import create_tally_csv
from procurement.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderRevision, GRN, GRNLine
from procurement.services import receipt_balance, record_purchase_order_revision
from matching.models import MatchingSetting
from vendors.models import Vendor
from .models import Invoice, DuplicateCheck, ExtractionResult
from .serializers import InvoiceSerializer
from .extraction import queue_invoice_extraction
from .policies import ensure_invoice_editable
from phase3.services import queue_webhook_event

def role_allowed(request, *roles):
    return getattr(getattr(request, "membership", None), "role", None) in roles

class Me(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        from admin_console.services import entitlements_for
        return Response({"id": str(request.user.id), "email": request.user.email, "name": request.user.get_full_name(), "tenant": request.tenant.name, "workspace_key": request.tenant.workspace_key, "role": request.membership.role,
                         "entitlements": entitlements_for(request.tenant)})

class MyWorkspaces(APIView):
    """Workspace memberships available to the signed-in user; no tenant selection required."""
    permission_classes = [IsAuthenticated]
    def get(self, request):
        memberships = Membership.objects.filter(user=request.user, is_active=True, tenant__is_deleted=False).select_related("tenant").order_by("tenant__name")
        return Response([{"tenant_id": str(m.tenant_id), "tenant": m.tenant.name, "workspace_key": m.tenant.workspace_key, "role": m.role} for m in memberships])

class Branches(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        branches = Branch.objects.filter(tenant=request.tenant).order_by("name")
        if request.membership.branch_scope_enabled:
            assigned_ids = BranchMembership.objects.filter(membership=request.membership, is_active=True,
                branch__active=True).values_list("branch_id", flat=True)
            branches = branches.filter(id__in=assigned_ids)
            return Response({"branches": [{"id": str(branch.id), "name": branch.name, "code": branch.code,
                "active": branch.active, "is_default": branch.is_default, "members": []} for branch in branches]})
        assignments = BranchMembership.objects.filter(membership__tenant=request.tenant, is_active=True).select_related("membership__user", "branch")
        assigned = {}
        for row in assignments:
            assigned.setdefault(str(row.branch_id), []).append({"membership_id": str(row.membership_id), "user_id": str(row.membership.user_id), "email": row.membership.user.email, "role": row.membership.role})
        return Response({"branches": [{"id": str(branch.id), "name": branch.name, "code": branch.code, "active": branch.active, "is_default": branch.is_default, "members": assigned.get(str(branch.id), [])} for branch in branches]})

    def post(self, request):
        if request.membership.role != Membership.Role.OWNER:
            return Response({"error": "Owner role required to manage branches"}, status=403)
        from django.utils.text import slugify
        name = str(request.data.get("name", "")).strip()
        code = slugify(request.data.get("code") or name)
        if not name or len(name) > 120 or not code or len(code) > 80:
            return Response({"error": "A branch name and valid code are required"}, status=400)
        if Branch.objects.filter(tenant=request.tenant, code=code).exists():
            return Response({"error": "A branch with this code already exists"}, status=409)
        branch = Branch.objects.create(tenant=request.tenant, name=name, code=code)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="BRANCH_CREATED", object_type="Branch", object_id=str(branch.id), metadata={"name": name, "code": code})
        return Response({"id": str(branch.id), "name": branch.name, "code": branch.code, "active": branch.active, "is_default": branch.is_default, "members": []}, status=201)

    def patch(self, request, branch_id=None):
        if request.membership.role != Membership.Role.OWNER:
            return Response({"error": "Owner role required to manage branches"}, status=403)
        branch = Branch.objects.filter(tenant=request.tenant, id=branch_id).first()
        if not branch: return Response({"error": "Branch not found"}, status=404)
        if set(request.data) - {"name", "active"}: return Response({"error": "Only branch name and active state can be changed"}, status=400)
        if "name" in request.data:
            name = str(request.data["name"]).strip()
            if not name or len(name) > 120: return Response({"error": "Branch name must be 1 to 120 characters"}, status=400)
            branch.name = name
        if "active" in request.data:
            if not isinstance(request.data["active"], bool): return Response({"error": "active must be true or false"}, status=400)
            if branch.is_default and not request.data["active"]: return Response({"error": "The default branch cannot be deactivated"}, status=409)
            branch.active = request.data["active"]
        branch.save(update_fields=["name", "active"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="BRANCH_UPDATED", object_type="Branch", object_id=str(branch.id), metadata={"name": branch.name, "active": branch.active})
        return Response({"id": str(branch.id), "name": branch.name, "code": branch.code, "active": branch.active, "is_default": branch.is_default})


class BranchAssignments(APIView):
    permission_classes = [HasTenantMembership]

    def post(self, request):
        if request.membership.role != Membership.Role.OWNER:
            return Response({"error": "Owner role required to assign branches"}, status=403)
        membership = Membership.objects.filter(tenant=request.tenant, id=request.data.get("membership_id"), is_active=True).first()
        branch = Branch.objects.filter(tenant=request.tenant, id=request.data.get("branch_id"), active=True).first()
        if not membership or not branch: return Response({"error": "Choose an active workspace member and branch"}, status=404)
        action = request.data.get("action", "assign")
        if action == "assign":
            assignment, created = BranchMembership.objects.get_or_create(membership=membership, branch=branch, defaults={"is_active": True})
            if not created and not assignment.is_active:
                assignment.is_active = True; assignment.save(update_fields=["is_active"])
            verb = "BRANCH_MEMBER_ASSIGNED"
        elif action == "unassign":
            assignment = BranchMembership.objects.filter(membership=membership, branch=branch).first()
            if assignment:
                assignment.is_active = False; assignment.save(update_fields=["is_active"])
            verb = "BRANCH_MEMBER_UNASSIGNED"
        else: return Response({"error": "action must be assign or unassign"}, status=400)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=verb, object_type="Membership", object_id=str(membership.id), metadata={"branch_id": str(branch.id), "email": membership.user.email})
        return Response({"membership_id": str(membership.id), "branch_id": str(branch.id), "assigned": action == "assign"})

class TenantSettings(APIView):
    permission_classes = [HasTenantMembership]
    allowed_keys = {"rate_tolerance_percent", "tax_tolerance_percent", "automatic_invoice_workflow_enabled"}
    def get(self, request):
        return Response({**{key: request.tenant.settings.get(key, 0) for key in sorted(self.allowed_keys)}, "extraction_provider": settings.EXTRACTION_PROVIDER, "automatic_extraction_enabled": settings.EXTRACTION_PROVIDER != "manual", "automatic_invoice_workflow_enabled": request.tenant.settings.get("automatic_invoice_workflow_enabled", True)})
    def patch(self, request):
        if request.membership.role not in ("OWNER", "FINANCE"):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Owner or finance role required"}}, status=403)
        if not request.data or set(request.data.keys()) - self.allowed_keys:
            return Response({"error": {"code": "VALIDATION_ERROR", "message": "Only matching tolerances and the automatic workflow setting can be updated"}}, status=400)
        updated = dict(request.tenant.settings)
        for key, value in request.data.items():
            if key == "automatic_invoice_workflow_enabled":
                if not isinstance(value, bool): return Response({"error": {"message": "Automatic workflow setting must be true or false."}}, status=400)
                updated[key] = value
                continue
            try: number = float(value)
            except (TypeError, ValueError): return Response({"error": {"code": "VALIDATION_ERROR", "message": f"{key} must be a number"}}, status=400)
            if number < 0 or number > 100: return Response({"error": {"code": "VALIDATION_ERROR", "message": f"{key} must be between 0 and 100"}}, status=400)
            updated[key] = number
        request.tenant.settings = updated
        request.tenant.save(update_fields=["settings"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WORKSPACE_SETTINGS_UPDATED", object_type="Tenant", object_id=str(request.tenant.id), metadata={key: updated[key] for key in request.data.keys()})
        return Response({key: updated.get(key, 0) for key in sorted(self.allowed_keys)})

class InviteUser(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request):
        if request.membership.role != "OWNER": return Response({"error": {"code": "PERMISSION_DENIED", "message": "Owner role required"}}, status=403)
        email, role = request.data.get("email", "").strip().lower(), request.data.get("role")
        if not email or role not in Membership.Role.values: return Response({"error": {"code": "VALIDATION_ERROR", "message": "Valid email and role are required"}}, status=400)
        if Membership.objects.filter(tenant=request.tenant, user__email=email).exists(): return Response({"error": {"code": "STATE_CONFLICT", "message": "User is already a member"}}, status=409)
        from admin_console.models import Subscription
        subscription = request.tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        if subscription and subscription.plan.user_limit is not None:
            active_members = Membership.objects.filter(tenant=request.tenant, is_active=True).count()
            pending_invites = Invitation.objects.filter(tenant=request.tenant, accepted_at__isnull=True, expires_at__gt=timezone.now()).count()
            if active_members + pending_invites >= subscription.plan.user_limit:
                return Response({"error": {"code": "USER_LIMIT_REACHED", "message": "Your plan's active user limit has been reached."}}, status=403)
        token = secrets.token_urlsafe(32)
        invitation = Invitation.objects.create(tenant=request.tenant, email=email, role=role, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now()+timedelta(days=7), invited_by=request.user)
        from partners.services import frontend_link, branding
        accept_url = frontend_link("/invite/accept", {"token": token})
        send_mail(f"Invitation to {request.tenant.name}", f"Join your {branding()['product_name']} workspace: {accept_url}", None, [email], fail_silently=True)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="USER_INVITED", object_type="Invitation", object_id=str(invitation.id), metadata={"email": email, "role": role})
        return Response({"id": str(invitation.id), "email": email, "role": role, "expires_at": invitation.expires_at}, status=201)

class AcceptInvitation(APIView):
    permission_classes = []
    @transaction.atomic
    def post(self, request):
        token = request.data.get("token", "")
        invitation = Invitation.objects.select_for_update().select_related("tenant").filter(token_hash=hashlib.sha256(token.encode()).hexdigest(), accepted_at__isnull=True, expires_at__gt=timezone.now()).first()
        if not invitation: return Response({"error": {"code": "NOT_FOUND", "message": "Invitation is invalid or expired"}}, status=404)
        Tenant.objects.select_for_update().get(pk=invitation.tenant_id)
        password = request.data.get("password", "")
        if len(password) < 10: return Response({"error": {"code": "VALIDATION_ERROR", "message": "Password must contain at least 10 characters"}}, status=400)
        user = User.objects.filter(email__iexact=invitation.email).first()
        if user:
            if not user.has_usable_password(): user.set_password(password); user.save()
        else:
            user = User.objects.create_user(username=invitation.email, email=invitation.email, password=password, first_name=request.data.get("name", ""))
        membership, created = Membership.objects.get_or_create(tenant=invitation.tenant, user=user, defaults={"role": invitation.role})
        if not created and (membership.role != invitation.role or not membership.is_active):
            if membership.is_active and membership.role == Membership.Role.OWNER and invitation.role != Membership.Role.OWNER and not Membership.objects.filter(tenant=invitation.tenant, is_active=True, role=Membership.Role.OWNER).exclude(pk=membership.pk).exists():
                return Response({"error": {"code": "LAST_OWNER", "message": "A workspace must have at least one active owner."}}, status=409)
            membership.role = invitation.role; membership.is_active = True; membership.save(update_fields=["role", "is_active"])
        invitation.accepted_at = timezone.now(); invitation.save(update_fields=["accepted_at"])
        AuditLog.objects.create(tenant=invitation.tenant, actor=user, action="INVITATION_ACCEPTED", object_type="Invitation", object_id=str(invitation.id), metadata={})
        return Response({"detail": "Invitation accepted. Sign in to continue."}, status=201)

class UserList(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        return Response([{"id": str(m.user_id), "membership_id": str(m.id), "email": m.user.email, "name": m.user.get_full_name(), "role": m.role, "is_active": m.is_active} for m in Membership.objects.filter(tenant=request.tenant).select_related("user")])
    def patch(self, request, user_id):
        if request.membership.role != "OWNER": return Response({"error": {"code": "PERMISSION_DENIED", "message": "Owner role required"}}, status=403)
        from django.db import transaction
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=request.tenant.pk)
            member = get_object_or_404(Membership.objects.select_for_update(), tenant=request.tenant, user_id=user_id)
            role = request.data.get("role")
            if role not in Membership.Role.values: return Response({"error": {"code": "VALIDATION_ERROR", "message": "Invalid role"}}, status=400)
            if member.is_active and member.role == Membership.Role.OWNER and role != Membership.Role.OWNER:
                other_owners = Membership.objects.filter(tenant=request.tenant, is_active=True, role=Membership.Role.OWNER).exclude(pk=member.pk).count()
                if other_owners == 0:
                    return Response({"error": {"code": "LAST_OWNER", "message": "A workspace must have at least one active owner."}}, status=409)
            old_role = member.role; member.role = role; member.save(update_fields=["role"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="ROLE_CHANGED", object_type="Membership", object_id=str(member.id), metadata={"from": old_role, "to": role})
        return Response({"id": str(member.user_id), "role": role})

class InvoicePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 50


class InvoiceViewSet(viewsets.ModelViewSet):
    pagination_class = InvoicePagination
    serializer_class = InvoiceSerializer
    permission_classes = [HasTenantMembership]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = {"status": ["exact", "in"], "vendor_id": ["exact"], "payment_status": ["exact", "in"]}
    ordering_fields = ["invoice_date", "invoice_total", "created_at"]
    def get_queryset(self):
        rows = Invoice.objects.filter(tenant=self.request.tenant).select_related("vendor", "document").prefetch_related("lines", "exceptions").order_by("-created_at", "-id")
        if self.action == "list" and self.request.query_params.get("payment_queue") == "1":
            from payments.services import with_invoice_balances
            rows = with_invoice_balances(rows).filter(outstanding_balance__gt=0)
        if self.action in {"list", "retrieve"}:
            rows = rows.prefetch_related(Prefetch(
                "extractions",
                queryset=ExtractionResult.objects.filter(tenant=self.request.tenant).only(
                    "invoice_id", "confidence", "status", "output", "created_at"
                ).order_by("-created_at", "-id")[:1],
                to_attr="_latest_extractions",
            ))
        search = self.request.query_params.get("search", "").strip()[:200]
        if search:
            rows = rows.filter(Q(invoice_number__icontains=search) | Q(supplier_name__icontains=search) | Q(vendor__name__icontains=search) | Q(po_number__icontains=search))
        return rows
    def perform_create(self, serializer):
        invoice = serializer.save()
        queue_invoice_extraction(invoice, self.request.user)
        queue_webhook_event(invoice.tenant, "invoice.created", {"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number, "invoice_total": str(invoice.invoice_total)})
    @action(detail=True, methods=["post"], url_path="resume-automation")
    def resume_automation(self, request, pk=None):
        if not role_allowed(request, "OWNER", "FINANCE"):
            return Response({"error": {"message": "Finance role required"}}, status=403)
        from invoices.automation import queue_invoice_workflow
        invoice = self.get_object()
        ensure_invoice_editable(invoice)
        queue_invoice_workflow(invoice, request.user, reviewed=(invoice.automation.get("reviewed") is True and invoice.automation.get("version") == invoice.version))
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="resolve-missing-supplier")
    def resolve_missing_supplier(self, request, pk=None):
        if not role_allowed(request, "OWNER", "FINANCE"):
            return Response({"error": {"message": "Finance role required"}}, status=403)
        reason = str(request.data.get("reason", "")).strip()
        if len(reason) < 8:
            return Response({"error": {"message": "Explain this supplier correction in at least 8 characters."}}, status=400)
        from uuid import UUID
        try:
            vendor_id = UUID(str(request.data.get("vendor", "")))
        except (ValueError, TypeError):
            return Response({"error": {"message": "Choose a supplier from this workspace."}}, status=400)
        with transaction.atomic():
            invoice = get_object_or_404(Invoice.objects.select_for_update(of=("self",)), tenant=request.tenant, pk=pk)
            vendor = get_object_or_404(Vendor, tenant=request.tenant, pk=vendor_id)
            if invoice.vendor_id:
                return Response({"error": {"message": "A supplier is already linked. Refresh the invoice."}}, status=409)
            if invoice.status not in {Invoice.Status.REVIEW_REQUIRED, Invoice.Status.EXCEPTION, Invoice.Status.MATCHED, Invoice.Status.APPROVAL_PENDING, Invoice.Status.APPROVED, Invoice.Status.PAYMENT_READY} or invoice.payment_status != "UNPAID" or invoice.payment_allocations.exists():
                return Response({"error": {"message": "Only unpaid, unexported invoices without payment allocations can use this correction."}}, status=409)
            previous_status = invoice.status
            previous_version = invoice.version
            invoice.vendor = vendor
            invoice.vendor_match_method = "MANUAL_REVIEW"
            invoice.vendor_match_confidence = None
            invoice.status = Invoice.Status.REVIEW_REQUIRED
            invoice.financial_locked_at = None
            invoice.version += 1
            invoice.save(update_fields=["vendor", "vendor_match_method", "vendor_match_confidence", "status", "financial_locked_at", "version", "updated_at"])
            invoice.approval_steps.filter(status="PENDING").update(status="SKIPPED", comments="Superseded by audited missing-supplier correction", decided_at=timezone.now())
            from invoices.automation import _state
            _state(invoice, "NEEDS_ATTENTION", "Supplier corrected. Review the invoice fields to restart automatic matching and approval.", version=invoice.version, reviewed=False, recheck_after=None)
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="INVOICE_MISSING_SUPPLIER_CORRECTED", object_type="Invoice", object_id=str(invoice.id), metadata={"vendor_id": str(vendor.id), "reason": reason[:500], "previous_status": previous_status, "previous_version": previous_version, "version": invoice.version, "requires_reapproval": True})
        return Response(InvoiceSerializer(invoice, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="extract")
    def extract(self, request, pk=None):
        if not role_allowed(request, "OWNER", "FINANCE"):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        invoice = self.get_object()
        ensure_invoice_editable(invoice)
        if not invoice.document_id:
            return Response({"error": {"code": "STATE_CONFLICT", "message": "This invoice has no source document"}}, status=409)
        if settings.EXTRACTION_PROVIDER == "manual":
            return Response({"error": {"code": "STATE_CONFLICT", "message": "Automatic extraction is not configured. Review invoice fields manually."}}, status=409)
        if invoice.status == Invoice.Status.EXTRACTING:
            return Response({"status": invoice.status}, status=202)
        queued = queue_invoice_extraction(invoice, request.user)
        if not queued:
            return Response({"error": {"code": "STATE_CONFLICT", "message": "Automatic extraction is not configured. Review invoice fields manually."}}, status=409)
        return Response({"status": invoice.status, "provider": settings.EXTRACTION_PROVIDER}, status=202)
    @action(detail=True, methods=["get"], url_path="source")
    def source(self, request, pk=None):
        invoice = self.get_object()
        if not invoice.document_id or invoice.document.tenant_id != request.tenant.pk or not invoice.document.file:
            return Response({"error": {"code": "NOT_FOUND", "message": "Source document is not available"}}, status=404)
        try:
            source = invoice.document.file.open("rb")
        except FileNotFoundError:
            return Response({"error": {"code": "NOT_FOUND", "message": "Source document is not available"}}, status=404)
        return FileResponse(source, as_attachment=False, filename=invoice.document.filename, content_type=invoice.document.media_type)
    def create(self, request, *args, **kwargs):
        if not role_allowed(request, "OWNER", "FINANCE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        if request.FILES.get("file"):
            file = request.FILES["file"]
            if file.size > 25 * 1024 * 1024: return Response({"error": {"code": "VALIDATION_ERROR", "message": "File exceeds 25 MB"}}, status=400)
            allowed = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif"}
            if file.content_type not in allowed: return Response({"error": {"code": "VALIDATION_ERROR", "message": "Upload a PDF, JPG, PNG, or HEIC invoice"}}, status=400)
            digest = hashlib.sha256(file.read()).hexdigest(); file.seek(0)
            with transaction.atomic():
                candidate_document = Document.objects.filter(tenant=request.tenant, checksum_sha256=digest).exclude(checksum_sha256="").order_by("created_at").first()
                candidate = Invoice.objects.filter(tenant=request.tenant, document=candidate_document).first() if candidate_document else None
                duplicate = candidate is not None
                doc = Document.objects.create(tenant=request.tenant, filename=file.name, media_type=file.content_type, checksum_sha256=digest, size_bytes=file.size, uploaded_by=request.user, file=file)
                invoice = Invoice.objects.create(tenant=request.tenant, document=doc, uploaded_by=request.user, status=Invoice.Status.REVIEW_REQUIRED)
                queue_webhook_event(request.tenant, "invoice.created", {"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number, "invoice_total": str(invoice.invoice_total)})
                AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="INVOICE_UPLOADED", object_type="Invoice", object_id=str(invoice.id), metadata={"checksum": digest, "duplicate_candidate": duplicate})
                if duplicate:
                    DuplicateCheck.objects.create(tenant=request.tenant, invoice=invoice, candidate_invoice=candidate, kind=DuplicateCheck.Kind.FILE, score=1, reasons=["Identical SHA-256 document checksum"])
                    InvoiceException.objects.create(tenant=request.tenant, invoice=invoice, code="DUPLICATE_INVOICE", details={"checksum": digest})
                    invoice.status = Invoice.Status.EXCEPTION; invoice.save(update_fields=["status", "updated_at"])
                queue_invoice_extraction(invoice, request.user)
            return Response(InvoiceSerializer(invoice, context={"request": request}).data, status=201)
        return super().create(request, *args, **kwargs)
    def update(self, request, *args, **kwargs):
        if not role_allowed(request, "OWNER", "FINANCE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        return super().update(request, *args, **kwargs)
    def partial_update(self, request, *args, **kwargs):
        if not role_allowed(request, "OWNER", "FINANCE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        return super().partial_update(request, *args, **kwargs)
    def perform_update(self, serializer):
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=serializer.instance.pk, tenant=self.request.tenant)
            ensure_invoice_editable(invoice)
            if invoice.status == Invoice.Status.EXTRACTING:
                raise ValidationError({"detail": "Extraction is running. Wait for it to finish before editing invoice fields."})
            serializer.instance = invoice
            invoice = serializer.save()
            from invoices.automation import queue_invoice_workflow
            queue_invoice_workflow(invoice, self.request.user, reviewed=True)
            invoice.refresh_from_db()
            AuditLog.objects.create(tenant=invoice.tenant, actor=self.request.user, action="EXTRACTION_CORRECTED", object_type="Invoice", object_id=str(invoice.id), metadata={"version": invoice.version})

    def perform_destroy(self, instance):
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=instance.pk, tenant=self.request.tenant)
            ensure_invoice_editable(invoice)
            invoice.delete()
    @action(detail=True, methods=["post"], url_path="confirm-extraction")
    def confirm_extraction(self, request, pk=None):
        if not role_allowed(request, "OWNER", "FINANCE", "PURCHASE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance or purchase role required"}}, status=403)
        invoice = self.get_object(); result = run_matching(invoice, request.user)
        if invoice.status == Invoice.Status.MATCHED:
            from invoices.automation import queue_invoice_workflow
            queue_invoice_workflow(invoice, request.user, reviewed=True)
            invoice.refresh_from_db()
        return Response({"invoice": InvoiceSerializer(invoice, context={"request": request}).data, "match_result": {"id": str(result.id), "outcome": result.outcome, "details": result.details}})
    @action(detail=True, methods=["post"], url_path="submit-for-approval")
    def submit_for_approval(self, request, pk=None):
        if not role_allowed(request, "OWNER", "FINANCE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        from approvals.workflow import submit_for_approval
        invoice = submit_for_approval(self.get_object(), request.user)
        return Response(InvoiceSerializer(invoice, context={"request": request}).data)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None): return self._decide(request, pk, "APPROVED")
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None): return self._decide(request, pk, "REJECTED")
    @action(detail=True, methods=["post"])
    def export(self, request, pk=None):
        if not role_allowed(request, "OWNER", "FINANCE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        invoice = self.get_object()
        try: job, csv_body = create_tally_csv(request.tenant, [invoice], request.user)
        except Exception as exc: return Response({"error": {"code": "STATE_CONFLICT", "message": str(exc)}}, status=409)
        response = HttpResponse(csv_body, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="kriyopay-tally-{job.id}.csv"'
        return response
    @transaction.atomic
    def _decide(self, request, pk, decision):
        invoice = get_object_or_404(Invoice.objects.select_for_update(of=("self",)), tenant=request.tenant, pk=pk)
        if request.membership.role not in ["OWNER", "FINANCE", "APPROVER"]: return Response({"error": {"code": "PERMISSION_DENIED", "message": "Approver role required"}}, status=403)
        if invoice.status != Invoice.Status.APPROVAL_PENDING: return Response({"error": {"code": "STATE_CONFLICT", "message": "Invoice is not awaiting approval"}}, status=409)
        if decision == "APPROVED" and (not invoice.vendor_id or invoice.vendor.tenant_id != request.tenant.pk):
            return Response({"error": {"message": "Link the correct workspace supplier and resubmit this invoice before approval."}}, status=409)
        step = invoice.approval_steps.filter(status=ApprovalStep.Status.PENDING).order_by("-workflow_version", "sequence").first()
        delegated_from = None
        if step:
            allowed_user = step.approver_id == request.user.id or bool(step.approver_role and step.approver_role == request.membership.role)
            if step.approver_id:
                delegation = ApprovalDelegation.objects.filter(tenant=request.tenant, delegator_id=step.approver_id, delegate=request.user, active=True, starts_at__lte=timezone.now(), ends_at__gt=timezone.now()).first()
                if delegation: allowed_user = True; delegated_from = step.approver
            if not allowed_user: return Response({"error": {"code": "PERMISSION_DENIED", "message": "This approval step is assigned to another user or role"}}, status=403)
        if invoice.uploaded_by_id == request.user.id: return Response({"error": {"code": "PERMISSION_DENIED", "message": "Invoice submitter cannot approve their own invoice"}}, status=403)
        Approval.objects.create(tenant=invoice.tenant, invoice=invoice, invoice_version=invoice.version, approver=request.user, decision=decision, comments=request.data.get("comments", ""), ip_address=request.META.get("REMOTE_ADDR"), user_agent=request.META.get("HTTP_USER_AGENT", "")[:500])
        more_steps = False
        if step:
            step.status = ApprovalStep.Status.APPROVED if decision == "APPROVED" else ApprovalStep.Status.REJECTED
            if delegated_from: step.delegated_from = delegated_from
            step.comments = request.data.get("comments", ""); step.decided_at = timezone.now()
            step.save(update_fields=["status", "delegated_from", "comments", "decided_at"])
            if decision == "REJECTED": invoice.approval_steps.filter(workflow_version=step.workflow_version, status=ApprovalStep.Status.PENDING).update(status=ApprovalStep.Status.SKIPPED, decided_at=timezone.now())
            more_steps = invoice.approval_steps.filter(workflow_version=step.workflow_version, status=ApprovalStep.Status.PENDING).exists()
        invoice.status = Invoice.Status.APPROVAL_PENDING if decision == "APPROVED" and more_steps else Invoice.Status.PAYMENT_READY if decision == "APPROVED" else Invoice.Status.REVIEW_REQUIRED; invoice.save(update_fields=["status", "updated_at"])
        if invoice.automation:
            from invoices.automation import _state
            _state(invoice, "PAYMENT_READY" if invoice.status == Invoice.Status.PAYMENT_READY else "AWAITING_APPROVAL" if invoice.status == Invoice.Status.APPROVAL_PENDING else "NEEDS_ATTENTION", "Approved and ready for payment recording." if invoice.status == Invoice.Status.PAYMENT_READY else "Waiting for the next approver." if invoice.status == Invoice.Status.APPROVAL_PENDING else "Invoice rejected. Review and correct it before resubmitting.", recheck_after=None)
        AuditLog.objects.create(tenant=invoice.tenant, actor=request.user, action=f"INVOICE_{decision}", object_type="Invoice", object_id=str(invoice.id), metadata={"version": invoice.version, "comments": request.data.get("comments", ""), "step_id": str(step.id) if step else None, "delegated_from": str(delegated_from.id) if delegated_from else None})
        return Response(InvoiceSerializer(invoice, context={"request": request}).data)

class Summary(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        qs = Invoice.objects.filter(tenant=request.tenant)
        payment_ready = qs.filter(status=Invoice.Status.PAYMENT_READY)
        open_exceptions = InvoiceException.objects.filter(tenant=request.tenant, status__in=["OPEN", "ASSIGNED"])
        status_counts = dict(qs.order_by().values("status").annotate(count=Count("id")).values_list("status", "count"))
        if request.query_params.get("compact") == "1":
            return Response({
                "total_invoices": sum(status_counts.values()),
                "exceptions": open_exceptions.count(),
                "pending_approvals": status_counts.get(Invoice.Status.APPROVAL_PENDING, 0),
            })
        exception_breakdown = list(open_exceptions.values("code").annotate(count=Count("id")).order_by("-count"))
        analytics = {}
        if request.query_params.get("analytics") == "1":
            from .dashboard import dashboard_analytics
            from admin_console.services import entitlements_for
            days = request.query_params.get("days", "30")
            days = int(days) if days in {"7", "30", "90"} else 30
            payment_access = entitlements_for(request.tenant)["features"].get("payment_tracking", {}).get("enabled", False)
            analytics = {"analytics": dashboard_analytics(request.tenant, days, include_finance=payment_access and role_allowed(request, "OWNER", "FINANCE", "AUDITOR"))}
        return Response({
            **analytics,
            "total_invoices": sum(status_counts.values()),
            "by_status": {s: status_counts.get(s, 0) for s, _ in Invoice.Status.choices},
            "exceptions": sum(row["count"] for row in exception_breakdown),
            "exception_breakdown": exception_breakdown,
            "payment_ready": status_counts.get(Invoice.Status.PAYMENT_READY, 0),
            "payment_ready_value": payment_ready.aggregate(total=Sum("invoice_total"))["total"] or 0,
            "pending_approvals": status_counts.get(Invoice.Status.APPROVAL_PENDING, 0),
            "monthly_volume": qs.filter(created_at__year=timezone.localdate().year, created_at__month=timezone.localdate().month).count(),
            "recent_invoices": [] if request.query_params.get("include_recent") == "0" else InvoiceSerializer(qs.select_related("vendor", "document").prefetch_related("lines", Prefetch("extractions", queryset=ExtractionResult.objects.filter(tenant=request.tenant).only("invoice_id", "confidence", "status", "output", "created_at").order_by("-created_at", "-id")[:1], to_attr="_latest_extractions")).order_by("-created_at")[:5], many=True, context={"request": request}).data,
        })

class ExceptionList(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        qs = InvoiceException.objects.filter(tenant=request.tenant).select_related("invoice", "assigned_to")
        if not request.query_params.get("status"):
            qs = qs.filter(status__in=["OPEN", "ASSIGNED"])
        for field in ("status", "code", "severity"):
            if request.query_params.get(field): qs = qs.filter(**{field: request.query_params[field]})
        return Response([{"id": str(x.id), "invoice_id": str(x.invoice_id), "invoice_number": x.invoice.invoice_number, "code": x.code, "severity": x.severity, "status": x.status, "details": x.details} for x in qs[:200]])

class ExceptionResolve(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request, exception_id):
        if not role_allowed(request, "OWNER", "FINANCE", "PURCHASE", "STORE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Operational role required"}}, status=403)
        exc = get_object_or_404(InvoiceException, id=exception_id, tenant=request.tenant)
        override = request.data.get("override", False); reason = request.data.get("override_reason", "")
        if override and not role_allowed(request, "OWNER", "FINANCE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance head approval is required to override"}}, status=403)
        if override and not reason.strip(): return Response({"error": {"code": "VALIDATION_ERROR", "message": "A reason is required to override"}}, status=400)
        exc.status = "OVERRIDDEN" if override else "RESOLVED"; exc.resolution_note = request.data.get("resolution_note", ""); exc.override_reason = reason; exc.resolved_at = timezone.now(); exc.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="EXCEPTION_OVERRIDDEN" if override else "EXCEPTION_RESOLVED", object_type="Exception", object_id=str(exc.id), metadata={"reason": reason, "note": exc.resolution_note})
        invoice = exc.invoice
        if not invoice.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists() and invoice.status == Invoice.Status.EXCEPTION:
            invoice.status = Invoice.Status.MATCHED; invoice.save(update_fields=["status", "updated_at"])
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="INVOICE_MATCHED_AFTER_RESOLUTION", object_type="Invoice", object_id=str(invoice.id), metadata={})
        return Response({"id": str(exc.id), "status": exc.status})

class ExceptionAssign(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request, exception_id):
        if not role_allowed(request, "OWNER", "FINANCE", "PURCHASE", "STORE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Operational role required"}}, status=403)
        exc = get_object_or_404(InvoiceException, id=exception_id, tenant=request.tenant)
        assignee = get_object_or_404(User, id=request.data.get("assigned_to_id"), memberships__tenant=request.tenant, memberships__is_active=True)
        if exc.status in ("RESOLVED", "OVERRIDDEN"): return Response({"error": {"code": "STATE_CONFLICT", "message": "Resolved exceptions cannot be assigned"}}, status=409)
        exc.assigned_to = assignee; exc.status = "ASSIGNED"; exc.save(update_fields=["assigned_to", "status"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="EXCEPTION_ASSIGNED", object_type="Exception", object_id=str(exc.id), metadata={"assigned_to": str(assignee.id)})
        return Response({"id": str(exc.id), "status": exc.status, "assigned_to_id": str(assignee.id)})

class MatchRun(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request):
        if not role_allowed(request, "OWNER", "FINANCE", "PURCHASE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance or purchase role required"}}, status=403)
        ids = request.data.get("invoice_ids", [])
        if not ids: return Response({"error": {"code": "VALIDATION_ERROR", "message": "invoice_ids is required"}}, status=400)
        invoices = Invoice.objects.filter(tenant=request.tenant, id__in=ids)
        results = [run_matching(invoice, request.user) for invoice in invoices]
        return Response({"results": [{"invoice_id": str(result.invoice_id), "outcome": result.outcome, "details": result.details} for result in results]})

class TallyExport(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request):
        if not role_allowed(request, "OWNER", "FINANCE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        ids = request.data.get("invoice_ids", [])
        try: job, csv_body = create_tally_csv(request.tenant, Invoice.objects.filter(tenant=request.tenant, id__in=ids), request.user)
        except Exception as exc: return Response({"error": {"code": "STATE_CONFLICT", "message": str(exc)}}, status=409)
        response = HttpResponse(csv_body, content_type="text/csv"); response["Content-Disposition"] = f'attachment; filename="kriyopay-tally-{job.id}.csv"'; return response

class ResourceList(APIView):
    permission_classes = [HasTenantMembership]
    model = None
    def get(self, request): return Response(list(self.model.objects.filter(tenant=request.tenant).values()[:200]))
class Vendors(ResourceList): model = Vendor

class POs(ResourceList):
    model = PurchaseOrder
    def get(self, request):
        records = PurchaseOrder.objects.filter(tenant=request.tenant).select_related("vendor", "approved_by").prefetch_related("lines").order_by("-order_date")[:200]
        line_ids = [line.id for po in records for line in po.lines.all()]
        received = {row["purchase_order_line_id"]: row["total"] for row in GRNLine.objects.filter(tenant=request.tenant, purchase_order_line_id__in=line_ids).values("purchase_order_line_id").annotate(total=Sum("quantity_received"))}
        matching_settings = MatchingSetting.objects.filter(tenant=request.tenant).only("over_receipt_tolerance_percent").first()
        tolerance = matching_settings.over_receipt_tolerance_percent if matching_settings else Decimal("0")
        return Response([{"id": str(po.id), "number": po.number, "vendor_id": str(po.vendor_id), "vendor": po.vendor.name, "order_date": po.order_date, "status": po.status, "revision": po.revision, "approved_by": po.approved_by.get_full_name() if po.approved_by else None, "lines": [{"id": str(l.id), "line_no": l.line_no, "description": l.description, "item_code": l.item_code, "quantity": l.quantity, "received_quantity": received.get(l.id, Decimal("0")), "remaining_quantity": max(Decimal("0"), l.quantity - received.get(l.id, Decimal("0"))), "maximum_receivable_quantity": (l.quantity * (Decimal("1") + tolerance / Decimal("100"))).quantize(Decimal("0.000001")), "uom": l.uom, "rate": l.rate, "taxable_value": l.taxable_value, "hsn_sac": l.hsn_sac, "gst_rate": l.gst_rate} for l in po.lines.order_by("line_no")]} for po in records])
    @transaction.atomic
    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Purchase role required"}}, status=403)
        vendor = Vendor.objects.filter(tenant=request.tenant, id=request.data.get("vendor_id")).first()
        number = str(request.data.get("number", "")).strip()
        lines = request.data.get("lines", [])
        if not vendor or not number or not isinstance(lines, list) or not lines: return Response({"error": {"code": "VALIDATION_ERROR", "message": "vendor_id, number and at least one line are required"}}, status=400)
        if PurchaseOrder.objects.filter(tenant=request.tenant, number=number).exists(): return Response({"error": {"code": "STATE_CONFLICT", "message": "Purchase order number already exists"}}, status=409)
        prepared = []
        if len(lines) > 50: return Response({"error": {"code": "VALIDATION_ERROR", "message": "A purchase order can contain at most 50 lines"}}, status=400)
        order_date = parse_date(str(request.data.get("order_date", ""))) if request.data.get("order_date") else None
        if request.data.get("order_date") and not order_date: return Response({"error": {"code": "VALIDATION_ERROR", "message": "order_date must be YYYY-MM-DD"}}, status=400)
        try:
            for index, line in enumerate(lines, 1):
                qty, rate = Decimal(str(line.get("quantity", 0))), Decimal(str(line.get("rate", 0)))
                taxable_value = Decimal(str(line.get("taxable_value", qty * rate)))
                gst_rate = Decimal(str(line.get("gst_rate", 0)))
                if not qty.is_finite() or not rate.is_finite() or not taxable_value.is_finite() or not gst_rate.is_finite() or qty <= 0 or rate < 0 or taxable_value < 0 or not 0 <= gst_rate <= 100 or not str(line.get("description", "")).strip(): raise ValueError
                prepared.append({"line_no": index, "description": str(line["description"]).strip()[:255], "item_code": str(line.get("item_code", ""))[:100], "hsn_sac": str(line.get("hsn_sac", ""))[:20], "quantity": qty, "uom": str(line.get("uom", ""))[:30], "rate": rate, "taxable_value": taxable_value, "gst_rate": gst_rate})
        except (ValueError, InvalidOperation, TypeError, KeyError, AttributeError): return Response({"error": {"code": "VALIDATION_ERROR", "message": "Each PO line needs a description, positive quantity, and non-negative rate"}}, status=400)
        po = PurchaseOrder.objects.create(tenant=request.tenant, vendor=vendor, number=number, order_date=order_date)
        for line in prepared: PurchaseOrderLine.objects.create(tenant=request.tenant, purchase_order=po, **line)
        record_purchase_order_revision(po, user=request.user, action="CREATED", change_note="Initial purchase order draft")
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="PURCHASE_ORDER_CREATED", object_type="PurchaseOrder", object_id=str(po.id), metadata={"number": number, "line_count": len(lines)})
        return Response({"id": str(po.id), "number": po.number, "status": po.status}, status=201)
    @transaction.atomic
    def patch(self, request):
        po = PurchaseOrder.objects.select_for_update().filter(tenant=request.tenant, id=request.data.get("purchase_order_id")).first()
        if not po: return Response({"error": "Purchase order not found"}, status=404)
        action = request.data.get("action")
        if action == "edit":
            if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE"): return Response({"error": "Purchase role required"}, status=403)
            if po.status != PurchaseOrder.Status.DRAFT: return Response({"error": "Only draft purchase orders can be edited; submit a change as a new purchase order after approval."}, status=409)
            if GRNLine.objects.filter(tenant=request.tenant, purchase_order_line__purchase_order=po).exists(): return Response({"error": "This purchase order has receipt history and cannot be edited."}, status=409)
            change_note = str(request.data.get("change_note", "")).strip()
            lines = request.data.get("lines")
            if len(change_note) < 8 or len(change_note) > 500: return Response({"error": "Add a change reason between 8 and 500 characters."}, status=400)
            if not isinstance(lines, list) or not lines or len(lines) > 50: return Response({"error": "Provide 1 to 50 purchase order lines."}, status=400)
            vendor = Vendor.objects.filter(tenant=request.tenant, id=request.data.get("vendor_id", po.vendor_id)).first()
            if not vendor: return Response({"error": "Choose a vendor from this workspace."}, status=404)
            order_date_raw = request.data.get("order_date", po.order_date.isoformat() if po.order_date else "")
            order_date = parse_date(str(order_date_raw)) if order_date_raw else None
            if order_date_raw and not order_date: return Response({"error": "order_date must be YYYY-MM-DD"}, status=400)
            prepared = []
            try:
                for index, line in enumerate(lines, 1):
                    qty = Decimal(str(line.get("quantity", 0))); rate = Decimal(str(line.get("rate", 0)))
                    taxable_value = Decimal(str(line.get("taxable_value", qty * rate))); gst_rate = Decimal(str(line.get("gst_rate", 0)))
                    if not qty.is_finite() or not rate.is_finite() or not taxable_value.is_finite() or not gst_rate.is_finite() or qty <= 0 or rate < 0 or taxable_value < 0 or not 0 <= gst_rate <= 100 or not str(line.get("description", "")).strip(): raise ValueError
                    prepared.append({"line_no": index, "description": str(line["description"]).strip()[:255], "item_code": str(line.get("item_code", ""))[:100], "hsn_sac": str(line.get("hsn_sac", ""))[:20], "quantity": qty, "uom": str(line.get("uom", ""))[:30], "rate": rate, "taxable_value": taxable_value, "gst_rate": gst_rate})
            except (ValueError, InvalidOperation, TypeError, KeyError, AttributeError): return Response({"error": "Each line needs a description, positive quantity, non-negative rate/taxable value, and GST rate from 0 to 100."}, status=400)
            po.vendor = vendor; po.order_date = order_date; po.revision += 1
            po.save(update_fields=["vendor", "order_date", "revision"])
            po.lines.all().delete()
            PurchaseOrderLine.objects.bulk_create([PurchaseOrderLine(tenant=request.tenant, purchase_order=po, **line) for line in prepared])
            record_purchase_order_revision(po, user=request.user, action="EDITED", change_note=change_note)
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="PURCHASE_ORDER_EDITED", object_type="PurchaseOrder", object_id=str(po.id), metadata={"revision": po.revision, "change_note": change_note, "line_count": len(prepared)})
            return Response({"id": str(po.id), "status": po.status, "revision": po.revision})
        elif action == "submit":
            if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE") or po.status != PurchaseOrder.Status.DRAFT: return Response({"error": "Only a draft PO can be submitted"}, status=409)
            po.status = PurchaseOrder.Status.PENDING_APPROVAL
        elif action in ("approve", "reject"):
            if request.membership.role not in ("OWNER", "FINANCE"): return Response({"error": "Finance approval role required"}, status=403)
            if po.status != PurchaseOrder.Status.PENDING_APPROVAL: return Response({"error": "PO is not awaiting approval"}, status=409)
            po.status = PurchaseOrder.Status.APPROVED if action == "approve" else PurchaseOrder.Status.CANCELLED
            if action == "approve": po.approved_by = request.user; po.approved_at = timezone.now()
        else: return Response({"error": "Action must be submit, approve or reject"}, status=400)
        po.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=f"PURCHASE_ORDER_{po.status}", object_type="PurchaseOrder", object_id=str(po.id), metadata={"action": action})
        if action == "approve": queue_webhook_event(request.tenant, "purchase_order.approved", {"purchase_order_id": str(po.id), "number": po.number, "vendor_id": str(po.vendor_id)})
        return Response({"id": str(po.id), "status": po.status})


class PORevisions(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request, purchase_order_id):
        purchase_order = PurchaseOrder.objects.filter(tenant=request.tenant, id=purchase_order_id).first()
        if not purchase_order: return Response({"error": "Purchase order not found"}, status=404)
        revisions = PurchaseOrderRevision.objects.filter(tenant=request.tenant, purchase_order=purchase_order).select_related("changed_by").order_by("-revision")[:100]
        return Response([{"revision": row.revision, "action": row.action, "change_note": row.change_note,
            "snapshot": row.snapshot, "changed_by": row.changed_by.get_full_name() if row.changed_by else None,
            "created_at": row.created_at} for row in revisions])

class GRNs(ResourceList):
    model = GRN
    def get(self, request):
        records = GRN.objects.filter(tenant=request.tenant).select_related("vendor", "purchase_order").prefetch_related("lines").order_by("-received_at")[:200]
        return Response([{"id": str(g.id), "number": g.number, "vendor_id": str(g.vendor_id), "vendor": g.vendor.name, "purchase_order_id": str(g.purchase_order_id) if g.purchase_order_id else None, "received_at": g.received_at, "quality_status": g.quality_status, "quality_note": g.quality_note, "lines": [{"id": str(line.id), "description": line.description, "quantity_received": line.quantity_received, "item_code": line.item_code} for line in g.lines.all()]} for g in records])
    @transaction.atomic
    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE", "STORE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Store role required"}}, status=403)
        po = PurchaseOrder.objects.select_for_update().filter(tenant=request.tenant, id=request.data.get("purchase_order_id"), status=PurchaseOrder.Status.APPROVED).first()
        number = str(request.data.get("number", "")).strip(); entries = request.data.get("lines", [])
        if not po or not number or not isinstance(entries, list) or not entries: return Response({"error": {"code": "VALIDATION_ERROR", "message": "An approved purchase_order_id, number and receipt lines are required"}}, status=400)
        if GRN.objects.filter(tenant=request.tenant, number=number).exists(): return Response({"error": {"code": "STATE_CONFLICT", "message": "GRN number already exists"}}, status=409)
        prepared = []; seen_lines = set()
        try:
            for entry in entries:
                line = PurchaseOrderLine.objects.filter(tenant=request.tenant, purchase_order=po, id=entry.get("purchase_order_line_id")).first()
                qty = Decimal(str(entry.get("quantity_received", 0)))
                if not line or not qty.is_finite() or qty <= 0: raise ValueError
                if line.id in seen_lines: return Response({"error": {"code": "VALIDATION_ERROR", "message": "Include each purchase order line only once per receipt"}}, status=400)
                seen_lines.add(line.id)
                prepared.append((line, qty))
        except (ValueError, InvalidOperation, TypeError): return Response({"error": {"code": "VALIDATION_ERROR", "message": "Receipt lines must reference PO lines and have positive quantities"}}, status=400)
        for line, qty in prepared:
            balance = receipt_balance(line)
            if balance["received"] + qty > balance["maximum_receivable"]:
                return Response({"error": {"code": "RECEIPT_LIMIT_EXCEEDED", "message": f"{line.description}: {balance['remaining_receivable']} {line.uom or 'unit(s)'} remain receivable across this PO line."}}, status=409)
        grn = GRN.objects.create(tenant=request.tenant, vendor=po.vendor, purchase_order=po, number=number, received_at=request.data.get("received_at"))
        for line, qty in prepared: GRNLine.objects.create(tenant=request.tenant, grn=grn, purchase_order_line=line, description=line.description, item_code=line.item_code, uom=line.uom, quantity_received=qty)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="GRN_CREATED", object_type="GRN", object_id=str(grn.id), metadata={"number": number, "purchase_order": po.number})
        queue_webhook_event(request.tenant, "goods_receipt.recorded", {"grn_id": str(grn.id), "number": grn.number, "purchase_order_id": str(po.id)})
        return Response({"id": str(grn.id), "number": grn.number, "quality_status": grn.quality_status}, status=201)
    def patch(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "STORE"): return Response({"error": "Store or finance role required"}, status=403)
        grn = GRN.objects.filter(tenant=request.tenant, id=request.data.get("grn_id")).first()
        quality = request.data.get("quality_status")
        if not grn: return Response({"error": "GRN not found"}, status=404)
        if quality not in GRN.QualityStatus.values: return Response({"error": "Invalid quality status"}, status=400)
        grn.quality_status = quality; grn.quality_note = str(request.data.get("quality_note", ""))[:3000]; grn.save(update_fields=["quality_status", "quality_note"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="GRN_QUALITY_RECORDED", object_type="GRN", object_id=str(grn.id), metadata={"quality_status": quality})
        return Response({"id": str(grn.id), "quality_status": grn.quality_status})

class AuditRecords(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        events = AuditLog.objects.filter(tenant=request.tenant).select_related("actor").order_by("-created_at")[:200]
        return Response([{
            "id": str(event.id),
            "actor": event.actor.get_full_name() or event.actor.email if event.actor else "System",
            "actor_email": event.actor.email if event.actor else "",
            "action": event.action,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "metadata": event.metadata,
            "created_at": event.created_at,
        } for event in events])
