from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .models import Vendor
from .serializers import VendorSerializer

class VendorCollection(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        qs = Vendor.objects.filter(tenant=request.tenant)
        if request.query_params.get("approved") is not None: qs = qs.filter(approved=request.query_params["approved"].lower()=="true")
        return Response(VendorSerializer(qs, many=True).data)
    def post(self, request):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Purchase role required"}}, status=403)
        serializer = VendorSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        vendor = serializer.save(tenant=request.tenant)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="VENDOR_CREATED", object_type="Vendor", object_id=str(vendor.id), metadata={})
        return Response(VendorSerializer(vendor).data, status=201)

class VendorDetail(APIView):
    permission_classes = [HasTenantMembership]
    def patch(self, request, vendor_id):
        if request.membership.role not in ("OWNER", "FINANCE", "PURCHASE"): return Response({"error": {"code": "PERMISSION_DENIED", "message": "Purchase role required"}}, status=403)
        vendor = get_object_or_404(Vendor, tenant=request.tenant, id=vendor_id)
        serializer = VendorSerializer(vendor, data=request.data, partial=True); serializer.is_valid(raise_exception=True); serializer.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="VENDOR_UPDATED", object_type="Vendor", object_id=str(vendor.id), metadata={})
        return Response(serializer.data)
