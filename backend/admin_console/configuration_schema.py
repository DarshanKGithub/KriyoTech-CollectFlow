"""
Configuration schema validation and serialization.
Provides Pydantic models for configuration validation and serialization.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
class FeatureSource(str, Enum):
    """Enumeration of feature configuration sources."""
    PLAN = "plan"
    OVERRIDE = "override"
    DEFAULT = "default"
class FeatureOverrideStatus(str, Enum):
    """Enumeration of feature override statuses."""
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING = "pending"
class TenantConfiguration(BaseModel):
    """Pydantic model for tenant configuration."""

    tenant_id: str
    tenant_name: str
    subscription: Dict[str, Any]
    features: Dict[str, Dict[str, Any]]
    updated_at: str

    @validator('updated_at')
    def validate_updated_at(cls, v):
        """Validate that updated_at is a valid ISO datetime string."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("updated_at must be a valid ISO datetime string")
class FeatureOverrideCreate(BaseModel):
    """Pydantic model for creating a feature override."""

    feature_key: str = Field(..., description="The feature key to override")
    enabled: bool = Field(..., description="Whether the feature is enabled")
    limit_value: Optional[int] = Field(None, description="Feature limit value")
    limit_period: str = Field("", description="Feature limit period")
    reason: str = Field(..., description="Reason for the override")
    expires_at: Optional[str] = Field(None, description="Override expiration date (ISO format)")
    created_by: Optional[str] = Field(None, description="User who created the override")

    @validator('reason')
    def validate_reason(cls, v):
        """Validate that reason meets minimum requirements."""
        if len(v.strip()) < 8:
            raise ValueError("reason must be at least 8 characters")
        return v.strip()

    @validator('limit_value')
    def validate_limit_value(cls, v):
        """Validate limit_value if provided."""
        if v is not None and v < 0:
            raise ValueError("limit_value must be non-negative")
        return v

    @validator('expires_at')
    def validate_expires_at(cls, v):
        """Validate expires_at if provided."""
        if not v:
            return v

        try:
            expires_at = datetime.fromisoformat(v.replace('Z', '+00:00'))
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError("expires_at must be in the future")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid expires_at format: {str(e)}")
class FeatureOverrideUpdate(BaseModel):
    """Pydantic model for updating a feature override."""

    feature_key: Optional[str] = None
    enabled: Optional[bool] = None
    limit_value: Optional[int] = None
    limit_period: Optional[str] = None
    reason: Optional[str] = None
    expires_at: Optional[str] = None
    created_by: Optional[str] = None

    @validator('reason')
    def validate_reason(cls, v):
        """Validate that reason meets minimum requirements if provided."""
        if v is not None and len(v.strip()) < 8:
            raise ValueError("reason must be at least 8 characters")
        return v.strip() if v else v

    @validator('limit_value')
    def validate_limit_value(cls, v):
        """Validate limit_value if provided."""
        if v is not None and v < 0:
            raise ValueError("limit_value must be non-negative")
        return v

    @validator('expires_at')
    def validate_expires_at(cls, v):
        """Validate expires_at if provided."""
        if not v:
            return v

        try:
            expires_at = datetime.fromisoformat(v.replace('Z', '+00:00'))
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError("expires_at must be in the future")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid expires_at format: {str(e)}")
class ConfigurationDiff(BaseModel):
    """Pydantic model for configuration diff between tenants."""

    only_in_tenant1: Dict[str, Dict[str, Any]]
    only_in_tenant2: Dict[str, Dict[str, Any]]
    different_in_both: Dict[str, Dict[str, Any]]
    same_in_both: Dict[str, Dict[str, Any]]
class ConfigurationReport(BaseModel):
    """Pydantic model for configuration report."""

    tenant_id: str
    tenant_name: str
    subscription_info: Dict[str, Any]
    feature_summary: Dict[str, Any]
    detailed_features: Dict[str, Dict[str, Any]]
    configuration_age: Optional[int]
class ConfigurationHistory(BaseModel):
    """Pydantic model for configuration history."""

    tenant_id: str
    overrides: List[Dict[str, Any]]
class BulkUpdateResult(BaseModel):
    """Pydantic model for bulk update results."""

    tenant_id: str
    results: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    success_count: int
    error_count: int
    success_rate: float = Field(..., description="Success rate percentage")

    @validator('success_rate')
    def calculate_success_rate(cls, v, values):
        """Calculate success rate."""
        if 'success_count' in values and 'error_count' in values:
            total = values['success_count'] + values['error_count']
            if total > 0:
                return (values['success_count'] / total) * 100
        return 0.0
class FeatureValidationResult(BaseModel):
    """Pydantic model for feature validation results."""

    feature_key: str
    status: str
    error: Optional[str] = None
class ConfigurationError(BaseModel):
    """Pydantic model for configuration errors."""

    error_code: str
    message: str
    field: Optional[str] = None
    value: Optional[str] = None
    suggested_action: Optional[str] = None

    @classmethod
    def create(cls, error_code: str, message: str, field: Optional[str] = None,
               value: Optional[str] = None, suggested_action: Optional[str] = None):
        """Create a configuration error."""
        return cls(
            error_code=error_code,
            message=message,
            field=field,
            value=value,
            suggested_action=suggested_action
        )
class ValidationResult(BaseModel):
    """Pydantic model for validation results."""

    is_valid: bool
    errors: List[ConfigurationError]
    warnings: List[ConfigurationError]

    @classmethod
    def success(cls):
        """Create a successful validation result."""
        return cls(
            is_valid=True,
            errors=[],
            warnings=[]
        )

    @classmethod
    def failure(cls, errors: List[ConfigurationError], warnings: List[ConfigurationError] = None):
        """Create a failed validation result."""
        return cls(
            is_valid=False,
            errors=errors,
            warnings=warnings or []
        )
class ConfigurationTemplate(BaseModel):
    """Pydantic model for configuration templates."""

    name: str
    description: str
    features: Dict[str, Dict[str, Any]]
    created_by: str
    created_at: str
    is_public: bool = True
    tags: List[str] = []

    @validator('created_at')
    def validate_created_at(cls, v):
        """Validate that created_at is a valid ISO datetime string."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("created_at must be a valid ISO datetime string")
class FeatureOverrideResponse(BaseModel):
    """Pydantic model for feature override API responses."""

    feature_key: str
    enabled: bool
    override_id: str
    status: str
    created_at: str
    expires_at: Optional[str] = None
    reason: str
    limit_value: Optional[int] = None
    source: FeatureSource
    plan_name: Optional[str] = None

    @classmethod
    def from_override(cls, override):
        """Create a response from a TenantFeatureOverride model."""
        return cls(
            feature_key=override.feature.key,
            enabled=override.enabled,
            override_id=str(override.id),
            status="active" if (not override.expires_at or override.expires_at > datetime.now(timezone.utc)) else "expired",
            created_at=override.created_at.isoformat(),
            expires_at=override.expires_at.isoformat() if override.expires_at else None,
            reason=override.reason,
            limit_value=override.limit_value,
            source=FeatureSource.OVERRIDE,
            plan_name=None  # Would need to fetch plan name if needed
        )