"""Capital Planning MCP Server.

A stateful MCP server that provides tools for capital planning workflows
with automatic token management and refresh.
"""
from .main import mcp, main, set_current_session, get_current_session
from .token_manager import token_manager, TokenManager, AuthenticationError, AuthorizationError
from .api_client import api_client, CapitalPlanningAPIClient, APIError
from .models import (
    TokenSession,
    Asset,
    AssetRisk,
    RiskAnalysisResponse,
    InvestmentCandidate,
    SelectedInvestment,
    InvestmentOptimizationResponse,
)

__all__ = [
    # Server
    "mcp",
    "main",
    "set_current_session",
    "get_current_session",
    # Token management
    "token_manager",
    "TokenManager",
    "AuthenticationError",
    "AuthorizationError",
    # API client
    "api_client",
    "CapitalPlanningAPIClient",
    "APIError",
    # Models
    "TokenSession",
    "Asset",
    "AssetRisk",
    "RiskAnalysisResponse",
    "InvestmentCandidate",
    "SelectedInvestment",
    "InvestmentOptimizationResponse",
]
