"""Capital Planning MCP Server.

A stateful MCP server that provides tools for capital planning workflows
with automatic token management and refresh.

Architecture:
- Single ASGI application serving both REST API and MCP endpoint
- REST API at /sessions/* for session management (tokens never touch MCP/agent)
- MCP endpoint at /mcp for agent tool calls
- TokenManager handles OAuth token lifecycle with automatic refresh

Run with:
    uvicorn mcp_server.main:app --port 8002
"""
from .main import (
    app,
    mcp,
    main,
    get_session_id_from_request,
)
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
    CreateSessionRequest,
    SessionResponse,
    SessionInfoResponse,
)

__all__ = [
    # ASGI Application
    "app",
    "mcp",
    "main",
    # Session management
    "get_session_id_from_request",
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
    "CreateSessionRequest",
    "SessionResponse",
    "SessionInfoResponse",
]
