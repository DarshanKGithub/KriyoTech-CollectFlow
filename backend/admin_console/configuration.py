import json
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from .models import TenantFeatureOverride, PlanFeature, Feature
from tenants.models import Tenant
from rest_framework.exceptions import ValidationError
class ConfigurationService:
    """Centralized configuration management service."""

    def __init__(self):
        self.cache_prefix = "config:"
        self.ttl = 300  # 5 minutes cache

    def get_feature_configuration(self, tenant):
        """Get complete feature configuration for a tenant."""
        cache_key = f"{self.cache_prefix}features:{tenant.id}"
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

    def set_feature_override(self, tenant_or_id, feature_key, enabled, limit_value=None, limit_period="", reason="", expires_at=None, created_by=None):
        """Set a feature override for a tenant."""
        from tenants.models import Tenant

        if isinstance(tenant_or_id, str):
            # tenant_or_id is actually tenant_id string
            tenant = Tenant.objects.get(id=tenant_or_id, is_deleted=False)
        else:
            tenant = tenant_or_id

        feature = Feature.objects.filter(key=feature_key, is_active=True).first()
        if not feature:
            raise ValidationError({"error": f"Feature '{feature_key}' not found."})

        # Validate reason length
        if len(reason) > 500:
            reason = reason[:500]

        # Invalidate cache
        cache.delete(f"{self.cache_prefix}features:{tenant.id}")

        override, created = TenantFeatureOverride.objects.update_or_create(
            tenant=tenant,
            feature=feature,
            defaults={
                "enabled": enabled,
                "limit_value": limit_value,
                "reason": reason,
                "expires_at": expires_at,
                "created_by": created_by,
            }
        )

        # If disabling a feature, check if it's part of the current plan
        if not enabled and created:
            subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
            if subscription:
                plan_feature = PlanFeature.objects.filter(plan=subscription.plan, feature=feature).first()
                if plan_feature and plan_feature.enabled:
                    # Re-enable from plan if this was the last override
                    remaining_overrides = TenantFeatureOverride.objects.filter(
                        tenant=tenant, feature=feature
                    ).exclude(id=override.id).count()
                    if remaining_overrides == 0:
                        plan_feature.enabled = True
                        plan_feature.save(update_fields=["enabled"])

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

            if not feature_key:
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

            # Validate limit_value if provided
            if limit_value is not None:
                try:
                    limit_value = int(limit_value)
                    if limit_value < 0:
                        errors.append({"error": f"limit_value for '{feature_key}' must be non-negative."})
                except (ValueError, TypeError):
                    errors.append({"error": f"limit_value for '{feature_key}' must be an integer."})

            # Validate reason
            if not reason or len(reason.strip()) < 8:
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

    def create_tenant_configuration(self, tenant_id, feature_overrides):
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
                    tenant=tenant,
                    feature_key=override_data["feature_key"],
                    enabled=override_data.get("enabled", False),
                    limit_value=override_data.get("limit_value"),
                    limit_period=override_data.get("limit_period", ""),
                    reason=override_data.get("reason", ""),
                    expires_at=override_data.get("expires_at"),
                    created_by=override_data.get("created_by")
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

        return {"tenant_id": str(tenant.id), "results": results}

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

    def bulk_update_features(self, tenant_id, updates):
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
                    tenant=tenant,
                    feature_key=update["feature_key"],
                    enabled=update.get("enabled"),
                    limit_value=update.get("limit_value"),
                    limit_period=update.get("limit_period", ""),
                    reason=update.get("reason", ""),
                    expires_at=update.get("expires_at"),
                    created_by=update.get("created_by")
                )
                results.append({
                    "feature_key": update["feature_key"],
                    "status": "success",
                    "override_id": str(override.id)
                })
            except Exception as e:
                errors.append({
                    "feature_key": update["feature_key"],
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
            cache.delete(f"{self.cache_prefix}features:{tenant_id}")
            return {"status": "success", "message": f"Cache cleared for tenant {tenant_id}"}
        else:
            # Clear all config cache
            keys = [k for k in cache.keys(f"{self.cache_prefix}*")]
            cache.delete_many(keys)
            return {"status": "success", "message": "All configuration cache cleared"}
# Global instance
config_service = ConfigurationService()
