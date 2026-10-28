"""
Configuration service interface and utilities.
Provides service class for centralized configuration management.
"""
from .configuration import ConfigurationService
from .configuration_helpers import ConfigurationHelpers
class ConfigurationServiceInterface:
    """Interface for configuration services."""

    def __init__(self):
        self._configuration_service = ConfigurationService()
        self._helpers = ConfigurationHelpers()

    def get_feature_configuration(self, tenant):
        """Get complete feature configuration for a tenant."""
        return self._configuration_service.get_feature_configuration(tenant)

    def set_feature_override(self, tenant_or_id, feature_key, enabled, **kwargs):
        """Set a feature override for a tenant."""
        return self._configuration_service.set_feature_override(
            tenant_or_id, feature_key, enabled, **kwargs
        )

    def validate_configuration(self, tenant, feature_overrides):
        """Validate feature overrides before applying."""
        return self._configuration_service.validate_configuration(
            tenant, feature_overrides
        )

    def create_tenant_configuration(self, tenant_id, feature_overrides):
        """Create initial configuration for a new tenant."""
        return self._configuration_service.create_tenant_configuration(
            tenant_id, feature_overrides
        )

    def get_all_features(self):
        """Get all available features."""
        return self._configuration_service.get_all_features()

    def get_plan_features(self, plan_id):
        """Get features for a specific plan."""
        return self._configuration_service.get_plan_features(plan_id)

    def get_tenant_configuration_history(self, tenant_id, limit=50):
        """Get configuration change history for a tenant."""
        return self._configuration_service.get_tenant_configuration_history(
            tenant_id, limit
        )

    def bulk_update_features(self, tenant_id, updates):
        """Bulk update multiple features for a tenant."""
        return self._configuration_service.bulk_update_features(
            tenant_id, updates
        )

    def clear_cache(self, tenant_id=None):
        """Clear configuration cache."""
        return self._configuration_service.clear_cache(tenant_id)

    # Helper methods

    def validate_feature_key(self, feature_key):
        """Validate that a feature key exists and is active."""
        return self._helpers.validate_feature_key(feature_key)

    def validate_reason(self, reason):
        """Validate that reason meets minimum requirements."""
        return self._helpers.validate_reason(reason)

    def validate_limit_value(self, limit_value):
        """Validate limit_value if provided."""
        return self._helpers.validate_limit_value(limit_value)

    def validate_expires_at(self, expires_at):
        """Validate expires_at datetime if provided."""
        return self._helpers.validate_expires_at(expires_at)

    def get_effective_features(self, tenant):
        """Get all effective features for a tenant (plan + overrides)."""
        return self._helpers.get_effective_features(tenant)

    def is_feature_enabled(self, tenant, feature_key):
        """Check if a specific feature is enabled for a tenant."""
        return self._helpers.is_feature_enabled(tenant, feature_key)

    def get_feature_details(self, tenant, feature_key):
        """Get detailed information about a specific feature for a tenant."""
        return self._helpers.get_feature_details(tenant, feature_key)

    def create_feature_override(self, tenant, feature_key, enabled, **kwargs):
        """Create a feature override with full validation."""
        return self._helpers.create_feature_override(
            tenant, feature_key, enabled, **kwargs
        )

    def bulk_create_feature_overrides(self, tenant, overrides):
        """Bulk create feature overrides with batch validation and processing."""
        return self._helpers.bulk_create_feature_overrides(
            tenant, overrides
        )

    def get_feature_configuration_report(self, tenant):
        """Get a comprehensive configuration report for a tenant."""
        return self._helpers.get_feature_configuration_report(tenant)

    def validate_configuration_transition(self, tenant, changes):
        """Validate if configuration changes are allowed."""
        return self._helpers.validate_configuration_transition(
            tenant, changes
        )

    def get_configuration_diff(self, tenant1, tenant2):
        """Compare configurations between two tenants."""
        return self._helpers.get_configuration_diff(
            tenant1, tenant2
        )

    def create_feature_override_batch(self, tenant, feature_overrides):
        """Create multiple feature overrides for a tenant."""
        return self._helpers.create_feature_override_batch(
            tenant, feature_overrides
        )
# Global service instance
service = ConfigurationServiceInterface()