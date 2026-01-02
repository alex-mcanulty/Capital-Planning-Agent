"""MCP Tools for Capital Planning.

This module defines the tools that the agent can use to interact with
the Capital Planning services. Each tool:
- Validates inputs using Pydantic models
- Checks user authorization
- Calls the appropriate API endpoint
- Formats the response in markdown or JSON
"""
import json
from typing import Annotated
import logging

from .models import (
    ResponseFormat,
    GetAssetsInput,
    GetAssetInput,
    AnalyzeRiskInput,
    OptimizeInvestmentsInput,
    Asset,
    AssetRisk,
    RiskAnalysisResponse,
    InvestmentCandidate,
    InvestmentOptimizationResponse,
)
from .api_client import api_client, APIError
from .token_manager import token_manager, AuthenticationError, AuthorizationError

logger = logging.getLogger(__name__)


# ==============================================================================
# Response Formatting Helpers
# ==============================================================================

def format_asset_markdown(asset: Asset) -> str:
    """Format a single asset as markdown."""
    return f"""### {asset.name}
- **ID**: {asset.id}
- **Type**: {asset.type.replace('_', ' ').title()}
- **Location**: {asset.location}
- **Condition**: {asset.condition.title()}
- **Install Date**: {asset.install_date}
- **Age**: {asset.current_age_years} years (expected life: {asset.expected_life_years} years)
- **Replacement Cost**: ${asset.replacement_cost:,.2f}
"""


def format_assets_markdown(assets: list[Asset]) -> str:
    """Format a list of assets as markdown."""
    if not assets:
        return "No assets found."
    
    lines = [f"## Assets ({len(assets)} total)\n"]
    for asset in assets:
        lines.append(format_asset_markdown(asset))
    return "\n".join(lines)


def format_risk_markdown(risk: AssetRisk) -> str:
    """Format a single risk assessment as markdown."""
    lines = [
        f"### Asset: {risk.asset_id}",
        f"- **Risk Score**: {risk.risk_score:.2f}/10.0",
        f"- **Probability of Failure**: {risk.probability_of_failure:.1%}",
        f"- **Consequence Score**: {risk.consequence_score:.2f}/10.0",
        f"- **Condition**: {risk.condition_assessment.title()}"
    ]

    if risk.recommended_interventions:
        lines.append("\n**Recommended Interventions:**")
        for i, intervention in enumerate(risk.recommended_interventions, 1):
            lines.append(f"{i}. **{intervention.intervention_type.replace('_', ' ').title()}**")
            lines.append(f"   - Description: {intervention.description}")
            lines.append(f"   - Estimated Cost: ${intervention.estimated_cost:,.2f}")
            lines.append(f"   - Expected Risk Reduction: {intervention.expected_risk_reduction:.1%}")

    return "\n".join(lines) + "\n"


def format_risk_analysis_markdown(response: RiskAnalysisResponse) -> str:
    """Format a risk analysis response as markdown."""
    lines = [
        f"## Risk Analysis: {response.analysis_id}",
        f"**Horizon**: {response.horizon_months} months\n",
        f"### Risk Assessments ({len(response.risks)} assets)\n"
    ]
    
    # Sort by risk score descending
    sorted_risks = sorted(response.risks, key=lambda r: r.risk_score, reverse=True)
    
    for risk in sorted_risks:
        lines.append(format_risk_markdown(risk))
    
    return "\n".join(lines)


def format_investment_plan_markdown(response: InvestmentOptimizationResponse) -> str:
    """Format an investment optimization response as markdown."""
    lines = [
        f"## Investment Plan: {response.plan_id}",
        f"- **Total Budget**: ${response.total_budget:,.2f}",
        f"- **Budget Used**: ${response.budget_used:,.2f}",
        f"- **Budget Remaining**: ${response.budget_remaining:,.2f}",
        f"- **Total Risk Reduction**: {response.total_risk_reduction:.2%}\n",
        f"### Selected Investments ({len(response.selected_investments)} items)\n"
    ]
    
    for inv in response.selected_investments:
        lines.append(f"""#### Priority {inv.priority_rank}: {inv.asset_id}
- **Intervention**: {inv.intervention_type.replace('_', ' ').title()}
- **Cost**: ${inv.cost:,.2f}
- **Expected Risk Reduction**: {inv.expected_risk_reduction:.1%}
""")
    
    return "\n".join(lines)


def handle_error(e: Exception) -> str:
    """Format an error as a helpful message."""
    if isinstance(e, AuthenticationError):
        return f"**Authentication Error**: {e}\n\nThe session may have expired. Please re-authenticate."
    elif isinstance(e, AuthorizationError):
        return f"**Authorization Error**: {e}\n\nThe user does not have permission for this operation."
    elif isinstance(e, APIError):
        if e.status_code == 404:
            return f"**Not Found**: {e}\n\nPlease check that the resource ID is correct."
        return f"**API Error**: {e}"
    else:
        return f"**Unexpected Error**: {type(e).__name__}: {e}"


# ==============================================================================
# Tool Functions (to be registered with MCP server)
# ==============================================================================

async def get_assets_tool(params: GetAssetsInput, session_id: str) -> str:
    """Fetch all assets in a portfolio.
    
    Retrieves a list of infrastructure assets including their condition,
    age, location, and replacement cost. Use this as the first step to
    understand what assets are available for analysis.
    
    Args:
        params: Input parameters including portfolio_id and response_format
        session_id: The authenticated session ID
        
    Returns:
        List of assets in markdown or JSON format
    """
    try:
        assets = await api_client.get_assets(
            session_id=session_id,
            portfolio_id=params.portfolio_id
        )
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps([a.model_dump() for a in assets], indent=2)
        else:
            return format_assets_markdown(assets)
            
    except Exception as e:
        logger.error(f"[Tools] get_assets failed: {e}")
        return handle_error(e)


async def get_asset_tool(params: GetAssetInput, session_id: str) -> str:
    """Fetch details for a single asset.
    
    Retrieves detailed information about a specific infrastructure asset
    including its condition, age, expected life, and replacement cost.
    
    Args:
        params: Input parameters including asset_id and response_format
        session_id: The authenticated session ID
        
    Returns:
        Asset details in markdown or JSON format
    """
    try:
        asset = await api_client.get_asset(
            session_id=session_id,
            asset_id=params.asset_id
        )
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(asset.model_dump(), indent=2)
        else:
            return f"## Asset Details\n\n{format_asset_markdown(asset)}"
            
    except Exception as e:
        logger.error(f"[Tools] get_asset failed: {e}")
        return handle_error(e)


async def analyze_risk_tool(params: AnalyzeRiskInput, session_id: str) -> str:
    """Analyze failure risk for specified assets.
    
    Performs risk analysis on a list of assets over a specified time horizon.
    Returns probability of failure, consequence scores, and overall risk scores.
    Use this to identify which assets are at highest risk of failure.
    
    **Note**: This operation may take several seconds to complete as it performs
    detailed analysis calculations.
    
    Args:
        params: Input parameters including asset_ids, horizon_months, and response_format
        session_id: The authenticated session ID
        
    Returns:
        Risk analysis results in markdown or JSON format, sorted by risk score
    """
    try:
        response = await api_client.analyze_risk(
            session_id=session_id,
            asset_ids=params.asset_ids,
            horizon_months=params.horizon_months
        )
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(response.model_dump(), indent=2)
        else:
            return format_risk_analysis_markdown(response)
            
    except Exception as e:
        logger.error(f"[Tools] analyze_risk failed: {e}")
        return handle_error(e)


async def optimize_investments_tool(params: OptimizeInvestmentsInput, session_id: str) -> str:
    """Generate an optimized investment plan.
    
    Takes a list of investment candidates (asset interventions with costs and
    expected risk reductions) and a budget, then returns an optimized plan that
    maximizes risk reduction within budget constraints.
    
    **Note**: This operation may take several seconds to complete as it performs
    optimization calculations.
    
    Args:
        params: Input parameters including candidates, budget, horizon_months, and response_format
        session_id: The authenticated session ID
        
    Returns:
        Optimized investment plan in markdown or JSON format
    """
    try:
        response = await api_client.optimize_investments(
            session_id=session_id,
            candidates=params.candidates,
            budget=params.budget,
            horizon_months=params.horizon_months
        )
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(response.model_dump(), indent=2)
        else:
            return format_investment_plan_markdown(response)
            
    except Exception as e:
        logger.error(f"[Tools] optimize_investments failed: {e}")
        return handle_error(e)


# ==============================================================================
# Session Management Tools
# ==============================================================================

async def get_session_info_tool(session_id: str) -> str:
    """Get information about the current session.
    
    Returns details about the authenticated session including user ID,
    granted scopes, token expiration times, and refresh statistics.
    Useful for debugging and understanding session state.
    
    Args:
        session_id: The authenticated session ID
        
    Returns:
        Session information in markdown format
    """
    try:
        stats = token_manager.get_session_stats(session_id)
        
        if "error" in stats:
            return f"**Error**: {stats['error']}"
        
        return f"""## Session Information

- **Session ID**: {stats['session_id']}
- **User ID**: {stats['user_id']}
- **Scopes**: {', '.join(stats['scopes'])}
- **Access Token Expires In**: {stats['access_token_expires_in_seconds']:.1f} seconds
- **Refresh Token Expires In**: {stats['refresh_token_expires_in_seconds']:.1f} seconds
- **Token Refresh Count**: {stats['refresh_count']}
- **Session Created**: {stats['created_at']}
- **Last Refreshed**: {stats['last_refreshed_at'] or 'Never'}
"""
    except Exception as e:
        logger.error(f"[Tools] get_session_info failed: {e}")
        return handle_error(e)
