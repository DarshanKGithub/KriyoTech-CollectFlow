from collections.abc import Mapping
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .permissions import IsAdminStaff
from .configuration import config_service
from .models import AdminStaff
from rest_framework.exceptions import ValidationError
class ConfigurationAPI(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method in {"POST", "PATCH"} and not isinstance(request.data, Mapping):
            raise ValidationError("Send an object with named fields.")


class ConfigurationView(ConfigurationAPI):
    """API endpoints for configuration management."""

    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]

    def get(self, request):
        """Get all available features."""
        try:
            features = config_service.get_all_features()
            return Response({"features": list(features), "count": len(features)})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """Create or update feature configuration for a tenant."""
        try:
            tenant_id = request.data.get("tenant_id")
            feature_overrides = request.data.get("feature_overrides", [])

            if not tenant_id:
                return Response(
                    {"error": "tenant_id is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not isinstance(feature_overrides, list) or not feature_overrides or len(feature_overrides) > 100 or any(not isinstance(row, dict) for row in feature_overrides):
                return Response(
                    {"error": "feature_overrides is required and cannot be empty."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            result = config_service.create_tenant_configuration(tenant_id, feature_overrides, actor=request.user)
            if "errors" in result:
                return Response(
                    {"errors": result["errors"]},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response(result, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Failed to create configuration: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class PlanFeaturesView(ConfigurationAPI):
    """API endpoints for plan features."""

    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]

    def get(self, request, plan_id):
        """Get all features for a specific plan."""
        try:
            plan_features = config_service.get_plan_features(plan_id)
            return Response(plan_features)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class TenantConfigurationView(ConfigurationAPI):
    """API endpoints for tenant-specific configuration."""

    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]

    def get(self, request, tenant_id):
        """Get complete configuration for a tenant."""
        try:
            # Import Tenant here to avoid circular imports
            from tenants.models import Tenant
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            configuration = config_service.get_feature_configuration(tenant)
            return Response(configuration)
        except Tenant.DoesNotExist:
            return Response(
                {"error": "Tenant not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, tenant_id):
        """Update multiple features for a tenant."""
        try:
            updates = request.data.get("updates", [])

            if not isinstance(updates, list) or not updates or len(updates) > 100 or any(not isinstance(row, dict) for row in updates):
                return Response(
                    {"error": "updates is required and cannot be empty."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            result = config_service.bulk_update_features(tenant_id, updates, actor=request.user)

            if result["error_count"] > 0:
                return Response(
                    {
                        "message": f"Partial success: {result['success_count']} succeeded, {result['error_count']} failed.",
                        "results": result["results"],
                        "errors": result["errors"]
                    },
                    status=status.HTTP_207_MULTI_STATUS
                )

            return Response(result, status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Failed to update configuration: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request, tenant_id):
        """Single feature override for a tenant."""
        try:
            feature_key = request.data.get("feature_key")
            enabled = request.data.get("enabled")
            limit_value = request.data.get("limit_value")
            limit_period = request.data.get("limit_period", "")
            reason = request.data.get("reason", "")
            expires_at = request.data.get("expires_at")

            if not feature_key:
                return Response(
                    {"error": "feature_key is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if enabled is None:
                return Response(
                    {"error": "enabled is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not isinstance(reason, str) or len(reason.strip()) < 8:
                return Response(
                    {"error": "reason must be at least 8 characters."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            override = config_service.set_feature_override(
                tenant_or_id=tenant_id,
                feature_key=feature_key,
                enabled=enabled,
                limit_value=limit_value,
                limit_period=limit_period,
                reason=reason,
                expires_at=expires_at,
                created_by=request.user
            )

            return Response(
                {
                    "feature_key": feature_key,
                    "enabled": override.enabled,
                    "override_id": str(override.id),
                    "status": "success"
                },
                status=status.HTTP_201_CREATED
            )

        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Failed to create feature override: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class ConfigurationHistoryView(ConfigurationAPI):
    """API endpoints for configuration history."""

    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]

    def get(self, request, tenant_id):
        """Get configuration change history for a tenant."""
        try:
            limit = int(request.query_params.get("limit", "50"))
            history = config_service.get_tenant_configuration_history(tenant_id, limit)
            return Response(history)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class ConfigurationCacheView(ConfigurationAPI):
    """API endpoints for configuration cache management."""

    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN]

    def post(self, request):
        """Clear configuration cache."""
        try:
            tenant_id = request.data.get("tenant_id")
            result = config_service.clear_cache(tenant_id)
            return Response(result)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
