"""Pydantic models for service APIs"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class Asset(BaseModel):
    id: str
    name: str
    type: str
    install_date: str
    location: str
    condition: str
    replacement_cost: float
    expected_life_years: int
    current_age_years: int


class RiskAnalysisRequest(BaseModel):
    asset_ids: list[str] = Field(..., description="List of asset IDs to analyze")
    horizon_months: int = Field(..., ge=1, le=120, description="Time horizon in months")


class AssetRisk(BaseModel):
    asset_id: str
    probability_of_failure: float = Field(..., ge=0.0, le=1.0)
    consequence_score: float = Field(..., ge=0.0, le=10.0)
    risk_score: float = Field(..., ge=0.0, le=10.0)
    condition_assessment: str


class RiskAnalysisResponse(BaseModel):
    analysis_id: str
    horizon_months: int
    risks: list[AssetRisk]


class InvestmentCandidate(BaseModel):
    asset_id: str
    intervention_type: str
    cost: float
    expected_risk_reduction: float = Field(..., ge=0.0, le=1.0)


class InvestmentOptimizationRequest(BaseModel):
    candidates: list[InvestmentCandidate]
    budget: float = Field(..., gt=0)
    horizon_months: int = Field(..., ge=1, le=120)


class SelectedInvestment(BaseModel):
    asset_id: str
    intervention_type: str
    cost: float
    expected_risk_reduction: float
    priority_rank: int


class InvestmentOptimizationResponse(BaseModel):
    plan_id: str
    total_budget: float
    budget_used: float
    budget_remaining: float
    selected_investments: list[SelectedInvestment]
    total_risk_reduction: float
