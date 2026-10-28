"""
Configuration exceptions and error handling.
Provides custom exception classes for configuration management.
"""
from rest_framework.exceptions import APIException
class ConfigurationError(APIException):
    """Base exception for configuration errors."""

    status_code = 400
    default_detail = "Configuration error occurred."
    default_code = "configuration_error"
class FeatureNotFoundError(ConfigurationError):
    """Exception raised when a feature is not found."""

    default_detail = "The specified feature was not found or is inactive."
    default_code = "feature_not_found"
class InvalidFeatureKeyError(ConfigurationError):
    """Exception raised when a feature key is invalid."""

    default_detail = "The feature key is invalid or empty."
    default_code = "invalid_feature_key"
class ReasonValidationError(ConfigurationError):
    """Exception raised when a reason doesn't meet requirements."""

    default_detail = "The reason must be at least 8 characters long."
    default_code = "reason_validation_error"
class LimitValueError(ConfigurationError):
    """Exception raised when a limit value is invalid."""

    default_detail = "The limit value is invalid or negative."
    default_code = "limit_value_error"
class ExpiresAtError(ConfigurationError):
    """Exception raised when expires_at is invalid."""

    default_detail = "The expires_at value is invalid or in the past."
    default_code = "expires_at_error"
class TenantNotFoundError(ConfigurationError):
    """Exception raised when a tenant is not found."""

    status_code = 404
    default_detail = "The specified tenant was not found."
    default_code = "tenant_not_found"
class SubscriptionRequiredError(ConfigurationError):
    """Exception raised when a tenant has no active subscription."""

    default_detail = "Tenant must have an active subscription to configure features."
    default_code = "subscription_required_error"
class FeatureNotInPlanError(ConfigurationError):
    """Exception raised when a feature is not part of the current plan."""

    default_detail = "The feature is not included in the current subscription plan."
    default_code = "feature_not_in_plan_error"
class OverrideNotAllowedError(ConfigurationError):
    """Exception raised when a feature override is not allowed."""

    default_detail = "Feature override is not allowed for this tenant or feature."
    default_code = "override_not_allowed_error"
class CacheError(ConfigurationError):
    """Exception raised when cache operations fail."""

    default_detail = "Configuration cache operation failed."
    default_code = "cache_error"
class ValidationError(ConfigurationError):
    """Exception raised when configuration validation fails."""

    default_detail = "Configuration validation failed."
    default_code = "validation_error"

    def __init__(self, detail, code="validation_error"):
        self.detail = detail
        self.code = code
        super().__init__(detail=detail)
class ConfigurationConflictError(ConfigurationError):
    """Exception raised when there's a configuration conflict."""

    default_detail = "There is a conflict with existing configuration."
    default_code = "configuration_conflict_error"
class FeatureAlreadyOverriddenError(ConfigurationError):
    """Exception raised when a feature is already overridden."""

    default_detail = "The feature is already overridden and cannot be overridden again."
    default_code = "feature_already_overridden_error"
class CacheNotAvailableError(ConfigurationError):
    """Exception raised when cache is not available."""

    default_detail = "Configuration cache is not available."
    default_code = "cache_not_available_error"
class InvalidConfigurationStateError(ConfigurationError):
    """Exception raised when configuration state is invalid."""

    default_detail = "The configuration state is invalid or corrupted."
    default_code = "invalid_configuration_state_error"
class FeatureOverrideLimitExceededError(ConfigurationError):
    """Exception raised when feature override limits are exceeded."""

    default_detail = "The maximum number of feature overrides has been exceeded."
    default_code = "feature_override_limit_exceeded_error"
class TenantConfigurationLockedError(ConfigurationError):
    """Exception raised when tenant configuration is locked."""

    default_detail = "Tenant configuration is currently locked and cannot be modified."
    default_code = "tenant_configuration_locked_error"
class FeatureDependencyError(ConfigurationError):
    """Exception raised when a feature has unresolved dependencies."""

    default_detail = "The feature has unresolved dependencies that must be addressed first."
    default_code = "feature_dependency_error"
class ConfigurationTimeoutError(ConfigurationError):
    """Exception raised when configuration operations timeout."""

    status_code = 408
    default_detail = "Configuration operation timed out."
    default_code = "configuration_timeout_error"
class ConfigurationPersistenceError(ConfigurationError):
    """Exception raised when configuration persistence fails."""

    default_detail = "Failed to persist configuration changes."
    default_code = "configuration_persistence_error"
class FeatureDependencyCycleError(ConfigurationError):
    """Exception raised when a feature dependency cycle is detected."""

    default_detail = "A circular dependency was detected among features."
    default_code = "feature_dependency_cycle_error"
class TenantNotAccessibleError(ConfigurationError):
    """Exception raised when tenant access is denied."""

    status_code = 403
    default_detail = "Access to the specified tenant is denied."
    default_code = "tenant_not_accessible_error"
class FeatureConfigurationStaleError(ConfigurationError):
    """Exception raised when feature configuration is stale."""

    default_detail = "The feature configuration is stale and should be refreshed."
    default_code = "feature_configuration_stale_error"
class InvalidFeatureConfigurationError(ConfigurationError):
    """Exception raised when feature configuration is invalid."""

    default_detail = "The feature configuration is invalid."
    default_code = "invalid_feature_configuration_error"
class FeatureOverrideExpiredError(ConfigurationError):
    """Exception raised when a feature override has expired."""

    default_detail = "The feature override has expired and is no longer active."
    default_code = "feature_override_expired_error"
class FeatureOverridePendingError(ConfigurationError):
    """Exception raised when a feature override is pending."""

    default_detail = "The feature override is pending and not yet active."
    default_code = "feature_override_pending_error"
class ConfigurationReadOnlyError(ConfigurationError):
    """Exception raised when trying to modify read-only configuration."""

    default_detail = "The configuration is read-only and cannot be modified."
    default_code = "configuration_read_only_error"
class FeatureValidationError(ConfigurationError):
    """Exception raised when feature validation fails."""

    default_detail = "Feature validation failed."
    default_code = "feature_validation_error"

    def __init__(self, detail, errors=None, code="feature_validation_error"):
        self.detail = detail
        self.errors = errors or []
        self.code = code
        super().__init__(detail=detail)
class ConfigurationImportError(ConfigurationError):
    """Exception raised when configuration import fails."""

    default_detail = "Configuration import failed."
    default_code = "configuration_import_error"
class ConfigurationExportError(ConfigurationError):
    """Exception raised when configuration export fails."""

    default_detail = "Configuration export failed."
    default_code = "configuration_export_error"
class ConfigurationTemplateError(ConfigurationError):
    """Exception raised when configuration template operations fail."""

    default_detail = "Configuration template operation failed."
    default_code = "configuration_template_error"
class FeatureTemplateError(ConfigurationError):
    """Exception raised when feature template operations fail."""

    default_detail = "Feature template operation failed."
    default_code = "feature_template_error"
class ConfigurationValidationError(ConfigurationError):
    """Exception raised when configuration validation fails."""

    default_detail = "Configuration validation failed."
    default_code = "configuration_validation_error"

    def __init__(self, detail, errors=None, code="configuration_validation_error"):
        self.detail = detail
        self.errors = errors or []
        self.code = code
        super().__init__(detail=detail)
class ConfigurationStateError(ConfigurationError):
    """Exception raised when configuration state is inconsistent."""

    default_detail = "The configuration state is inconsistent."
    default_code = "configuration_state_error"
class FeatureConfigurationConflictError(ConfigurationError):
    """Exception raised when there's a feature configuration conflict."""

    default_detail = "There is a conflict with the feature configuration."
    default_code = "feature_configuration_conflict_error"
class ConfigurationMigrationError(ConfigurationError):
    """Exception raised when configuration migration fails."""

    default_detail = "Configuration migration failed."
    default_code = "configuration_migration_error"
class FeatureConfigurationParsingError(ConfigurationError):
    """Exception raised when feature configuration parsing fails."""

    default_detail = "Failed to parse feature configuration."
    default_code = "feature_configuration_parsing_error"
class ConfigurationSyncError(ConfigurationError):
    """Exception raised when configuration sync fails."""

    default_detail = "Configuration synchronization failed."
    default_code = "configuration_sync_error"
class FeatureConfigurationDiffError(ConfigurationError):
    """Exception raised when feature configuration diff fails."""

    default_detail = "Failed to generate configuration diff."
    default_code = "feature_configuration_diff_error"
class ConfigurationRollbackError(ConfigurationError):
    """Exception raised when configuration rollback fails."""

    default_detail = "Configuration rollback failed."
    default_code = "configuration_rollback_error"
class FeatureConfigurationBackupError(ConfigurationError):
    """Exception raised when feature configuration backup fails."""

    default_detail = "Feature configuration backup failed."
    default_code = "feature_configuration_backup_error"
class ConfigurationRestoreError(ConfigurationError):
    """Exception raised when configuration restore fails."""

    default_detail = "Configuration restore failed."
    default_code = "configuration_restore_error"
class FeatureConfigurationArchiveError(ConfigurationError):
    """Exception raised when feature configuration archive fails."""

    default_detail = "Feature configuration archive failed."
    default_code = "feature_configuration_archive_error"
class ConfigurationArchiveError(ConfigurationError):
    """Exception raised when configuration archive operations fail."""

    default_detail = "Configuration archive operation failed."
    default_code = "configuration_archive_error"
class FeatureConfigurationImportError(ConfigurationError):
    """Exception raised when feature configuration import fails."""

    default_detail = "Feature configuration import failed."
    default_code = "feature_configuration_import_error"
class ConfigurationExportError(ConfigurationError):
    """Exception raised when configuration export fails."""

    default_detail = "Configuration export failed."
    default_code = "configuration_export_error"
class FeatureConfigurationExportError(ConfigurationError):
    """Exception raised when feature configuration export fails."""

    default_detail = "Feature configuration export failed."
    default_code = "feature_configuration_export_error"
class ConfigurationImportValidationError(ConfigurationError):
    """Exception raised when configuration import validation fails."""

    default_detail = "Configuration import validation failed."
    default_code = "configuration_import_validation_error"
class FeatureConfigurationImportValidationError(ConfigurationError):
    """Exception raised when feature configuration import validation fails."""

    default_detail = "Feature configuration import validation failed."
    default_code = "feature_configuration_import_validation_error"
class ConfigurationExportValidationError(ConfigurationError):
    """Exception raised when configuration export validation fails."""

    default_detail = "Configuration export validation failed."
    default_code = "configuration_export_validation_error"
class FeatureConfigurationExportValidationError(ConfigurationError):
    """Exception raised when feature configuration export validation fails."""

    default_detail = "Feature configuration export validation failed."
    default_code = "feature_configuration_export_validation_error"
class ConfigurationTemplateValidationError(ConfigurationError):
    """Exception raised when configuration template validation fails."""

    default_detail = "Configuration template validation failed."
    default_code = "configuration_template_validation_error"
class FeatureTemplateValidationError(ConfigurationError):
    """Exception raised when feature template validation fails."""

    default_detail = "Feature template validation failed."
    default_code = "feature_template_validation_error"
class ConfigurationTemplateImportError(ConfigurationError):
    """Exception raised when configuration template import fails."""

    default_detail = "Configuration template import failed."
    default_code = "configuration_template_import_error"
class FeatureTemplateImportError(ConfigurationError):
    """Exception raised when feature template import fails."""

    default_detail = "Feature template import failed."
    default_code = "feature_template_import_error"
class ConfigurationTemplateExportError(ConfigurationError):
    """Exception raised when configuration template export fails."""

    default_detail = "Configuration template export failed."
    default_code = "configuration_template_export_error"
class FeatureTemplateExportError(ConfigurationError):
    """Exception raised when feature template export fails."""

    default_detail = "Feature template export failed."
    default_code = "feature_template_export_error"
class ConfigurationTemplateExportValidationError(ConfigurationError):
    """Exception raised when configuration template export validation fails."""

    default_detail = "Configuration template export validation failed."
    default_code = "configuration_template_export_validation_error"
class FeatureTemplateExportValidationError(ConfigurationError):
    """Exception raised when feature template export validation fails."""

    default_detail = "Feature template export validation failed."
    default_code = "feature_template_export_validation_error"
class ConfigurationTemplateImportValidationError(ConfigurationError):
    """Exception raised when configuration template import validation fails."""

    default_detail = "Configuration template import validation failed."
    default_code = "configuration_template_import_validation_error"
class FeatureTemplateImportValidationError(ConfigurationError):
    """Exception raised when feature template import validation fails."""

    default_detail = "Feature template import validation failed."
    default_code = "feature_template_import_validation_error"
class ConfigurationVersionError(ConfigurationError):
    """Exception raised when configuration version operations fail."""

    default_detail = "Configuration version operation failed."
    default_code = "configuration_version_error"
class FeatureConfigurationVersionError(ConfigurationError):
    """Exception raised when feature configuration version operations fail."""

    default_detail = "Feature configuration version operation failed."
    default_code = "feature_configuration_version_error"
class ConfigurationVersionValidationError(ConfigurationError):
    """Exception raised when configuration version validation fails."""

    default_detail = "Configuration version validation failed."
    default_code = "configuration_version_validation_error"
class FeatureConfigurationVersionValidationError(ConfigurationError):
    """Exception raised when feature configuration version validation fails."""

    default_detail = "Feature configuration version validation failed."
    default_code = "feature_configuration_version_validation_error"
class ConfigurationVersionImportError(ConfigurationError):
    """Exception raised when configuration version import fails."""

    default_detail = "Configuration version import failed."
    default_code = "configuration_version_import_error"
class FeatureConfigurationVersionImportError(ConfigurationError):
    """Exception raised when feature configuration version import fails."""

    default_detail = "Feature configuration version import failed."
    default_code = "feature_configuration_version_import_error"
class ConfigurationVersionExportError(ConfigurationError):
    """Exception raised when configuration version export fails."""

    default_detail = "Configuration version export failed."
    default_code = "configuration_version_export_error"
class FeatureConfigurationVersionExportError(ConfigurationError):
    """Exception raised when feature configuration version export fails."""

    default_detail = "Feature configuration version export failed."
    default_code = "feature_configuration_version_export_error"
class ConfigurationVersionValidationError(ConfigurationError):
    """Exception raised when configuration version validation fails."""

    default_detail = "Configuration version validation failed."
    default_code = "configuration_version_validation_error"
class FeatureConfigurationVersionValidationError(ConfigurationError):
    """Exception raised when feature configuration version validation fails."""

    default_detail = "Feature configuration version validation failed."
    default_code = "feature_configuration_version_validation_error"
class ConfigurationVersionImportValidationError(ConfigurationError):
    """Exception raised when configuration version import validation fails."""

    default_detail = "Configuration version import validation failed."
    default_code = "configuration_version_import_validation_error"
class FeatureConfigurationVersionImportValidationError(ConfigurationError):
    """Exception raised when feature configuration version import validation fails."""

    default_detail = "Feature configuration version import validation failed."
    default_code = "feature_configuration_version_import_validation_error"
class ConfigurationVersionExportValidationError(ConfigurationError):
    """Exception raised when configuration version export validation fails."""

    default_detail = "Configuration version export validation failed."
    default_code = "configuration_version_export_validation_error"
class FeatureConfigurationVersionExportValidationError(ConfigurationError):
    """Exception raised when feature configuration version export validation fails."""

    default_detail = "Feature configuration version export validation failed."
    default_code = "feature_configuration_version_export_validation_error"
class ConfigurationDiffError(ConfigurationError):
    """Exception raised when configuration diff operations fail."""

    default_detail = "Configuration diff operation failed."
    default_code = "configuration_diff_error"
class FeatureConfigurationDiffError(ConfigurationError):
    """Exception raised when feature configuration diff fails."""

    default_detail = "Feature configuration diff failed."
    default_code = "feature_configuration_diff_error"
class ConfigurationReportError(ConfigurationError):
    """Exception raised when configuration report operations fail."""

    default_detail = "Configuration report operation failed."
    default_code = "configuration_report_error"
class FeatureConfigurationReportError(ConfigurationError):
    """Exception raised when feature configuration report fails."""

    default_detail = "Feature configuration report failed."
    default_code = "feature_configuration_report_error"
class ConfigurationCacheError(ConfigurationError):
    """Exception raised when configuration cache operations fail."""

    default_detail = "Configuration cache operation failed."
    default_code = "configuration_cache_error"
class FeatureConfigurationCacheError(ConfigurationError):
    """Exception raised when feature configuration cache fails."""

    default_detail = "Feature configuration cache operation failed."
    default_code = "feature_configuration_cache_error"
class ConfigurationBulkUpdateError(ConfigurationError):
    """Exception raised when configuration bulk update fails."""

    default_detail = "Configuration bulk update failed."
    default_code = "configuration_bulk_update_error"
class FeatureConfigurationBulkUpdateError(ConfigurationError):
    """Exception raised when feature configuration bulk update fails."""

    default_detail = "Feature configuration bulk update failed."
    default_code = "feature_configuration_bulk_update_error"
class ConfigurationCreateError(ConfigurationError):
    """Exception raised when configuration create operations fail."""

    default_detail = "Configuration create operation failed."
    default_code = "configuration_create_error"
class FeatureConfigurationCreateError(ConfigurationError):
    """Exception raised when feature configuration create fails."""

    default_detail = "Feature configuration create failed."
    default_code = "feature_configuration_create_error"
class ConfigurationUpdateError(ConfigurationError):
    """Exception raised when configuration update fails."""

    default_detail = "Configuration update failed."
    default_code = "configuration_update_error"
class FeatureConfigurationUpdateError(ConfigurationError):
    """Exception raised when feature configuration update fails."""

    default_detail = "Feature configuration update failed."
    default_code = "feature_configuration_update_error"
class ConfigurationDeleteError(ConfigurationError):
    """Exception raised when configuration delete operations fail."""

    default_detail = "Configuration delete operation failed."
    default_code = "configuration_delete_error"
class FeatureConfigurationDeleteError(ConfigurationError):
    """Exception raised when feature configuration delete fails."""

    default_detail = "Feature configuration delete failed."
    default_code = "feature_configuration_delete_error"
class ConfigurationListError(ConfigurationError):
    """Exception raised when configuration list operations fail."""

    default_detail = "Configuration list operation failed."
    default_code = "configuration_list_error"
class FeatureConfigurationListError(ConfigurationError):
    """Exception raised when feature configuration list fails."""

    default_detail = "Feature configuration list failed."
    default_code = "feature_configuration_list_error"
class ConfigurationRetrieveError(ConfigurationError):
    """Exception raised when configuration retrieve operations fail."""

    default_detail = "Configuration retrieve operation failed."
    default_code = "configuration_retrieve_error"
class FeatureConfigurationRetrieveError(ConfigurationError):
    """Exception raised when feature configuration retrieve fails."""

    default_detail = "Feature configuration retrieve failed."
    default_code = "feature_configuration_retrieve_error"
class ConfigurationSearchError(ConfigurationError):
    """Exception raised when configuration search fails."""

    default_detail = "Configuration search failed."
    default_code = "configuration_search_error"
class FeatureConfigurationSearchError(ConfigurationError):
    """Exception raised when feature configuration search fails."""

    default_detail = "Feature configuration search failed."
    default_code = "feature_configuration_search_error"
class ConfigurationFilterError(ConfigurationError):
    """Exception raised when configuration filter operations fail."""

    default_detail = "Configuration filter operation failed."
    default_code = "configuration_filter_error"
class FeatureConfigurationFilterError(ConfigurationError):
    """Exception raised when feature configuration filter fails."""

    default_detail = "Feature configuration filter failed."
    default_code = "feature_configuration_filter_error"
class ConfigurationSortError(ConfigurationError):
    """Exception raised when configuration sort operations fail."""

    default_detail = "Configuration sort operation failed."
    default_code = "configuration_sort_error"
class FeatureConfigurationSortError(ConfigurationError):
    """Exception raised when feature configuration sort fails."""

    default_detail = "Feature configuration sort failed."
    default_code = "feature_configuration_sort_error"
class ConfigurationPaginationError(ConfigurationError):
    """Exception raised when configuration pagination fails."""

    default_detail = "Configuration pagination operation failed."
    default_code = "configuration_pagination_error"
class FeatureConfigurationPaginationError(ConfigurationError):
    """Exception raised when feature configuration pagination fails."""

    default_detail = "Feature configuration pagination failed."
    default_code = "feature_configuration_pagination_error"
class ConfigurationAuthorizationError(ConfigurationError):
    """Exception raised when configuration authorization fails."""

    default_detail = "Configuration authorization failed."
    default_code = "configuration_authorization_error"
class FeatureConfigurationAuthorizationError(ConfigurationError):
    """Exception raised when feature configuration authorization fails."""

    default_detail = "Feature configuration authorization failed."
    default_code = "feature_configuration_authorization_error"
class ConfigurationAuthenticationError(ConfigurationError):
    """Exception raised when configuration authentication fails."""

    default_detail = "Configuration authentication failed."
    default_code = "configuration_authentication_error"
class FeatureConfigurationAuthenticationError(ConfigurationError):
    """Exception raised when feature configuration authentication fails."""

    default_detail = "Feature configuration authentication failed."
    default_code = "feature_configuration_authentication_error"
class ConfigurationPermissionError(ConfigurationError):
    """Exception raised when configuration permission fails."""

    default_detail = "Configuration permission failed."
    default_code = "configuration_permission_error"
class FeatureConfigurationPermissionError(ConfigurationError):
    """Exception raised when feature configuration permission fails."""

    default_detail = "Feature configuration permission failed."
    default_code = "feature_configuration_permission_error"
class ConfigurationRateLimitError(ConfigurationError):
    """Exception raised when configuration rate limit is exceeded."""

    default_detail = "Configuration rate limit exceeded."
    default_code = "configuration_rate_limit_error"
class FeatureConfigurationRateLimitError(ConfigurationError):
    """Exception raised when feature configuration rate limit is exceeded."""

    default_detail = "Feature configuration rate limit exceeded."
    default_code = "feature_configuration_rate_limit_error"
class ConfigurationThrottlingError(ConfigurationError):
    """Exception raised when configuration throttling fails."""

    default_detail = "Configuration throttling operation failed."
    default_code = "configuration_throttling_error"
class FeatureConfigurationThrottlingError(ConfigurationError):
    """Exception raised when feature configuration throttling fails."""

    default_detail = "Feature configuration throttling failed."
    default_code = "feature_configuration_throttling_error"
class ConfigurationErrorWithDetails(ConfigurationError):
    """Exception raised when configuration error includes additional details."""

    def __init__(self, detail: str, errors: list, code: str = "configuration_error"):
        self.errors = errors
        super().__init__(detail, code)
class ConfigurationSuccess:
    """Represents a successful configuration operation."""

    @staticmethod
    def create_result(data: dict, message: str = "Operation completed successfully"):
        """Create a success result."""
        return {
            'success': True,
            'message': message,
            'data': data
        }
class ConfigurationFailure:
    """Represents a failed configuration operation."""

    @staticmethod
    def create_error(error: ConfigurationError, status_code: int = None):
        """Create a failure result."""
        result = {
            'success': False,
            'error': {
                'code': error.code,
                'message': error.detail,
                'status_code': status_code or error.status_code
            }
        }

        if hasattr(error, 'errors'):
            result['error']['details'] = error.errors

        return result
class ConfigurationValidator:
    """Configuration validator helper class."""

    @staticmethod
    def validate_feature_key(feature_key: str):
        """Validate a feature key."""
        if not feature_key or not feature_key.strip():
            raise InvalidFeatureKeyError()
        return feature_key.strip()

    @staticmethod
    def validate_reason(reason: str, min_length: int = 8):
        """Validate a reason."""
        if not reason or len(reason.strip()) < min_length:
            raise ReasonValidationError()
        return reason.strip()

    @staticmethod
    def validate_limit_value(limit_value):
        """Validate a limit value."""
        if limit_value is not None and limit_value < 0:
            raise LimitValueError()
        return limit_value

    @staticmethod
    def validate_expires_at(expires_at):
        """Validate an expires_at datetime."""
        if expires_at and expires_at <= timezone.now():
            raise ExpiresAtError()
        return expires_at

    @staticmethod
    def validate_tenant_access(tenant, requesting_user):
        """Validate tenant access."""
        if not requesting_user:
            raise ConfigurationAuthenticationError()

        if hasattr(tenant, 'is_deleted') and tenant.is_deleted:
            raise TenantNotFoundError()

        return True
class ConfigurationLogger:
    """Configuration logger helper class."""

    @staticmethod
    def log_creation(tenant_id: str, feature_key: str, user: str):
        """Log configuration creation."""
        # In a real implementation, this would log to a structured logging system
        pass

    @staticmethod
    def log_update(tenant_id: str, feature_key: str, user: str):
        """Log configuration update."""
        # In a real implementation, this would log to a structured logging system
        pass

    @staticmethod
    def log_deletion(tenant_id: str, feature_key: str, user: str):
        """Log configuration deletion."""
        # In a real implementation, this would log to a structured logging system
        pass

    @staticmethod
    def log_validation_failure(tenant_id: str, error: ConfigurationError):
        """Log configuration validation failure."""
        # In a real implementation, this would log to a structured logging system
        pass

    @staticmethod
    def log_cache_operation(operation: str, tenant_id: str, success: bool):
        """Log cache operation."""
        # In a real implementation, this would log to a structured logging system
        pass
# Export commonly used exceptions
__all__ = [
    'ConfigurationError',
    'FeatureNotFoundError',
    'InvalidFeatureKeyError',
    'ReasonValidationError',
    'LimitValueError',
    'ExpiresAtError',
    'TenantNotFoundError',
    'SubscriptionRequiredError',
    'FeatureNotInPlanError',
    'OverrideNotAllowedError',
    'CacheError',
    'ValidationError',
    'ConfigurationConflictError',
    'FeatureAlreadyOverriddenError',
    'CacheNotAvailableError',
    'InvalidConfigurationStateError',
    'FeatureOverrideLimitExceededError',
    'TenantConfigurationLockedError',
    'FeatureDependencyError',
    'ConfigurationTimeoutError',
    'ConfigurationPersistenceError',
    'FeatureDependencyCycleError',
    'TenantNotAccessibleError',
    'FeatureConfigurationStaleError',
    'InvalidFeatureConfigurationError',
    'FeatureOverrideExpiredError',
    'FeatureOverridePendingError',
    'ConfigurationReadOnlyError',
    'FeatureValidationError',
    'ConfigurationImportError',
    'ConfigurationExportError',
    'ConfigurationTemplateError',
    'FeatureTemplateError',
    'ConfigurationVersionError',
    'FeatureConfigurationVersionError',
    'ConfigurationDiffError',
    'FeatureConfigurationDiffError',
    'ConfigurationReportError',
    'FeatureConfigurationReportError',
    'ConfigurationCacheError',
    'FeatureConfigurationCacheError',
    'ConfigurationBulkUpdateError',
    'FeatureConfigurationBulkUpdateError',
    'ConfigurationCreateError',
    'FeatureConfigurationCreateError',
    'ConfigurationUpdateError',
    'FeatureConfigurationUpdateError',
    'ConfigurationDeleteError',
    'FeatureConfigurationDeleteError',
    'ConfigurationListError',
    'FeatureConfigurationListError',
    'ConfigurationRetrieveError',
    'FeatureConfigurationRetrieveError',
    'ConfigurationSearchError',
    'FeatureConfigurationSearchError',
    'ConfigurationFilterError',
    'FeatureConfigurationFilterError',
    'ConfigurationSortError',
    'FeatureConfigurationSortError',
    'ConfigurationPaginationError',
    'FeatureConfigurationPaginationError',
    'ConfigurationAuthorizationError',
    'FeatureConfigurationAuthorizationError',
    'ConfigurationAuthenticationError',
    'FeatureConfigurationAuthenticationError',
    'ConfigurationPermissionError',
    'FeatureConfigurationPermissionError',
    'ConfigurationRateLimitError',
    'FeatureConfigurationRateLimitError',
    'ConfigurationThrottlingError',
    'FeatureConfigurationThrottlingError',
    'ConfigurationErrorWithDetails',
    'ConfigurationSuccess',
    'ConfigurationFailure',
    'ConfigurationValidator',
    'ConfigurationLogger',
]