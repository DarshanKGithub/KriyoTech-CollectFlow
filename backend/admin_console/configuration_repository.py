"""
Configuration repository for data access and persistence.
Provides data access layer for configuration management.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache
from .models import (
    Feature,
    Plan,
    PlanFeature,
    Tenant,
    TenantFeatureOverride,
    AdminStaff,
    Subscription,
    AdminAuditLog,
)
class ConfigurationRepository:
    """Repository for configuration data access."""

    def __init__(self):
        self.cache_prefix = "config:"
        self.ttl = 300  # 5 minutes cache

    def get_feature_configuration(self, tenant_id):
        """Get feature configuration for a tenant by ID."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            return self._get_feature_configuration(tenant)
        except Tenant.DoesNotExist:
            return None

    def _get_feature_configuration(self, tenant):
        """Get feature configuration for a tenant object."""
        cache_key = f"{self.cache_prefix}features:{tenant.id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        config = self._build_feature_configuration(tenant)
        cache.set(cache_key, config, self.ttl)
        return config

    def _build_feature_configuration(self, tenant):
        """Build complete feature configuration for a tenant."""
        # Get plan-based features
        subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        features = {}

        if subscription:
            for row in PlanFeature.objects.filter(
                plan=subscription.plan, feature__is_active=True
            ).select_related("feature"):
                features[row.feature.key] = {
                    "enabled": row.enabled,
                    "limit_value": row.limit_value,
                    "limit_period": row.limit_period,
                    "source": "plan",
                    "plan_name": subscription.plan.name
                }

        # Apply overrides
        now = timezone.now()
        for row in TenantFeatureOverride.objects.filter(
            tenant=tenant, feature__is_active=True
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).select_related("feature").order_by("created_at", "id"):
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
                    "plan_name": subscription.plan.name if subscription and subscription.plan else None
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

        return config

    def create_feature_override(self, tenant, feature_key, enabled, **kwargs):
        """Create a feature override."""
        feature = Feature.objects.get(key=feature_key, is_active=True)

        # Invalidate cache
        cache.delete(f"{self.cache_prefix}features:{tenant.id}")

        with transaction.atomic():
            override, created = TenantFeatureOverride.objects.update_or_create(
                tenant=tenant,
                feature=feature,
                defaults={
                    "enabled": enabled,
                    "limit_value": kwargs.get('limit_value'),
                    "reason": kwargs.get('reason', '')[:500],
                    "expires_at": kwargs.get('expires_at'),
                    "created_by": kwargs.get('created_by'),
                }
            )

            # Handle plan re-enablement
            self._handle_feature_re_enablement(tenant, feature, enabled, override, created)

            return override

    def _handle_feature_re_enablement(self, tenant, feature, enabled, override, created):
        """Handle re-enabling features from plan when overrides are removed."""
        if not enabled and created:
            subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
            if subscription:
                plan_feature = PlanFeature.objects.filter(
                    plan=subscription.plan, feature=feature
                ).first()

                if plan_feature and plan_feature.enabled:
                    # Re-enable from plan if this was the last override
                    remaining_overrides = TenantFeatureOverride.objects.filter(
                        tenant=tenant, feature=feature
                    ).exclude(id=override.id).count()

                    if remaining_overrides == 0:
                        plan_feature.enabled = True
                        plan_feature.save(update_fields=["enabled"])

    def get_tenant_subscription(self, tenant_id):
        """Get tenant's subscription information."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
            return subscription
        except Tenant.DoesNotExist:
            return None

    def get_plan_features(self, plan_id):
        """Get all features for a specific plan."""
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

    def get_all_active_features(self):
        """Get all active features."""
        return Feature.objects.filter(is_active=True).order_by("sort_order", "name").values(
            "key", "name", "description", "sort_order"
        )

    def get_feature_overrides_for_tenant(self, tenant_id):
        """Get all feature overrides for a tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            return TenantFeatureOverride.objects.filter(
                tenant=tenant
            ).select_related("feature", "created_by").order_by("-created_at")
        except Tenant.DoesNotExist:
            return TenantFeatureOverride.objects.none()

    def delete_feature_override(self, tenant_id, override_id):
        """Delete a feature override."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            override = TenantFeatureOverride.objects.get(id=override_id, tenant=tenant)

            # Invalidate cache
            cache.delete(f"{self.cache_prefix}features:{tenant.id}")

            override.delete()
            return True
        except (Tenant.DoesNotExist, TenantFeatureOverride.DoesNotExist):
            return False

    def get_feature_override_by_feature(self, tenant_id, feature_key):
        """Get feature override by tenant and feature key."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            feature = Feature.objects.get(key=feature_key, is_active=True)
            return TenantFeatureOverride.objects.filter(
                tenant=tenant, feature=feature
            ).select_related("feature", "created_by").order_by("-created_at").first()
        except (Tenant.DoesNotExist, Feature.DoesNotExist):
            return None

    def exists_feature_override(self, tenant_id, feature_key):
        """Check if a feature override exists for a tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            feature = Feature.objects.get(key=feature_key, is_active=True)
            return TenantFeatureOverride.objects.filter(
                tenant=tenant, feature=feature
            ).exists()
        except (Tenant.DoesNotExist, Feature.DoesNotExist):
            return False

    def get_admin_staff(self, user_id):
        """Get admin staff information."""
        try:
            user = AdminStaff.objects.get(id=user_id, is_active=True)
            return user
        except AdminStaff.DoesNotExist:
            return None

    def log_admin_action(self, user, action, tenant=None, obj=None, reason="", metadata=None):
        """Log admin action to audit log."""
        return AdminAuditLog.objects.create(
            actor=user,
            actor_role=user.role if hasattr(user, 'role') else None,
            action=action,
            tenant=tenant,
            object_type=obj.__class__.__name__ if obj else "",
            object_id=str(obj.pk) if obj else "",
            reason=reason,
            metadata=metadata or {}
        )

    def get_tenant_by_id(self, tenant_id):
        """Get tenant by ID."""
        try:
            return Tenant.objects.get(id=tenant_id, is_deleted=False)
        except Tenant.DoesNotExist:
            return None

    def invalidate_cache(self, tenant_id):
        """Invalidate configuration cache for a tenant."""
        cache.delete(f"{self.cache_prefix}features:{tenant_id}")

    def get_feature_configuration_with_audit(self, tenant_id, requesting_user):
        """Get feature configuration with audit logging."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            user = AdminStaff.objects.get(user=requesting_user, is_active=True)

            # Log access
            self.log_admin_action(
                user=user,
                action="CONFIGURATION_ACCESS",
                tenant=tenant,
                reason="Admin accessed feature configuration"
            )

            return self._get_feature_configuration(tenant)

        except (Tenant.DoesNotExist, AdminStaff.DoesNotExist):
            return None

    def create_feature_override_with_audit(self, tenant_id, feature_key, enabled, **kwargs):
        """Create feature override with audit logging."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            user = AdminStaff.objects.get(user=kwargs.get('created_by'), is_active=True)

            override = self.create_feature_override(
                tenant, feature_key, enabled, **kwargs
            )

            # Log creation
            self.log_admin_action(
                user=user,
                action="FEATURE_OVERRIDE_CREATED",
                tenant=tenant,
                obj=override,
                reason=kwargs.get('reason', ''),
                metadata={'feature_key': feature_key, 'enabled': enabled}
            )

            return override

        except (Tenant.DoesNotExist, AdminStaff.DoesNotExist) as e:
            return None

    def update_feature_override_with_audit(self, tenant_id, override_id, updates, user):
        """Update feature override with audit logging."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            override = TenantFeatureOverride.objects.get(id=override_id, tenant=tenant)

            # Invalidate cache
            cache.delete(f"{self.cache_prefix}features:{tenant.id}")

            # Update fields
            for field, value in updates.items():
                setattr(override, field, value)

            override.save()

            # Log update
            self.log_admin_action(
                user=user,
                action="FEATURE_OVERRIDE_UPDATED",
                tenant=tenant,
                obj=override,
                reason=updates.get('reason', ''),
                metadata={'field_updates': list(updates.keys())}
            )

            return override

        except (Tenant.DoesNotExist, TenantFeatureOverride.DoesNotExist):
            return None

    def delete_feature_override_with_audit(self, tenant_id, override_id, user):
        """Delete feature override with audit logging."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            override = TenantFeatureOverride.objects.get(id=override_id, tenant=tenant)

            # Invalidate cache
            cache.delete(f"{self.cache_prefix}features:{tenant.id}")

            # Log deletion before deleting
            self.log_admin_action(
                user=user,
                action="FEATURE_OVERRIDE_DELETED",
                tenant=tenant,
                obj=override,
                reason="Override deleted via admin interface"
            )

            override.delete()
            return True

        except (Tenant.DoesNotExist, TenantFeatureOverride.DoesNotExist):
            return False

    def get_feature_override_history(self, tenant_id, limit=50):
        """Get feature override history for a tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            return TenantFeatureOverride.objects.filter(
                tenant=tenant
            ).select_related("feature", "created_by").order_by("-created_at")[:limit]
        except Tenant.DoesNotExist:
            return TenantFeatureOverride.objects.none()

    def bulk_create_feature_overrides(self, tenant_id, overrides):
        """Bulk create feature overrides."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)

            results = []
            errors = []

            for override_data in overrides:
                try:
                    feature_key = override_data['feature_key']
                    enabled = override_data['enabled']

                    override = self.create_feature_override(
                        tenant,
                        feature_key,
                        enabled,
                        reason=override_data.get('reason', ''),
                        expires_at=override_data.get('expires_at'),
                        created_by=override_data.get('created_by')
                    )

                    results.append({
                        'feature_key': feature_key,
                        'status': 'success',
                        'override_id': str(override.id)
                    })
                except Exception as e:
                    errors.append({
                        'feature_key': override_data['feature_key'],
                        'status': 'error',
                        'error': str(e)
                    })

            return {
                'tenant_id': tenant_id,
                'results': results,
                'errors': errors,
                'success_count': len(results),
                'error_count': len(errors)
            }

        except Tenant.DoesNotExist:
            return {
                'tenant_id': tenant_id,
                'results': [],
                'errors': [{'feature_key': 'unknown', 'status': 'error', 'error': 'Tenant not found'}],
                'success_count': 0,
                'error_count': 1
            }

    def validate_tenant_subscription(self, tenant_id):
        """Validate that tenant has an active subscription."""
        subscription = self.get_tenant_subscription(tenant_id)
        return subscription is not None

    def validate_feature_exists(self, feature_key):
        """Validate that feature exists."""
        return Feature.objects.filter(key=feature_key, is_active=True).exists()

    def get_feature_by_key(self, feature_key):
        """Get feature by key."""
        try:
            return Feature.objects.get(key=feature_key, is_active=True)
        except Feature.DoesNotExist:
            return None

    def validate_reason(self, reason):
        """Validate reason length."""
        return len(reason) <= 500

    def get_feature_override_count_for_tenant(self, tenant_id):
        """Get count of feature overrides for a tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            return TenantFeatureOverride.objects.filter(tenant=tenant).count()
        except Tenant.DoesNotExist:
            return 0

    def get_expiring_overrides(self, days_ahead=7):
        """Get feature overrides expiring within specified days."""
        from datetime import timedelta
        expiry_date = timezone.now() + timedelta(days=days_ahead)

        return TenantFeatureOverride.objects.filter(
            expires_at__lte=expiry_date,
            expires_at__gt=timezone.now()
        ).select_related("tenant", "feature").order_by("expires_at")

    def get_expired_overrides(self):
        """Get expired feature overrides."""
        return TenantFeatureOverride.objects.filter(
            expires_at__lte=timezone.now()
        ).select_related("tenant", "feature").order_by("expires_at")

    def clean_expired_overrides(self):
        """Clean up expired feature overrides."""
        expired = self.get_expired_overrides()
        count = expired.count()

        # Invalidate cache for affected tenants
        tenant_ids = expired.values_list('tenant_id', flat=True).distinct()
        for tenant_id in tenant_ids:
            cache.delete(f"{self.cache_prefix}features:{tenant_id}")

        expired.delete()
        return count

    def get_feature_usage_statistics(self, tenant_id):
        """Get feature usage statistics for a tenant."""
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_deleted=False)
            subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()

            if not subscription:
                return None

            # Get all features
            all_features = self.get_all_active_features()
            feature_stats = []

            for feature_data in all_features:
                feature_key = feature_data['key']
                is_enabled = False

                # Check if feature is enabled in plan
                plan_feature = PlanFeature.objects.filter(
                    plan=subscription.plan,
                    feature__key=feature_key
                ).first()

                if plan_feature:
                    is_enabled = plan_feature.enabled

                # Check if overridden
                override = TenantFeatureOverride.objects.filter(
                    tenant=tenant,
                    feature__key=feature_key
                ).first()

                if override:
                    is_enabled = override.enabled

                feature_stats.append({
                    'feature_key': feature_key,
                    'feature_name': feature_data['name'],
                    'enabled': is_enabled,
                    'source': 'plan' if plan_feature and plan_feature.enabled and not override else 'override' if override else 'default'
                })

            return {
                'tenant_id': str(tenant.id),
                'plan_name': subscription.plan.name,
                'total_features': len(feature_stats),
                'enabled_features': sum(1 for f in feature_stats if f['enabled']),
                'disabled_features': sum(1 for f in feature_stats if not f['enabled']),
                'features': feature_stats
            }

        except Tenant.DoesNotExist:
            return None

    def get_all_tenants_with_feature_overrides(self):
        """Get all tenants that have feature overrides."""
        return Tenant.objects.filter(
            adminfeatureoverride__isnull=False,
            is_deleted=False
        ).distinct()

    def get_tenants_without_subscription(self):
        """Get tenants that don't have an active subscription."""
        return Tenant.objects.filter(
            is_deleted=False
        ).exclude(
            admin_subscriptions__isnull=True
        ).exclude(
            admin_subscriptions__status__in=['CANCELLED', 'CHURNED', 'SUSPENDED']
        ).distinct()

    def get_feature_override_summary_by_tenant(self):
        """Get summary of feature overrides by tenant."""
        tenants = self.get_all_tenants_with_feature_overrides()
        summary = []

        for tenant in tenants:
            override_count = self.get_feature_override_count_for_tenant(str(tenant.id))
            subscription = self.get_tenant_subscription(str(tenant.id))

            summary.append({
                'tenant_id': str(tenant.id),
                'tenant_name': tenant.name,
                'override_count': override_count,
                'has_subscription': subscription is not None,
                'subscription_status': subscription.status if subscription else None,
                'subscription_plan': subscription.plan.name if subscription and subscription.plan else None,
            })

        return summary

    def search_features(self, search_term):
        """Search for features by name or key."""
        return Feature.objects.filter(
            is_active=True
        ).filter(
            Q(key__icontains=search_term) | Q(name__icontains=search_term)
        ).order_by("name").values(
            "key", "name", "description"
        )

    def get_feature_statistics(self):
        """Get overall feature statistics."""
        total_features = Feature.objects.filter(is_active=True).count()
        total_overrides = TenantFeatureOverride.objects.count()
        active_overrides = TenantFeatureOverride.objects.exclude(
            expires_at__lte=timezone.now()
        ).count()
        expired_overrides = TenantFeatureOverride.objects.filter(
            expires_at__lte=timezone.now()
        ).count()

        return {
            'total_features': total_features,
            'total_overrides': total_overrides,
            'active_overrides': active_overrides,
            'expired_overrides': expired_overrides,
            'override_rate': (total_overrides / total_features * 100) if total_features > 0 else 0
        }