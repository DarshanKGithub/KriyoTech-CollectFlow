"""
Configuration helper utilities for admin console.
Provides high-level configuration management functions and validation.
"""
from django.db.models import Q
from django.utils import timezone
from .models import Feature, PlanFeature, TenantFeatureOverride
from .configuration import config_service
from rest_framework.exceptions import ValidationError
class ConfigurationHelpers:
    """High-level configuration helpers."""

    @staticmethod
    def validate_feature_key(feature_key):
        """Validate that a feature key exists and is active."""
        if not feature_key:
            raise ValidationError({"error": "feature_key is required."})

        feature = Feature.objects.filter(key=feature_key, is_active=True).first()
        if not feature:
            raise ValidationError({"error": f"Feature '{feature_key}' not found or inactive."})

        return feature

    @staticmethod
    def validate_reason(reason):
        """Validate that reason meets minimum requirements."""
        if not reason or len(reason.strip()) < 8:
            raise ValidationError({"error": "reason must be at least 8 characters."})
        return reason.strip()

    @staticmethod
    def validate_limit_value(limit_value):
        """Validate limit_value if provided."""
        if limit_value is None:
            return None

        try:
            limit_value = int(limit_value)
            if limit_value < 0:
                raise ValidationError({"error": "limit_value must be non-negative."})
            return limit_value
        except (ValueError, TypeError):
            raise ValidationError({"error": "limit_value must be an integer."})

    @staticmethod
    def validate_expires_at(expires_at):
        """Validate expires_at datetime if provided."""
        if not expires_at:
            return None

        from django.utils.dateparse import parse_datetime
        if isinstance(expires_at, str):
            expires_at = parse_datetime(expires_at)

        if not expires_at or timezone.is_naive(expires_at):
            raise ValidationError({"error": "expires_at must be a valid datetime with timezone."})

        if expires_at <= timezone.now():
            raise ValidationError({"error": "expires_at must be in the future."})

        return expires_at

    @staticmethod
    def get_effective_features(tenant):
        """Get all effective features for a tenant (plan + overrides)."""
        config = config_service.get_feature_configuration(tenant)
        return config.get('features', {})

    @staticmethod
    def is_feature_enabled(tenant, feature_key):
        """Check if a specific feature is enabled for a tenant."""
        features = ConfigurationHelpers.get_effective_features(tenant)
        return features.get(feature_key, {}).get('enabled', False)

    @staticmethod
    def get_feature_details(tenant, feature_key):
        """Get detailed information about a specific feature for a tenant."""
        features = ConfigurationHelpers.get_effective_features(tenant)
        return features.get(feature_key, {})

    @staticmethod
    def validate_feature_override_compatibility(tenant, feature_key, enabled):
        """Validate if a feature override is compatible with tenant state."""
        from tenants.models import Tenant

        # Get tenant subscription
        subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        if not subscription:
            raise ValidationError({"error": "Tenant must have an active subscription."})

        # Check if feature is part of current plan
        feature = ConfigurationHelpers.validate_feature_key(feature_key)
        plan_feature = PlanFeature.objects.filter(plan=subscription.plan, feature=feature).first()

        if not plan_feature:
            raise ValidationError({
                "error": f"Feature '{feature_key}' is not included in the current plan."
            })

        # Special validation for disabling features
        if not enabled:
            # Check if there are other overrides for this feature
            other_overrides = TenantFeatureOverride.objects.filter(
                tenant=tenant, feature=feature
            ).exclude(enabled=True).count()

            if other_overrides > 0:
                raise ValidationError({
                    "error": f"Cannot disable '{feature_key}' - other active overrides exist."
                })

        return True

    @staticmethod
    def create_feature_override(tenant, feature_key, enabled, **kwargs):
        """Create a feature override with full validation."""
        # Validate feature
        feature = ConfigurationHelpers.validate_feature_key(feature_key)

        # Validate override compatibility
        ConfigurationHelpers.validate_feature_override_compatibility(tenant, feature_key, enabled)

        # Validate parameters
        reason = ConfigurationHelpers.validate_reason(kwargs.get('reason', ''))
        limit_value = ConfigurationHelpers.validate_limit_value(kwargs.get('limit_value'))
        expires_at = ConfigurationHelpers.validate_expires_at(kwargs.get('expires_at'))

        # Create override
        override = config_service.set_feature_override(
            tenant=tenant,
            feature_key=feature_key,
            enabled=enabled,
            limit_value=limit_value,
            reason=reason,
            expires_at=expires_at,
            created_by=kwargs.get('created_by')
        )

        return override

    @staticmethod
    def bulk_create_feature_overrides(tenant, overrides):
        """Bulk create feature overrides with batch validation and processing."""
        results = []
        errors = []

        for override_data in overrides:
            try:
                override = ConfigurationHelpers.create_feature_override(
                    tenant=tenant,
                    **override_data
                )
                results.append({
                    'feature_key': override_data['feature_key'],
                    'status': 'success',
                    'override_id': str(override.id)
                })
            except ValidationError as e:
                errors.append({
                    'feature_key': override_data['feature_key'],
                    'status': 'error',
                    'error': str(e.detail[0]['error']) if isinstance(e.detail, list) else str(e)
                })
            except Exception as e:
                errors.append({
                    'feature_key': override_data['feature_key'],
                    'status': 'error',
                    'error': f"Unexpected error: {str(e)}"
                })

        return {
            'tenant_id': str(tenant.id),
            'results': results,
            'errors': errors,
            'success_count': len(results),
            'error_count': len(errors)
        }

    @staticmethod
    def get_feature_configuration_report(tenant):
        """Get a comprehensive configuration report for a tenant."""
        features = ConfigurationHelpers.get_effective_features(tenant)
        subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()

        report = {
            'tenant_id': str(tenant.id),
            'tenant_name': tenant.name,
            'subscription_info': {
                'plan_id': str(subscription.id) if subscription else None,
                'plan_name': subscription.plan.name if subscription and subscription.plan else None,
                'status': subscription.status if subscription else None,
                'billing_cycle': subscription.billing_cycle if subscription else None,
            },
            'feature_summary': {
                'total_features': len(features),
                'enabled_features': sum(1 for f in features.values() if f.get('enabled', False)),
                'disabled_features': sum(1 for f in features.values() if not f.get('enabled', False)),
                'overridden_features': sum(1 for f in features.values() if f.get('source') == 'override'),
                'plan_only_features': sum(1 for f in features.values() if f.get('source') == 'plan'),
                'default_features': sum(1 for f in features.values() if f.get('source') == 'default'),
            },
            'detailed_features': features,
            'configuration_age': (timezone.now() - tenant.created_at).days if hasattr(tenant, 'created_at') else None,
        }

        return report

    @staticmethod
    def validate_configuration_transition(tenant, changes):
        """Validate if configuration changes are allowed."""
        errors = []

        for change in changes:
            feature_key = change.get('feature_key')
            enabled = change.get('enabled')

            if not feature_key or enabled is None:
                errors.append({
                    'feature_key': feature_key or 'unknown',
                    'error': 'Both feature_key and enabled are required'
                })
                continue

            try:
                ConfigurationHelpers.validate_feature_override_compatibility(tenant, feature_key, enabled)
            except ValidationError as e:
                errors.append({
                    'feature_key': feature_key,
                    'error': str(e.detail[0]['error']) if isinstance(e.detail, list) else str(e)
                })

        return errors

    @staticmethod
    def get_configuration_diff(tenant1, tenant2):
        """Compare configurations between two tenants."""
        config1 = ConfigurationHelpers.get_effective_features(tenant1)
        config2 = ConfigurationHelpers.get_effective_features(tenant2)

        diff = {
            'only_in_tenant1': {},
            'only_in_tenant2': {},
            'different_in_both': {},
            'same_in_both': {}
        }

        all_features = set(config1.keys()) | set(config2.keys())

        for feature_key in all_features:
            features1 = config1.get(feature_key, {})
            features2 = config2.get(feature_key, {})

            if feature_key in config1 and feature_key not in config2:
                diff['only_in_tenant1'][feature_key] = features1
            elif feature_key not in config1 and feature_key in config2:
                diff['only_in_tenant2'][feature_key] = features2
            else:
                # Both have the feature, check if they're the same
                if features1 == features2:
                    diff['same_in_both'][feature_key] = features1
                else:
                    diff['different_in_both'][feature_key] = {
                        'tenant1': features1,
                        'tenant2': features2
                    }

        return diff

    @staticmethod
    def create_feature_override_batch(tenant, feature_overrides):
        """Create multiple feature overrides for a tenant."""
        results = []
        errors = []

        for override_data in feature_overrides:
            try:
                override = ConfigurationHelpers.create_feature_override(
                    tenant=tenant,
                    **override_data
                )
                results.append({
                    'feature_key': override_data['feature_key'],
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
            'tenant_id': str(tenant.id),
            'results': results,
            'errors': errors,
            'success_count': len(results),
            'error_count': len(errors)
        }
# Global instance
helpers = ConfigurationHelpers()