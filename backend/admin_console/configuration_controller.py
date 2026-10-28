"""
Configuration controller for REST API endpoints.
Handles HTTP requests and responses for configuration management.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .configuration_manager import ConfigurationManager
from .configuration_schema import (
    FeatureOverrideCreate,
    FeatureOverrideUpdate,
    ConfigurationDiff,
    ConfigurationReport,
    ValidationResult,
    ConfigurationError,
    TenantConfiguration,
)
from .configuration_exceptions import (
    FeatureNotFoundError,
    InvalidFeatureKeyError,
    ReasonValidationError,
    LimitValueError,
    ExpiresAtError,
    TenantNotFoundError,
    SubscriptionRequiredError,
    FeatureNotInPlanError,
    OverrideNotAllowedError,
    CacheError,
    ConfigurationErrorWithDetails,
)
@method_decorator(csrf_exempt, name='dispatch')
class FeatureOverrideController(APIView):
    """Controller for feature override operations."""

    permission_classes = [IsAuthenticated]

    def __init__(self):
        self.manager = ConfigurationManager()

    def get(self, request, tenant_id=None, feature_key=None):
        """Get feature configuration(s)."""
        try:
            if tenant_id:
                if feature_key:
                    # Get specific feature for tenant
                    enabled = self.manager.is_feature_enabled(tenant_id, feature_key)
                    details = self.manager.get_feature_details(tenant_id, feature_key)
                    return Response({
                        'tenant_id': tenant_id,
                        'feature_key': feature_key,
                        'enabled': enabled,
                        'details': details
                    })
                else:
                    # Get all features for tenant
                    features = self.manager.get_tenant_features(tenant_id)
                    return Response({
                        'tenant_id': tenant_id,
                        'features': features,
                        'total_count': len(features)
                    })
            else:
                # Get all available features
                features = self.manager.get_all_available_features()
                return Response({
                    'features': features,
                    'total_count': len(features)
                })

        except FeatureNotFoundError as e:
            return Response(
                {'error': str(e), 'code': e.code},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': 'An unexpected error occurred.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request, tenant_id=None):
        """Create a feature override."""
        try:
            # Parse and validate request data
            data = request.data

            if not tenant_id:
                return Response(
                    {'error': 'tenant_id is required.', 'code': 'MISSING_TENANT_ID'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate required fields
            if not data.get('feature_key'):
                return Response(
                    {'error': 'feature_key is required.', 'code': 'MISSING_FEATURE_KEY'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if data.get('enabled') is None:
                return Response(
                    {'error': 'enabled is required.', 'code': 'MISSING_ENABLED'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create feature override
            override = self.manager.create_feature_override(
                tenant_id=tenant_id,
                feature_key=data['feature_key'],
                enabled=data['enabled'],
                reason=data.get('reason', ''),
                limit_value=data.get('limit_value'),
                limit_period=data.get('limit_period', ''),
                expires_at=data.get('expires_at'),
                created_by=request.user
            )

            return Response({
                'feature_key': override.feature.key,
                'enabled': override.enabled,
                'override_id': str(override.id),
                'status': 'created',
                'created_at': override.created_at.isoformat() if hasattr(override, 'created_at') else None
            }, status=status.HTTP_201_CREATED)

        except (FeatureNotFoundError, InvalidFeatureKeyError, ReasonValidationError,
                LimitValueError, ExpiresAtError, TenantNotFoundError, SubscriptionRequiredError,
                FeatureNotInPlanError) as e:
            return Response(
                {'error': str(e), 'code': e.code},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': 'Failed to create feature override.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, tenant_id, feature_key):
        """Update an existing feature override."""
        try:
            # Validate request data
            updates = request.data

            if not updates:
                return Response(
                    {'error': 'No updates provided.', 'code': 'NO_UPDATES'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update feature override
            override = self.manager.update_feature_override(
                tenant_id=tenant_id,
                feature_key=feature_key,
                updates=updates,
                user=request.user
            )

            if not override:
                return Response(
                    {'error': 'Feature override not found.', 'code': 'OVERRIDE_NOT_FOUND'},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response({
                'feature_key': override.feature.key,
                'enabled': override.enabled,
                'override_id': str(override.id),
                'status': 'updated',
                'updated_at': override.updated_at.isoformat() if hasattr(override, 'updated_at') else None
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to update feature override.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, tenant_id, feature_key):
        """Delete a feature override."""
        try:
            # Get the override first
            override = self.manager.get_feature_override(tenant_id, feature_key)

            if not override:
                return Response(
                    {'error': 'Feature override not found.', 'code': 'OVERRIDE_NOT_FOUND'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Delete the override
            success = self.manager.delete_feature_override(
                tenant_id=tenant_id,
                feature_key=feature_key
            )

            if success:
                return Response({
                    'message': 'Feature override deleted successfully.',
                    'feature_key': feature_key,
                    'tenant_id': tenant_id
                })
            else:
                return Response(
                    {'error': 'Failed to delete feature override.', 'code': 'DELETE_FAILED'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            return Response(
                {'error': 'Failed to delete feature override.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class TenantConfigurationController(APIView):
    """Controller for tenant configuration operations."""

    permission_classes = [IsAuthenticated]

    def __init__(self):
        self.manager = ConfigurationManager()

    def get(self, request, tenant_id):
        """Get complete configuration for a tenant."""
        try:
            config = self.manager.get_tenant_configuration(tenant_id)

            if not config:
                return Response(
                    {'error': 'Configuration not found.', 'code': 'CONFIG_NOT_FOUND'},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response(config)

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve configuration.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, tenant_id):
        """Update tenant configuration."""
        try:
            updates = request.data.get('updates', [])

            if not updates:
                return Response(
                    {'error': 'No updates provided.', 'code': 'NO_UPDATES'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate each update
            validation_errors = self.manager.validate_configuration_transition(
                tenant_id, updates
            )

            if validation_errors:
                return Response(
                    {
                        'error': 'Configuration validation failed.',
                        'errors': validation_errors,
                        'code': 'VALIDATION_FAILED'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Apply updates
            results = self.manager.bulk_create_feature_overrides(
                tenant_id, updates
            )

            if results['error_count'] > 0:
                return Response(
                    {
                        'message': f'Partial success: {results["success_count"]} succeeded, {results["error_count"]} failed.',
                        'results': results['results'],
                        'errors': results['errors'],
                        'code': 'PARTIAL_SUCCESS'
                    },
                    status=status.HTTP_207_MULTI_STATUS
                )

            return Response({
                'tenant_id': tenant_id,
                'success_count': results['success_count'],
                'status': 'completed'
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to update tenant configuration.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request, tenant_id):
        """Create configuration for a tenant."""
        try:
            configuration_data = request.data

            if not configuration_data:
                return Response(
                    {'error': 'Configuration data is required.', 'code': 'MISSING_CONFIGURATION_DATA'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create configuration
            result = self.manager.create_tenant_configuration_complete(
                tenant_id, configuration_data
            )

            return Response(result, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': 'Failed to create tenant configuration.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_configuration_report(self, request, tenant_id):
        """Get configuration report for a tenant."""
        try:
            report = self.manager.get_feature_configuration_report(tenant_id)

            if not report:
                return Response(
                    {'error': 'Report not found.', 'code': 'REPORT_NOT_FOUND'},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response(report)

        except Exception as e:
            return Response(
                {'error': 'Failed to generate configuration report.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class ConfigurationComparisonController(APIView):
    """Controller for configuration comparison operations."""

    permission_classes = [IsAuthenticated]

    def __init__(self):
        self.manager = ConfigurationManager()

    def compare_tenants(self, request, tenant_id1, tenant_id2):
        """Compare configurations between two tenants."""
        try:
            diff = self.manager.compare_tenant_configurations(
                tenant_id1, tenant_id2
            )

            return Response({
                'tenant_id_1': tenant_id1,
                'tenant_id_2': tenant_id2,
                'diff': diff,
                'summary': {
                    'features_only_in_first': len(diff['only_in_tenant1']),
                    'features_only_in_second': len(diff['only_in_tenant2']),
                    'different_in_both': len(diff['different_in_both']),
                    'same_in_both': len(diff['same_in_both'])
                }
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to compare configurations.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class ConfigurationAnalyticsController(APIView):
    """Controller for configuration analytics operations."""

    permission_classes = [IsAuthenticated]

    def __init__(self):
        self.manager = ConfigurationManager()

    def get_feature_statistics(self, request):
        """Get feature usage statistics."""
        try:
            stats = self.manager.get_overall_feature_statistics()
            return Response(stats)

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve feature statistics.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_tenants_with_overrides(self, request):
        """Get tenants that have feature overrides."""
        try:
            tenants = self.manager.get_all_tenants_with_overrides()

            return Response({
                'total_tenants': len(tenants),
                'tenants': [
                    {
                        'tenant_id': str(tenant.id),
                        'tenant_name': tenant.name,
                        'override_count': self.manager.repository.get_feature_override_count_for_tenant(str(tenant.id))
                    }
                    for tenant in tenants
                ]
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve tenants with overrides.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_tenants_without_subscription(self, request):
        """Get tenants that don't have an active subscription."""
        try:
            tenants = self.manager.get_tenants_without_subscription()

            return Response({
                'total_tenants': len(tenants),
                'tenants': [
                    {
                        'tenant_id': str(tenant.id),
                        'tenant_name': tenant.name
                    }
                    for tenant in tenants
                ]
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve tenants without subscription.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_feature_override_summary(self, request):
        """Get summary of feature overrides."""
        try:
            summary = self.manager.get_feature_override_summary()

            return Response(summary)

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve feature override summary.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def search_features(self, request):
        """Search for features."""
        search_term = request.query_params.get('q', '')

        if not search_term:
            return Response(
                {'error': 'Search term is required.', 'code': 'MISSING_SEARCH_TERM'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            features = self.manager.search_features(search_term)

            return Response({
                'search_term': search_term,
                'features': features,
                'total_count': len(features)
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to search features.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class ConfigurationMonitoringController(APIView):
    """Controller for configuration monitoring operations."""

    permission_classes = [IsAuthenticated]

    def __init__(self):
        self.manager = ConfigurationManager()

    def get_expiring_overrides(self, request):
        """Get expiring feature overrides."""
        try:
            days_ahead = int(request.query_params.get('days', '7'))
            overrides = self.manager.get_expiring_overrides(days_ahead)

            return Response({
                'days_ahead': days_ahead,
                'total_expiring': overrides.count(),
                'overrides': [
                    {
                        'override_id': str(override.id),
                        'tenant_id': str(override.tenant_id),
                        'tenant_name': override.tenant.name if hasattr(override, 'tenant') else None,
                        'feature_key': override.feature.key if hasattr(override, 'feature') else None,
                        'expires_at': override.expires_at.isoformat() if override.expires_at else None,
                        'reason': override.reason if hasattr(override, 'reason') else None
                    }
                    for override in overrides
                ]
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve expiring overrides.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_expired_overrides(self, request):
        """Get expired feature overrides."""
        try:
            overrides = self.manager.get_expired_overrides()

            return Response({
                'total_expired': overrides.count(),
                'overrides': [
                    {
                        'override_id': str(override.id),
                        'tenant_id': str(override.tenant_id),
                        'tenant_name': override.tenant.name if hasattr(override, 'tenant') else None,
                        'feature_key': override.feature.key if hasattr(override, 'feature') else None,
                        'expired_at': override.expires_at.isoformat() if override.expires_at else None,
                        'reason': override.reason if hasattr(override, 'reason') else None
                    }
                    for override in overrides
                ]
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve expired overrides.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def clean_expired_overrides(self, request):
        """Clean up expired feature overrides."""
        try:
            count = self.manager.clean_expired_overrides()

            return Response({
                'cleaned_count': count,
                'status': 'completed'
            })

        except Exception as e:
            return Response(
                {'error': 'Failed to clean expired overrides.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_feature_usage_report(self, request, tenant_id):
        """Get feature usage report for a tenant."""
        try:
            report = self.manager.get_feature_statistics(tenant_id)

            if not report:
                return Response(
                    {'error': 'Feature usage report not found.', 'code': 'REPORT_NOT_FOUND'},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response(report)

        except Exception as e:
            return Response(
                {'error': 'Failed to retrieve feature usage report.', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )