import json
import uuid
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.dateparse import parse_datetime
from django.db.models import Q
from django.utils import timezone
from .models import AdminAuditLog, AdminStaff, TenantFeatureOverride, PlanFeature, Feature
from tenants.models import Tenant
from rest_framework.exceptions import ValidationError
class ConfigurationService:
    """Centralized configuration management service."""

    def __init__(self):
        self.cache_prefix = "config:"
        self.ttl = 300  # 5 minutes cache

    def _feature_cache_key(self, tenant_id):
        generation = cache.get(f"{self.cache_prefix}generation", "0")
        return f"{self.cache_prefix}features:{generation}:{tenant_id}"

    def get_feature_configuration(self, tenant):
        """Get complete feature configuration for a tenant."""
        cache_key = self._feature_cache_key(tenant.id)
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Get plan-based features
        subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        features = {}

        if subscription:
            for row in PlanFeature.objects.filter(plan=subscription.plan, feature__is_active=True).select_related("feature"):
                features[row.feature.key] = {
                    "enabled": row.enabled,
                    "limit_value": row.limit_value,
                    "limit_period": row.limit_period,
                    "source": "plan",
                    "plan_name": subscription.plan.name
                }

        # Apply overrides
        now = timezone.now()
        for row in TenantFeatureOverride.objects.filter(tenant=tenant, feature__is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).select_related("feature").order_by("created_at", "id"):
            features[row.feature.key] = {
                "enabled": row.enabled,
                "limit_value": row.limit_value,
                "limit_period": "",
                "source": "override",
                "reason": row.reason,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "created_by": row.created_by.email if row.created_by else None
            }

        # Add default values for missing features
        feature_keys = Feature.objects.filter(is_active=True).values_list("key", flat=True)
        for key in feature_keys:
            if key not in features:
                features[key] = {
                    "enabled": False,
                    "limit_value": None,
                    "limit_period": None,
                    "source": "default",
                    "plan_name": subscription.plan.name if subscription else None
                }

        config = {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "subscription": {
                "id": str(subscription.id) if subscription else None,
                "plan_id": str(subscription.plan_id) if subscription and subscription.plan else None,
                "plan_name": subscription.plan.name if subscription and subscription.plan else None,
                "status": subscription.status if subscription else None,
                "billing_cycle": subscription.billing_cycle if subscription else None,
            },
            "features": features,
            "updated_at": timezone.now().isoformat()
        }

        cache.set(cache_key, config, self.ttl)
        return config

    @transaction.atomic
    def set_feature_override(self, tenant_or_id, feature_key, enabled, limit_value=None, limit_period="", reason="", expires_at=None, created_by=None):
        """Append an audited decision, preserving previous override history."""
        try:
            tenant = Tenant.objects.select_for_update().get(
                pk=tenant_or_id.pk if isinstance(tenant_or_id, Tenant) else tenant_or_id,
                is_deleted=False,
            )
        except (Tenant.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            raise ValidationError({"tenant_id": "Choose an active company."}) from None
        if not isinstance(feature_key, str):
            raise ValidationError({"feature_key": "Choose an active feature."})
        feature = Feature.objects.filter(key=feature_key, is_active=True).first()
        if not feature:
            raise ValidationError({"feature_key": "Choose an active feature."})
        if type(enabled) is not bool:
            raise ValidationError({"enabled": "Use true or false."})
        if limit_value is not None and (type(limit_value) is not int or not 0 <= limit_value <= 2147483647):
            raise ValidationError({"limit_value": "Use a non-negative integer or null."})
        if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 500:
            raise ValidationError({"reason": "Give a reason of 8 to 500 characters."})
        if isinstance(expires_at, str):
            try:
                expires_at = parse_datetime(expires_at)
            except ValueError:
                expires_at = None
            if expires_at is None:
                raise ValidationError({"expires_at": "Use a future ISO timestamp with timezone."})
        if expires_at is not None:
            from datetime import datetime
            if not isinstance(expires_at, datetime) or not timezone.is_aware(expires_at) or expires_at <= timezone.now():
                raise ValidationError({"expires_at": "Use a future ISO timestamp with timezone."})
        override = TenantFeatureOverride.objects.create(
            tenant=tenant, feature=feature, enabled=enabled, limit_value=limit_value,
            reason=reason.strip(), expires_at=expires_at, created_by=created_by,
        )
        role = AdminStaff.objects.filter(user=created_by, is_active=True).values_list("role", flat=True).first() if created_by else ""
        AdminAuditLog.objects.create(
            tenant=tenant, actor=created_by, actor_role=role or "", action="TENANT_FEATURE_OVERRIDE_CHANGED",
            object_type="TenantFeatureOverride", object_id=str(override.pk), reason=reason.strip(),
            metadata={"feature": feature.key, "enabled": enabled, "limit_value": limit_value},
        )
        cache_key = self._feature_cache_key(tenant.id)
        cache.delete(cache_key)
        transaction.on_commit(lambda: cache.delete(cache_key))
        return override

    def validate_configuration(self, tenant, feature_overrides):
        """Validate feature overrides before applying."""
        errors = []

        # Check if tenant has a subscription
        subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        if not subscription:
            errors.append({"error": "Tenant must have an active subscription to configure features."})
            return errors

        # Validate each override
        for override_data in feature_overrides:
            feature_key = override_data.get("feature_key")
            enabled = override_data.get("enabled", False)
            limit_value = override_data.get("limit_value")
            reason = override_data.get("reason", "")

            if not isinstance(feature_key, str) or not feature_key:
                errors.append({"error": "feature_key is required."})
                continue

            feature = Feature.objects.filter(key=feature_key, is_active=True).first()
            if not feature:
                errors.append({"error": f"Feature '{feature_key}' not found or inactive."})
                continue

            # Check if feature is available in current plan
            plan_feature = PlanFeature.objects.filter(plan=subscription.plan, feature=feature).first()
            if not plan_feature:
                errors.append({
                    "error": f"Feature '{feature_key}' is not included in the current plan."
                })

            if type(enabled) is not bool:
                errors.append({"error": f"enabled for '{feature_key}' must be true or false."})
            if limit_value is not None and (type(limit_value) is not int or not 0 <= limit_value <= 2147483647):
                errors.append({"error": f"limit_value for '{feature_key}' must be a non-negative integer."})

            # Validate reason
            if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 500:
                errors.append({"error": f"reason must be at least 8 characters for '{feature_key}'."})

        return errors

    def get_all_features(self):
        """Get all available features."""
        return Feature.objects.filter(is_active=True).order_by("sort_order", "name").values(
            "key", "name", "description", "sort_order"
        )

    def get_plan_features(self, plan_id):
        """Get features for a specific plan."""
        try:
            from .models import Plan
            plan = Plan.objects.get(id=plan_id, is_active=True)
            features = []

            for plan_feature in PlanFeature.objects.filter(plan=plan).select_related("feature"):
                features.append({
                    "feature_key": plan_feature.feature.key,
                    "feature_name": plan_feature.feature.name,
                    "enabled": plan_feature.enabled,
                    "limit_value": plan_feature.limit_value,
                    "limit_period": plan_feature.limit_period,
                    "description": plan_feature.feature.description
                })

            return {"plan_id": str(plan.id), "plan_name": plan.name, "features": features}

        except Plan.DoesNotExist:
            raise ValidationError({"error": "Plan not found or inactive."})

    def create_tenant_configuration(self, tenant_id, feature_overrides, *, actor=None):
        """Create initial configuration for a new tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
        except Tenant.DoesNotExist:
            raise ValidationError({"error": "Tenant not found."})

        # Validate configuration
        errors = self.validate_configuration(tenant, feature_overrides)
        if errors:
            return {"errors": errors}

        # Apply overrides
        results = []
        for override_data in feature_overrides:
            try:
                override = self.set_feature_override(
                    tenant_or_id=tenant,
                    feature_key=override_data["feature_key"],
                    enabled=override_data.get("enabled", False),
                    limit_value=override_data.get("limit_value"),
                    limit_period=override_data.get("limit_period", ""),
                    reason=override_data.get("reason", ""),
                    expires_at=override_data.get("expires_at"),
                    created_by=actor
                )
                results.append({
                    "feature_key": override_data["feature_key"],
                    "status": "success",
                    "override_id": str(override.id)
                })
            except Exception as e:
                results.append({
                    "feature_key": override_data["feature_key"],
                    "status": "error",
                    "error": str(e)
                })

        return {"tenant_id": str(tenant.id), "results": results,
                **({"errors": [row for row in results if row["status"] == "error"]} if any(row["status"] == "error" for row in results) else {})}

    def get_tenant_configuration_history(self, tenant_id, limit=50):
        """Get configuration change history for a tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
        except Tenant.DoesNotExist:
            raise ValidationError({"error": "Tenant not found."})

        overrides = TenantFeatureOverride.objects.filter(
            tenant=tenant
        ).select_related("feature", "created_by").order_by("-created_at")[:limit]

        history = []
        for override in overrides:
            history.append({
                "override_id": str(override.id),
                "feature_key": override.feature.key,
                "feature_name": override.feature.name,
                "enabled": override.enabled,
                "limit_value": override.limit_value,
                "reason": override.reason,
                "expires_at": override.expires_at.isoformat() if override.expires_at else None,
                "created_by": override.created_by.email if override.created_by else None,
                "created_at": override.created_at.isoformat(),
            })

        return {"tenant_id": str(tenant.id), "overrides": history}

    def bulk_update_features(self, tenant_id, updates, *, actor=None):
        """Bulk update multiple features for a tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
        except Tenant.DoesNotExist:
            raise ValidationError({"error": "Tenant not found."})

        results = []
        errors = []

        for update in updates:
            try:
                override = self.set_feature_override(
                    tenant_or_id=tenant,
                    feature_key=update.get("feature_key"),
                    enabled=update.get("enabled"),
                    limit_value=update.get("limit_value"),
                    limit_period=update.get("limit_period", ""),
                    reason=update.get("reason", ""),
                    expires_at=update.get("expires_at"),
                    created_by=actor
                )
                results.append({
                    "feature_key": update.get("feature_key"),
                    "status": "success",
                    "override_id": str(override.id)
                })
            except Exception as e:
                errors.append({
                    "feature_key": update.get("feature_key"),
                    "status": "error",
                    "error": str(e)
                })

        return {
            "tenant_id": str(tenant.id),
            "results": results,
            "errors": errors,
            "success_count": len(results),
            "error_count": len(errors)
        }

    def clear_cache(self, tenant_id=None):
        """Clear configuration cache."""
        if tenant_id:
            cache.delete(self._feature_cache_key(tenant_id))
            return {"status": "success", "message": f"Cache cleared for tenant {tenant_id}"}
        else:
            # Rotate only this namespace; never clear authentication throttles.
            cache.set(f"{self.cache_prefix}generation", uuid.uuid4().hex, timeout=None)
            return {"status": "success", "message": "All configuration cache cleared"}
# Global instance
config_service = ConfigurationService()
