"""
Configuration manager for high-level configuration operations.
Combines service and repository layers for complete configuration management.
"""
from django.db.models import Q
from django.utils import timezone
from .configuration import ConfigurationService
from .configuration_repository import ConfigurationRepository
from .configuration_schema import (
    TenantConfiguration,
    FeatureOverrideCreate,
    FeatureOverrideUpdate,
    ConfigurationDiff,
    ConfigurationReport,
    ValidationResult,
    ConfigurationError,
)
from rest_framework.exceptions import ValidationError as DRFValidationError
class ConfigurationManager:
    """High-level configuration manager combining service and repository layers."""

    def __init__(self):
        self.service = ConfigurationService()
        self.repository = ConfigurationRepository()

    def get_tenant_configuration(self, tenant_id):
        """Get complete configuration for a tenant."""
        # Try service first (cached)
        try:
            tenant = self.repository.get_tenant_by_id(tenant_id)
            if tenant:
                return self.service.get_feature_configuration(tenant)
        except Exception:
            pass

        # Fall back to repository
        return self.repository.get_feature_configuration(tenant_id)

    def create_feature_override(self, tenant_id, feature_key, enabled, **kwargs):
        """Create a feature override with validation and audit."""
        # Validate input
        if not tenant_id:
            raise DRFValidationError({"error": "tenant_id is required."})

        if not feature_key:
            raise DRFValidationError({"error": "feature_key is required."})

        if enabled is None:
            raise DRFValidationError({"error": "enabled is required."})

        # Check if tenant exists
        tenant = self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            raise DRFValidationError({"error": "Tenant not found."})

        # Validate feature exists
        if not self.repository.validate_feature_exists(feature_key):
            raise DRFValidationError({"error": f"Feature '{feature_key}' not found or inactive."})

        # Validate reason
        reason = kwargs.get('reason', '')
        if len(reason.strip()) < 8:
            raise DRFValidationError({"error": "reason must be at least 8 characters."})

        # Validate limit_value
        limit_value = kwargs.get('limit_value')
        if limit_value is not None and limit_value < 0:
            raise DRFValidationError({"error": "limit_value must be non-negative."})

        # Validate expires_at
        expires_at = kwargs.get('expires_at')
        if expires_at and expires_at <= timezone.now():
            raise DRFValidationError({"error": "expires_at must be in the future."})

        # Check if feature is in current plan
        if not self.repository.validate_tenant_subscription(tenant_id):
            raise DRFValidationError({
                "error": "Tenant must have an active subscription to configure features."
            })

        # Check if feature is included in current plan
        subscription = self.repository.get_tenant_subscription(tenant_id)
        if subscription:
            feature = self.repository.get_feature_by_key(feature_key)
            if not feature:
                raise DRFValidationError({"error": f"Feature '{feature_key}' not found."})

            plan_feature = self.service.get_plan_features(subscription.plan_id)
            feature_in_plan = any(f['feature_key'] == feature_key for f in plan_feature['features'])

            if not feature_in_plan:
                raise DRFValidationError({
                    "error": f"Feature '{feature_key}' is not included in the current plan."
                })

        # Create override
        override = self.repository.create_feature_override(
            tenant=tenant,
            feature_key=feature_key,
            enabled=bool(enabled),
            limit_value=limit_value,
            reason=reason,
            expires_at=expires_at,
            created_by=kwargs.get('created_by')
        )

        return override

    def update_feature_override(self, tenant_id, override_id, updates):
        """Update an existing feature override."""
        # Validate updates
        if 'feature_key' in updates:
            if not updates['feature_key']:
                raise DRFValidationError({"error": "feature_key cannot be empty."})

        if 'reason' in updates:
            reason = updates['reason']
            if len(reason.strip()) < 8:
                raise DRFValidationError({"error": "reason must be at least 8 characters."})

        if 'limit_value' in updates:
            limit_value = updates['limit_value']
            if limit_value is not None and limit_value < 0:
                raise DRFValidationError({"error": "limit_value must be non-negative."})

        if 'expires_at' in updates:
            expires_at = updates['expires_at']
            if expires_at and expires_at <= timezone.now():
                raise DRFValidationError({"error": "expires_at must be in the future."})

        # Update override
        override = self.repository.update_feature_override(
            tenant_id=tenant_id,
            override_id=override_id,
            updates=updates,
            user=updates.get('user')
        )

        return override

    def delete_feature_override(self, tenant_id, override_id):
        """Delete a feature override."""
        return self.repository.delete_feature_override_with_audit(
            tenant_id=tenant_id,
            override_id=override_id,
            user=None  # Would need to pass the user
        )

    def get_feature_override(self, tenant_id, feature_key):
        """Get a specific feature override."""
        return self.repository.get_feature_override_by_feature(
            tenant_id=tenant_id,
            feature_key=feature_key
        )

    def get_tenant_features(self, tenant_id):
        """Get all features for a tenant with current settings."""
        config = self.get_tenant_configuration(tenant_id)
        return config.get('features', {})

    def is_feature_enabled(self, tenant_id, feature_key):
        """Check if a feature is enabled for a tenant."""
        features = self.get_tenant_features(tenant_id)
        return features.get(feature_key, {}).get('enabled', False)

    def get_feature_details(self, tenant_id, feature_key):
        """Get detailed information about a specific feature for a tenant."""
        features = self.get_tenant_features(tenant_id)
        return features.get(feature_key, {})

    def get_all_available_features(self):
        """Get all available features."""
        return self.repository.get_all_active_features()

    def get_plan_features(self, plan_id):
        """Get features for a specific plan."""
        return self.repository.get_plan_features(plan_id)

    def bulk_create_feature_overrides(self, tenant_id, overrides):
        """Bulk create feature overrides with validation."""
        # Validate tenant exists
        tenant = self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            raise DRFValidationError({"error": "Tenant not found."})

        # Validate each override
        validated_overrides = []
        for override_data in overrides:
            try:
                # Create a minimal override to validate
                temp_override = self.repository.create_feature_override(
                    tenant=tenant,
                    feature_key=override_data['feature_key'],
                    enabled=override_data['enabled'],
                    reason=override_data.get('reason', ''),
                    expires_at=override_data.get('expires_at'),
                    created_by=override_data.get('created_by')
                )
                validated_overrides.append(override_data)
            except DRFValidationError as e:
                raise DRFValidationError({
                    "error": f"Validation failed for feature '{override_data['feature_key']}': {str(e)}"
                })

        # If all validations pass, create all overrides
        return self.repository.bulk_create_feature_overrides(
            tenant_id, validated_overrides
        )

    def get_configuration_history(self, tenant_id, limit=50):
        """Get configuration change history for a tenant."""
        return self.repository.get_feature_override_history(
            tenant_id=tenant_id,
            limit=limit
        )

    def get_feature_configuration_report(self, tenant_id):
        """Get a comprehensive configuration report for a tenant."""
        features = self.get_tenant_features(tenant_id)
        subscription = self.repository.get_tenant_subscription(tenant_id)

        if not subscription:
            return None

        report = {
            'tenant_id': tenant_id,
            'tenant_name': subscription.tenant.name if hasattr(subscription, 'tenant') else None,
            'subscription_info': {
                'plan_id': str(subscription.plan_id),
                'plan_name': subscription.plan.name if subscription.plan else None,
                'status': subscription.status,
                'billing_cycle': subscription.billing_cycle,
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
            'configuration_age': (timezone.now() - subscription.created_at).days if hasattr(subscription, 'created_at') else None,
        }

        return report

    def compare_tenant_configurations(self, tenant_id1, tenant_id2):
        """Compare configurations between two tenants."""
        config1 = self.get_tenant_features(tenant_id1)
        config2 = self.get_tenant_features(tenant_id2)

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
                if features1 == features2:
                    diff['same_in_both'][feature_key] = features1
                else:
                    diff['different_in_both'][feature_key] = {
                        'tenant1': features1,
                        'tenant2': features2
                    }

        return diff

    def validate_configuration_transition(self, tenant_id, changes):
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
                # Check if feature exists
                if not self.repository.validate_feature_exists(feature_key):
                    errors.append({
                        'feature_key': feature_key,
                        'error': f"Feature '{feature_key}' not found or inactive"
                    })
                    continue

                # Check if tenant has subscription
                if not self.repository.validate_tenant_subscription(tenant_id):
                    errors.append({
                        'feature_key': feature_key,
                        'error': 'Tenant must have an active subscription'
                    })
                    continue

                # Check if feature is in current plan
                subscription = self.repository.get_tenant_subscription(tenant_id)
                if subscription:
                    plan_features = self.service.get_plan_features(subscription.plan_id)
                    feature_in_plan = any(f['feature_key'] == feature_key for f in plan_features['features'])

                    if not feature_in_plan:
                        errors.append({
                            'feature_key': feature_key,
                            'error': f"Feature '{feature_key}' is not included in the current plan"
                        })

            except Exception as e:
                errors.append({
                    'feature_key': feature_key,
                    'error': f"Unexpected error: {str(e)}"
                })

        return errors

    def create_feature_override_batch(self, tenant_id, overrides):
        """Create multiple feature overrides with batch validation."""
        # Validate tenant exists
        tenant = self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            raise DRFValidationError({"error": "Tenant not found."})

        # Use repository for bulk creation
        return self.repository.bulk_create_feature_overrides(
            tenant_id, overrides
        )

    def get_expiring_overrides(self, days_ahead=7):
        """Get feature overrides expiring within specified days."""
        return self.repository.get_expiring_overrides(days_ahead)

    def get_expired_overrides(self):
        """Get expired feature overrides."""
        return self.repository.get_expired_overrides()

    def clean_expired_overrides(self):
        """Clean up expired feature overrides."""
        return self.repository.clean_expired_overrides()

    def get_feature_statistics(self, tenant_id):
        """Get feature statistics for a tenant."""
        return self.repository.get_feature_usage_statistics(tenant_id)

    def get_all_tenants_with_overrides(self):
        """Get all tenants that have feature overrides."""
        return self.repository.get_all_tenants_with_feature_overrides()

    def get_tenants_without_subscription(self):
        """Get tenants that don't have an active subscription."""
        return self.repository.get_tenants_without_subscription()

    def get_feature_override_summary(self):
        """Get summary of feature overrides by tenant."""
        return self.repository.get_feature_override_summary_by_tenant()

    def search_features(self, search_term):
        """Search for features by name or key."""
        return self.repository.search_features(search_term)

    def get_overall_feature_statistics(self):
        """Get overall feature statistics."""
        return self.repository.get_feature_statistics()

    def validate_configuration_for_tenant(self, tenant_id):
        """Validate configuration for a tenant."""
        errors = []
        warnings = []

        # Check if tenant exists
        tenant = self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            errors.append({
                'code': 'TENANT_NOT_FOUND',
                'message': 'Tenant not found',
                'field': 'tenant_id'
            })
            return ValidationResult.failure(
                [ConfigurationError.create('TENANT_NOT_FOUND', 'Tenant not found', 'tenant_id')],
                [ConfigurationError.create('TENANT_ACCESS_ISSUE', 'Tenant access issue', 'tenant_id', 'not_found')]
            )

        # Check if tenant has subscription
        if not self.repository.validate_tenant_subscription(tenant_id):
            warnings.append({
                'code': 'NO_SUBSCRIPTION',
                'message': 'Tenant does not have an active subscription',
                'field': 'subscription'
            })

        # Get feature count
        features = self.get_tenant_features(tenant_id)
        total_features = len(features)
        enabled_features = sum(1 for f in features.values() if f.get('enabled', False))

        if total_features == 0:
            warnings.append({
                'code': 'NO_FEATURES_CONFIGURED',
                'message': 'No features are configured for this tenant',
                'field': 'features'
            })

        # Check for orphaned overrides
        overrides = self.repository.get_feature_overrides_for_tenant(tenant_id)
        for override in overrides:
            feature_key = override.feature.key
            # Check if feature is still active
            if not self.repository.validate_feature_exists(feature_key):
                warnings.append({
                    'code': 'ORPHANED_OVERRIDE',
                    'message': f"Feature override for inactive feature '{feature_key}'",
                    'field': 'feature_overrides'
                })

        if not errors and not warnings:
            return ValidationResult.success()

        # Convert warnings to ConfigurationError objects
        warning_errors = [
            ConfigurationError.create(w['code'], w['message'], w['field'])
            for w in warnings
        ]

        error_objects = [
            ConfigurationError.create(e['code'], e['message'], e['field'], e.get('value'))
            for e in errors
        ]

        return ValidationResult.failure(error_objects, warning_errors)

    def create_tenant_configuration_complete(self, tenant_id, configuration_data):
        """Create complete configuration for a tenant with full validation."""
        # Validate tenant exists
        tenant = self.repository.get_tenant_by_id(tenant_id)
        if not tenant:
            raise DRFValidationError({"error": "Tenant not found."})

        # Validate configuration data
        validation_result = self.validate_configuration_for_tenant(tenant_id)
        if not validation_result.is_valid:
            raise DRFValidationError({
                "errors": [
                    {
                        'error': error.message,
                        'code': error.code,
                        'field': error.field
                    }
                    for error in validation_result.errors
                ]
            })

        # Apply configuration (for now, just validate)
        # In a real implementation, this would apply all feature overrides
        # from the configuration_data

        return {
            'tenant_id': tenant_id,
            'status': 'validated',
            'warnings': [
                {
                    'code': warning.code,
                    'message': warning.message,
                    'field': warning.field
                }
                for warning in validation_result.warnings
            ]
        }

    def export_tenant_configuration(self, tenant_id, format='json'):
        """Export tenant configuration."""
        config = self.get_tenant_configuration(tenant_id)
        if not config:
            raise DRFValidationError({"error": "Configuration not found."})

        if format == 'json':
            import json
            return json.dumps(config, indent=2, default=str)
        elif format == 'csv':
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(['Feature Key', 'Enabled', 'Source', 'Limit Value', 'Limit Period'])

            # Write data
            for feature_key, feature_data in config.get('features', {}).items():
                writer.writerow([
                    feature_key,
                    feature_data.get('enabled', False),
                    feature_data.get('source', 'unknown'),
                    feature_data.get('limit_value', ''),
                    feature_data.get('limit_period', '')
                ])

            return output.getvalue()
        else:
            raise DRFValidationError({"error": f"Unsupported export format: {format}"})

    def import_tenant_configuration(self, tenant_id, configuration_data, format='json'):
        """Import tenant configuration."""
        # For now, just validate that configuration is in the right format
        # In a real implementation, this would parse the configuration and apply it

        if format == 'json':
            import json
            try:
                data = json.loads(configuration_data)
                # Validate structure
                if 'features' not in data:
                    raise DRFValidationError({"error": "Invalid configuration format: missing 'features' field"})

                return {
                    'tenant_id': tenant_id,
                    'status': 'imported',
                    'features_count': len(data['features'])
                }
            except json.JSONDecodeError as e:
                raise DRFValidationError({"error": f"Invalid JSON format: {str(e)}"})

        elif format == 'csv':
            import csv
            import io

            reader = csv.DictReader(io.StringIO(configuration_data))
            features = {}

            for row in reader:
                features[row['Feature Key']] = {
                    'enabled': row.get('Enabled', '').lower() in ('true', '1', 'yes'),
                    'source': 'import',
                    'limit_value': row.get('Limit Value', ''),
                    'limit_period': row.get('Limit Period', '')
                }

            return {
                'tenant_id': tenant_id,
                'status': 'imported',
                'features_count': len(features)
            }

        else:
            raise DRFValidationError({"error": f"Unsupported import format: {format}"})