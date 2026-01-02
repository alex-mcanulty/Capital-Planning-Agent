"""Capital Planning MCP Server.

A stateful MCP server that provides tools for capital planning workflows:
- Asset management (list, get details)
- Risk analysis
- Investment optimization

The server manages authentication tokens transparently, refreshing them
as needed to support long-running agent workflows.
"""
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from .config import TOOL_SCOPE_REQUIREMENTS
from .models import (
    GetAssetsInput,
    GetAssetInput,
    AnalyzeRiskInput,
    OptimizeInvestmentsInput,
    InvestmentCandidate,
    ResponseFormat,
)
from .token_manager import token_manager, AuthenticationError
from .api_client import api_client
from .tools import (
    get_assets_tool,
    get_asset_tool,
    analyze_risk_tool,
    optimize_investments_tool,
    get_session_info_tool,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,  # MCP servers should log to stderr, not stdout
)
logger = logging.getLogger(__name__)


# ==============================================================================
# Lifespan Management
# ==============================================================================

@asynccontextmanager
async def app_lifespan():
    """Manage resources for the server's lifetime."""
    logger.info("[MCP Server] Starting Capital Planning MCP Server")
    
    # Initialize any startup resources
    yield {
        "token_manager": token_manager,
        "api_client": api_client,
    }
    
    # Cleanup on shutdown
    logger.info("[MCP Server] Shutting down...")
    await api_client.close()
    await token_manager.close()


# Initialize the MCP server
mcp = FastMCP(
    "capital_planning_mcp",
    lifespan=app_lifespan,
    port=8002
)


# ==============================================================================
# Session Management Resources
# ==============================================================================

# Store current session ID (in a real app, this would be per-connection)
_current_session_id: str | None = None


def set_current_session(session_id: str):
    """Set the current session ID for tool calls."""
    global _current_session_id
    _current_session_id = session_id
    logger.info(f"[MCP Server] Session set: {session_id[:8]}...")


def get_current_session() -> str:
    """Get the current session ID."""
    if not _current_session_id:
        raise AuthenticationError("No session established. Please authenticate first.")
    return _current_session_id


# ==============================================================================
# Authentication Tool (for establishing sessions)
# ==============================================================================

class AuthenticateInput(BaseModel):
    """Input for establishing an authenticated session."""
    model_config = ConfigDict(extra='forbid')
    
    access_token: str = Field(..., description="Access token from OIDC server")
    refresh_token: str = Field(..., description="Refresh token from OIDC server")
    expires_in: int = Field(..., description="Access token lifetime in seconds", ge=1)
    refresh_expires_in: int = Field(
        default=3600,
        description="Refresh token lifetime in seconds",
        ge=1
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="List of granted scopes"
    )
    user_id: str = Field(..., description="User identifier (sub claim)")


@mcp.tool(
    name="capital_authenticate",
    annotations={
        "title": "Authenticate Session",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def authenticate(params: AuthenticateInput) -> str:
    """Establish an authenticated session with the Capital Planning services.
    
    Call this tool first to set up authentication before using other tools.
    The session will be maintained and tokens will be refreshed automatically.
    
    Args:
        params: Authentication credentials including tokens and scopes
        
    Returns:
        Confirmation message with session details
    """
    session_id = await token_manager.create_session(
        access_token=params.access_token,
        refresh_token=params.refresh_token,
        expires_in=params.expires_in,
        refresh_expires_in=params.refresh_expires_in,
        scopes=params.scopes,
        user_id=params.user_id,
    )
    
    set_current_session(session_id)
    
    return f"""## Session Established

- **User**: {params.user_id}
- **Scopes**: {', '.join(params.scopes) if params.scopes else 'None'}
- **Access Token Expires In**: {params.expires_in} seconds
- **Refresh Token Expires In**: {params.refresh_expires_in} seconds

You can now use the capital planning tools. Tokens will be refreshed automatically.
"""


# ==============================================================================
# Capital Planning Tools
# ==============================================================================

@mcp.tool(
    name="capital_get_assets",
    annotations={
        "title": "Get Assets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def capital_get_assets(params: GetAssetsInput) -> str:
    """Fetch all infrastructure assets in a portfolio.
    
    Retrieves a list of infrastructure assets including their condition,
    age, location, and replacement cost. Use this as the first step to
    understand what assets are available for risk analysis.
    
    Required scope: assets:read
    
    Args:
        params: Input parameters
            - portfolio_id (str): Portfolio to fetch from (default: "default")
            - response_format (str): "markdown" or "json"
            
    Returns:
        List of assets with id, name, type, condition, age, and cost information
    """
    session_id = get_current_session()
    return await get_assets_tool(params, session_id)


@mcp.tool(
    name="capital_get_asset",
    annotations={
        "title": "Get Asset Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def capital_get_asset(params: GetAssetInput) -> str:
    """Fetch detailed information about a specific asset.
    
    Retrieves detailed information about a single infrastructure asset
    including its condition, age, expected life, and replacement cost.
    
    Required scope: assets:read
    
    Args:
        params: Input parameters
            - asset_id (str): The asset ID (e.g., "asset-001")
            - response_format (str): "markdown" or "json"
            
    Returns:
        Detailed asset information including condition and financial data
    """
    session_id = get_current_session()
    return await get_asset_tool(params, session_id)


@mcp.tool(
    name="capital_analyze_risk",
    annotations={
        "title": "Analyze Asset Risk",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def capital_analyze_risk(params: AnalyzeRiskInput) -> str:
    """Analyze failure risk for specified assets.
    
    Performs risk analysis on a list of assets over a specified time horizon.
    Returns probability of failure, consequence scores, and overall risk scores.
    Results are sorted by risk score (highest first) to identify priority assets.
    
    **Note**: This operation may take several seconds as it performs detailed
    analysis calculations. The token will be refreshed automatically if needed.
    
    Required scope: risk:analyze
    
    Args:
        params: Input parameters
            - asset_ids (list[str]): Asset IDs to analyze (e.g., ["asset-001", "asset-002"])
            - horizon_months (int): Time horizon in months (1-120, default: 12)
            - response_format (str): "markdown" or "json"
            
    Returns:
        Risk analysis with probability of failure, consequence score, and overall
        risk score for each asset, sorted by risk (highest first)
    """
    session_id = get_current_session()
    return await analyze_risk_tool(params, session_id)


@mcp.tool(
    name="capital_optimize_investments",
    annotations={
        "title": "Optimize Investment Plan",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def capital_optimize_investments(params: OptimizeInvestmentsInput) -> str:
    """Generate an optimized investment plan within budget constraints.
    
    Takes a list of investment candidates (asset interventions with costs and
    expected risk reductions) and a budget, then returns an optimized plan that
    maximizes total risk reduction within the budget.
    
    **Note**: This operation may take several seconds as it performs optimization
    calculations. The token will be refreshed automatically if needed.
    
    Required scope: investments:write
    
    Args:
        params: Input parameters
            - candidates (list): Investment options, each with:
                - asset_id (str): The asset to invest in
                - intervention_type (str): Type of intervention (e.g., "replace", "repair")
                - cost (float): Cost of the intervention
                - expected_risk_reduction (float): Expected risk reduction (0.0-1.0)
            - budget (float): Total budget available (must be positive)
            - horizon_months (int): Planning horizon in months (1-120, default: 12)
            - response_format (str): "markdown" or "json"
            
    Returns:
        Optimized investment plan with selected investments, budget usage,
        and total expected risk reduction
    """
    session_id = get_current_session()
    return await optimize_investments_tool(params, session_id)


@mcp.tool(
    name="capital_session_info",
    annotations={
        "title": "Get Session Information",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def capital_session_info() -> str:
    """Get information about the current authentication session.
    
    Returns details about the authenticated session including user ID,
    granted scopes, token expiration times, and refresh statistics.
    Useful for debugging and understanding session state.
    
    Args:
        None
        
    Returns:
        Session information including token status and refresh count
    """
    session_id = get_current_session()
    return await get_session_info_tool(session_id)


# ==============================================================================
# Server Entry Point
# ==============================================================================

def main():
    """Run the MCP server."""
    # import argparse
    
    # parser = argparse.ArgumentParser(description="Capital Planning MCP Server")
    # parser.add_argument(
    #     "--transport",
    #     choices=["stdio", "streamable-http"],
    #     default="stdio",
    #     help="Transport mechanism (default: stdio)"
    # )
    # parser.add_argument(
    #     "--port",
    #     type=int,
    #     default=8002,
    #     help="Port for HTTP transport (default: 8002)"
    # )
    
    # args = parser.parse_args()
    
    # if args.transport == "streamable-http":
    logger.info(f"[MCP Server] Starting with streamable HTTP on port 8002")
    mcp.run(transport="streamable-http")
    # else:
    #     logger.info("[MCP Server] Starting with stdio transport")
    #     mcp.run()


if __name__ == "__main__":
    main()
