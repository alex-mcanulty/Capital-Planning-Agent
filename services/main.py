"""FastAPI Mock Services for Capital Planning"""
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import secrets
from typing import Optional

from .config import ENDPOINT_DELAYS
from .models import (
    Asset, RiskAnalysisRequest, RiskAnalysisResponse, AssetRisk,
    InvestmentOptimizationRequest, InvestmentOptimizationResponse, SelectedInvestment
)
from .mock_data import (
    get_assets_by_portfolio, get_asset_by_id,
    calculate_mock_risk, optimize_mock_investments
)
from .auth import verify_token, require_scope

app = FastAPI(title="Capital Planning Services")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "capital-planning-services"}


# ============================================================================
# Asset Service Endpoints
# ============================================================================

@app.get("/assets", response_model=list[Asset])
async def get_assets(
    portfolio_id: str = Query(default="default"),
    token_payload: dict = Depends(require_scope("assets:read"))
):
    """Get all assets in a portfolio"""
    print(f"[Services] GET /assets - User: {token_payload.get('sub')}")

    # Artificial delay
    await asyncio.sleep(ENDPOINT_DELAYS["get_assets"])

    assets = get_assets_by_portfolio(portfolio_id)
    print(f"[Services] Returning {len(assets)} assets")

    return assets


@app.get("/assets/{asset_id}", response_model=Asset)
async def get_asset(
    asset_id: str,
    token_payload: dict = Depends(require_scope("assets:read"))
):
    """Get a single asset by ID"""
    print(f"[Services] GET /assets/{asset_id} - User: {token_payload.get('sub')}")

    # Artificial delay
    await asyncio.sleep(ENDPOINT_DELAYS["get_asset"])

    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")

    return asset


# ============================================================================
# Risk Service Endpoints
# ============================================================================

@app.post("/risk/analyze", response_model=RiskAnalysisResponse)
async def analyze_risk(
    request: RiskAnalysisRequest,
    token_payload: dict = Depends(require_scope("risk:analyze"))
):
    """Analyze risk for given assets"""
    print(f"[Services] POST /risk/analyze - User: {token_payload.get('sub')}")
    print(f"[Services] Analyzing {len(request.asset_ids)} assets over {request.horizon_months} months")

    # Artificial delay (longer than access token lifetime!)
    print(f"[Services] Simulating analysis delay of {ENDPOINT_DELAYS['analyze_risk']}s...")
    await asyncio.sleep(ENDPOINT_DELAYS["analyze_risk"])

    # Calculate risk for each asset
    risks = []
    for asset_id in request.asset_ids:
        asset = get_asset_by_id(asset_id)
        if asset:
            risk_data = calculate_mock_risk(asset, request.horizon_months)
            risks.append(AssetRisk(
                asset_id=asset_id,
                **risk_data
            ))

    analysis_id = f"risk-analysis-{secrets.token_urlsafe(8)}"

    print(f"[Services] Risk analysis complete: {analysis_id}")

    return RiskAnalysisResponse(
        analysis_id=analysis_id,
        horizon_months=request.horizon_months,
        risks=risks
    )


# ============================================================================
# Investment Service Endpoints
# ============================================================================

@app.post("/investments/optimize", response_model=InvestmentOptimizationResponse)
async def optimize_investments(
    request: InvestmentOptimizationRequest,
    token_payload: dict = Depends(require_scope("investments:write"))
):
    """Optimize investment plan"""
    print(f"[Services] POST /investments/optimize - User: {token_payload.get('sub')}")
    print(f"[Services] Optimizing {len(request.candidates)} candidates with budget ${request.budget:,.2f}")

    # Artificial delay (longer than access token lifetime!)
    print(f"[Services] Simulating optimization delay of {ENDPOINT_DELAYS['optimize_investments']}s...")
    await asyncio.sleep(ENDPOINT_DELAYS["optimize_investments"])

    # Run optimization
    result = optimize_mock_investments(
        request.candidates,
        request.budget,
        request.horizon_months
    )

    plan_id = f"investment-plan-{secrets.token_urlsafe(8)}"

    print(f"[Services] Optimization complete: {plan_id}")
    print(f"[Services] Selected {len(result['selected_investments'])} investments, using ${result['budget_used']:,.2f}")

    return InvestmentOptimizationResponse(
        plan_id=plan_id,
        total_budget=request.budget,
        budget_used=result["budget_used"],
        budget_remaining=result["budget_remaining"],
        selected_investments=[SelectedInvestment(**inv) for inv in result["selected_investments"]],
        total_risk_reduction=result["total_risk_reduction"]
    )


if __name__ == "__main__":
    import uvicorn
    print("[Services] Starting Capital Planning Services on port 8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
