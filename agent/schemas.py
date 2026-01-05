"""Pydantic schemas for structured output from the Capital Planning Agent.

These schemas define the structure of the agent's final response,
enabling type-safe parsing and structured display in the frontend.
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class InterventionType(str, Enum):
    """Types of interventions available for assets."""
    REPLACE = "replace"
    REHABILITATE = "rehabilitate"
    REPAIR = "repair"
    PREVENTIVE_MAINTENANCE = "preventive_maintenance"
    MONITORING = "monitoring"


class AssetRisk(BaseModel):
    """Risk assessment for a single asset."""
    asset_id: str = Field(..., description="Unique identifier for the asset")
    asset_name: str = Field(..., description="Human-readable name of the asset")
    asset_type: str = Field(..., description="Type of asset (e.g., water_main, pump_station)")
    risk_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Overall risk score from 0 (low) to 100 (critical)"
    )
    probability_of_failure: float = Field(
        ...,
        ge=0,
        le=1,
        description="Probability of failure within the analysis horizon (0-1)"
    )
    consequence_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Consequence score if failure occurs (0-100)"
    )


class RecommendedIntervention(BaseModel):
    """A recommended intervention for an asset."""
    asset_id: str = Field(..., description="Asset this intervention applies to")
    asset_name: str = Field(..., description="Name of the asset")
    intervention_type: str = Field(
        ...,
        description="Type of intervention (replace, rehabilitate, repair, preventive_maintenance, monitoring)"
    )
    description: str = Field(..., description="Description of what the intervention involves")
    estimated_cost: float = Field(..., ge=0, description="Estimated cost in dollars")
    expected_risk_reduction: float = Field(
        ...,
        ge=0,
        le=1,
        description="Expected risk reduction factor (0-1)"
    )


class SelectedInvestment(BaseModel):
    """An investment selected by the optimizer."""
    asset_id: str = Field(..., description="Asset being invested in")
    asset_name: str = Field(..., description="Name of the asset")
    intervention_type: str = Field(..., description="Type of intervention selected")
    cost: float = Field(..., ge=0, description="Cost of this investment")
    expected_risk_reduction: float = Field(
        ...,
        ge=0,
        le=1,
        description="Expected risk reduction from this investment"
    )


class InvestmentPlanSummary(BaseModel):
    """Summary of the optimized investment plan."""
    total_budget: Optional[float] = Field(
        None,
        ge=0,
        description="Total budget constraint (if specified)"
    )
    total_cost: float = Field(..., ge=0, description="Total cost of selected investments")
    budget_utilization: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Percentage of budget utilized (0-1)"
    )
    total_risk_reduction: float = Field(
        ...,
        ge=0,
        description="Total expected risk reduction across all investments"
    )
    num_assets_addressed: int = Field(
        ...,
        ge=0,
        description="Number of assets included in the plan"
    )


class CapitalPlanningResponse(BaseModel):
    """Structured response from the Capital Planning Agent.

    This schema captures the full output of a capital planning analysis,
    including risk assessment, recommendations, and investment optimization.
    """

    # Summary for the user
    summary: str = Field(
        ...,
        description="Brief executive summary of findings and recommendations (2-3 sentences)"
    )

    # Analysis parameters
    analysis_horizon_months: Optional[int] = Field(
        None,
        ge=1,
        description="Time horizon used for risk analysis in months"
    )

    # Risk assessment results
    high_risk_assets: list[AssetRisk] = Field(
        default_factory=list,
        description="List of high-risk assets identified, sorted by risk score (highest first)"
    )

    # Recommended interventions
    recommended_interventions: list[RecommendedIntervention] = Field(
        default_factory=list,
        description="Recommended interventions for high-risk assets"
    )

    # Optimized investment plan (if optimization was performed)
    investment_plan: Optional[InvestmentPlanSummary] = Field(
        None,
        description="Summary of the optimized investment plan"
    )
    selected_investments: list[SelectedInvestment] = Field(
        default_factory=list,
        description="List of investments selected by the optimizer"
    )

    # Additional insights
    key_findings: list[str] = Field(
        default_factory=list,
        description="Key findings and insights from the analysis"
    )

    # Indicates if analysis was incomplete or limited
    limitations: Optional[str] = Field(
        None,
        description="Any limitations or caveats about the analysis"
    )
