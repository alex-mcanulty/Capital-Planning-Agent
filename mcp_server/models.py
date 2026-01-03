"""Pydantic models for the Capital Planning MCP Server"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
from enum import Enum


def utc_now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


# ==============================================================================
# Token Session Models
# ==============================================================================

class TokenSession(BaseModel):
    """Represents an authenticated user session with token state."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User identifier (sub claim)")
    access_token: str = Field(..., description="Current access token")
    access_token_expires_at: datetime = Field(..., description="Access token expiration timestamp")
    refresh_token: str = Field(..., description="Current refresh token")
    refresh_token_expires_at: datetime = Field(..., description="Refresh token expiration timestamp")
    scopes: list[str] = Field(default_factory=list, description="Granted scopes")
    created_at: datetime = Field(default_factory=utc_now, description="Session creation time")
    last_refreshed_at: Optional[datetime] = Field(default=None, description="Last token refresh time")
    refresh_count: int = Field(default=0, description="Number of times tokens have been refreshed")


# ==============================================================================
# API Request/Response Models (matching services swagger spec)
# ==============================================================================

class Asset(BaseModel):
    """Asset data returned from the Asset Service."""
    id: str
    name: str
    type: str
    install_date: str
    location: str
    condition: str
    replacement_cost: float
    expected_life_years: int
    current_age_years: int


class InterventionOption(BaseModel):
    """A recommended intervention option for an asset."""
    intervention_type: str
    description: str
    estimated_cost: float
    expected_risk_reduction: float = Field(..., ge=0.0, le=1.0)


class AssetRisk(BaseModel):
    """Risk assessment for a single asset."""
    asset_id: str
    probability_of_failure: float = Field(..., ge=0.0, le=1.0)
    consequence_score: float = Field(..., ge=0.0, le=10.0)
    risk_score: float = Field(..., ge=0.0, le=10.0)
    condition_assessment: str
    recommended_interventions: list[InterventionOption] = Field(default_factory=list)


class RiskAnalysisResponse(BaseModel):
    """Response from the Risk Service analyze endpoint."""
    analysis_id: str
    horizon_months: int
    risks: list[AssetRisk]


class InvestmentCandidate(BaseModel):
    """A candidate investment for optimization."""
    asset_id: str
    intervention_type: str
    cost: float
    expected_risk_reduction: float = Field(..., ge=0.0, le=1.0)


class SelectedInvestment(BaseModel):
    """An investment selected by the optimization algorithm."""
    asset_id: str
    intervention_type: str
    cost: float
    expected_risk_reduction: float
    priority_rank: int


class InvestmentOptimizationResponse(BaseModel):
    """Response from the Investment Service optimize endpoint."""
    plan_id: str
    total_budget: float
    budget_used: float
    budget_remaining: float
    selected_investments: list[SelectedInvestment]
    total_risk_reduction: float


# ==============================================================================
# Tool Input Models
# ==============================================================================

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    JSON = "json"
    MARKDOWN = "markdown"


# ==============================================================================
# REST API Session Management Models
# ==============================================================================

class CreateSessionRequest(BaseModel):
    """Request body for creating a new session via REST API.
    
    This is called by the frontend/orchestrator BEFORE starting the agent.
    Tokens are passed here, not through MCP tools.
    """
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    access_token: str = Field(..., description="Access token from OIDC server")
    refresh_token: str = Field(..., description="Refresh token from OIDC server")
    expires_in: Optional[int] = Field(None, description="Access token lifetime in seconds (optional, heartbeat handles refresh)", ge=1)
    refresh_expires_in: Optional[int] = Field(None, description="Refresh token lifetime in seconds (optional, heartbeat handles refresh)", ge=1)
    scopes: list[str] = Field(default_factory=list, description="List of granted scopes")
    user_id: str = Field(..., description="User identifier (sub claim)")


class SessionResponse(BaseModel):
    """Response after creating or activating a session."""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User identifier")
    scopes: list[str] = Field(..., description="Granted scopes")
    message: str = Field(..., description="Status message")


class SessionInfoResponse(BaseModel):
    """Detailed session information response."""
    session_id: str = Field(..., description="Session identifier (truncated for security)")
    user_id: str = Field(..., description="User identifier")
    scopes: list[str] = Field(..., description="Granted scopes")
    access_token_expires_in_seconds: float = Field(..., description="Seconds until access token expires")
    refresh_token_expires_in_seconds: float = Field(..., description="Seconds until refresh token expires")
    refresh_count: int = Field(..., description="Number of token refreshes performed")
    created_at: str = Field(..., description="Session creation timestamp (ISO format)")
    last_refreshed_at: Optional[str] = Field(None, description="Last refresh timestamp (ISO format)")


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class GetAssetsInput(BaseModel):
    """Input parameters for the get_assets tool."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    portfolio_id: str = Field(
        default="default",
        description="Portfolio ID to fetch assets from (e.g., 'default', 'infrastructure-2024')",
        min_length=1,
        max_length=100
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for structured data"
    )


class GetAssetInput(BaseModel):
    """Input parameters for the get_asset tool."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    asset_id: str = Field(
        ...,
        description="Asset ID to fetch (e.g., 'asset-001', 'asset-015')",
        min_length=1,
        max_length=100
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for structured data"
    )


class AnalyzeRiskInput(BaseModel):
    """Input parameters for the analyze_risk tool."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    asset_ids: list[str] = Field(
        ...,
        description="List of asset IDs to analyze (e.g., ['asset-001', 'asset-002'])",
        min_length=1,
        max_length=100
    )
    horizon_months: int = Field(
        default=12,
        description="Time horizon for risk analysis in months (1-120)",
        ge=1,
        le=120
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for structured data"
    )


class OptimizeInvestmentsInput(BaseModel):
    """Input parameters for the optimize_investments tool."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    candidates: list[InvestmentCandidate] = Field(
        ...,
        description="List of investment candidates with asset_id, intervention_type, cost, and expected_risk_reduction",
        min_length=1
    )
    budget: float = Field(
        ...,
        description="Total budget available for investments (must be positive)",
        gt=0
    )
    horizon_months: int = Field(
        default=12,
        description="Planning horizon in months (1-120)",
        ge=1,
        le=120
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for structured data"
    )
