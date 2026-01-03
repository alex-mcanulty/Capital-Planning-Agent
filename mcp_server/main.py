"""Capital Planning MCP Server.

A stateful MCP server that provides tools for capital planning workflows:
- Asset management (list, get details)
- Risk analysis
- Investment optimization

Architecture:
- Single ASGI application serving both REST API and MCP endpoint
- REST API at /sessions/* for session management (tokens never touch MCP/agent)
- MCP endpoint at /mcp for agent tool calls
- TokenManager handles OAuth token lifecycle with automatic refresh
- Global heartbeat refreshes tokens for all sessions to prevent expiration

Run with:
    uvicorn mcp_server.main:app --port 8002

Or:
    python -m mcp_server.main
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

from .config import TOOL_SCOPE_REQUIREMENTS, TOKEN_REFRESH_HEARTBEAT_SECONDS
from .models import (
    GetAssetsInput,
    GetAssetInput,
    AnalyzeRiskInput,
    OptimizeInvestmentsInput,
    CreateSessionRequest,
    SessionResponse,
    SessionInfoResponse,
    ErrorResponse,
)
from .token_manager import token_manager, AuthenticationError, AuthorizationError
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
# Session State Management
# ==============================================================================

class SessionManager:
    """Manages the active session for MCP tool calls.
    
    This is separate from TokenManager - it just tracks WHICH session
    is currently active for the MCP server to use.
    """
    
    def __init__(self):
        self._active_session_id: Optional[str] = None
    
    def set_active_session(self, session_id: str) -> None:
        """Set the active session for MCP tools."""
        # Verify session exists
        session = token_manager.get_session(session_id)
        if not session:
            raise AuthenticationError(f"Session not found: {session_id[:16]}...")
        
        self._active_session_id = session_id
        logger.info(f"[SessionManager] Active session set: {session_id[:16]}... (user: {session.user_id})")
    
    def get_active_session(self) -> str:
        """Get the active session ID.
        
        Raises:
            AuthenticationError: If no session is active
        """
        if not self._active_session_id:
            raise AuthenticationError(
                "No active session. The frontend must create and activate a session "
                "via POST /sessions and POST /sessions/{id}/activate before using tools."
            )
        return self._active_session_id
    
    def clear_active_session(self) -> None:
        """Clear the active session."""
        self._active_session_id = None
        logger.info("[SessionManager] Active session cleared")
    
    @property
    def has_active_session(self) -> bool:
        """Check if there's an active session."""
        return self._active_session_id is not None


# Global session manager
session_manager = SessionManager()


# ==============================================================================
# MCP Server (tools only, no auth)
# ==============================================================================

# Create MCP server with stateless_http=True
# Our TokenManager handles application-level session state, so we don't need
# MCP protocol-level session state. This simplifies mounting into FastAPI.
# Set streamable_http_path to "/streamable" so we can mount the app at "/mcp"
# making the endpoint accessible at /mcp/streamable
mcp = FastMCP(
    "capital_planning_mcp",
    stateless_http=True,
    streamable_http_path="/streamable"
)


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
    session_id = session_manager.get_active_session()
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
    session_id = session_manager.get_active_session()
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
    analysis calculations.
    
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
    session_id = session_manager.get_active_session()
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
    calculations.
    
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
    session_id = session_manager.get_active_session()
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
    
    Returns:
        Session information including token status and refresh count
    """
    session_id = session_manager.get_active_session()
    return await get_session_info_tool(session_id)


# ==============================================================================
# Token Refresh Heartbeat
# ==============================================================================

# Global heartbeat task reference
_heartbeat_task: Optional[asyncio.Task] = None


async def token_refresh_heartbeat():
    """Background task that periodically refreshes tokens for all sessions.

    This runs independently of tool calls to ensure tokens don't expire
    during long-running workflows or long-duration individual tool calls.
    """
    logger.info(
        f"[Heartbeat] Token refresh heartbeat started "
        f"(interval: {TOKEN_REFRESH_HEARTBEAT_SECONDS}s)"
    )

    try:
        while True:
            await asyncio.sleep(TOKEN_REFRESH_HEARTBEAT_SECONDS)

            try:
                stats = await token_manager.refresh_all_sessions()

                if stats["total_sessions"] > 0:
                    logger.info(
                        f"[Heartbeat] Refresh cycle complete: "
                        f"total={stats['total_sessions']}, "
                        f"refreshed={stats['refreshed']}, "
                        f"failed={stats['failed']}"
                    )

                    if stats["failed"] > 0:
                        logger.warning(
                            f"[Heartbeat] {stats['failed']} session(s) failed to refresh: "
                            f"{stats['errors']}"
                        )

            except Exception as e:
                logger.error(f"[Heartbeat] Error during refresh cycle: {e}", exc_info=True)
                # Don't crash the heartbeat - log and continue

    except asyncio.CancelledError:
        logger.info("[Heartbeat] Token refresh heartbeat stopped")
        raise


# ==============================================================================
# Combined ASGI Application (REST + MCP)
# ==============================================================================

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Combined lifespan for REST API and MCP server.

    The MCP session manager must be started for streamable HTTP to work.
    Our TokenManager/SessionManager are initialized at module level.
    Starts the global token refresh heartbeat.
    """
    global _heartbeat_task

    logger.info("[Server] Starting Capital Planning API + MCP Server")

    # Start the token refresh heartbeat
    _heartbeat_task = asyncio.create_task(token_refresh_heartbeat())
    logger.info("[Server] Token refresh heartbeat task started")

    # Start MCP's session manager (required for streamable HTTP transport)
    async with mcp.session_manager.run():
        yield

    # Cleanup on shutdown
    logger.info("[Server] Shutting down...")

    # Cancel the heartbeat task
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await asyncio.wait_for(_heartbeat_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    await api_client.close()
    await token_manager.close()


# Create the combined FastAPI application
app = FastAPI(
    title="Capital Planning API",
    description=(
        "REST API for session management + MCP endpoint for agent tools.\n\n"
        "- **REST API**: `/sessions/*` - Create and manage authentication sessions\n"
        "- **MCP Endpoint**: `/mcp` - Agent tool access via Model Context Protocol"
    ),
    version="1.0.0",
    lifespan=app_lifespan,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP streamable HTTP app at /mcp
# With streamable_http_path="/streamable", the full endpoint will be /mcp/streamable
from starlette.routing import Mount
app.routes.append(Mount("/mcp", app=mcp.streamable_http_app()))


# ==============================================================================
# REST API Endpoints (Session Management)
# ==============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "capital-planning-mcp",
        "has_active_session": session_manager.has_active_session,
    }


@app.post(
    "/sessions",
    response_model=SessionResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Create a new session",
    description="Create an authenticated session from OIDC tokens. Call this BEFORE starting the agent.",
    tags=["Sessions"],
)
async def create_session(request: CreateSessionRequest):
    """Create a new authenticated session.

    The frontend calls this endpoint with tokens obtained from the OIDC server.
    This keeps tokens out of the agent/LLM conversation entirely.
    """
    try:
        logger.info(f"[REST API] Creating session for user: {request.user_id}, scopes: {request.scopes}")

        session_id = await token_manager.create_session(
            access_token=request.access_token,
            refresh_token=request.refresh_token,
            expires_in=request.expires_in or 1,  # Default to 1s, heartbeat will refresh
            refresh_expires_in=request.refresh_expires_in or 3600,  # Default to 1h
            scopes=request.scopes,
            user_id=request.user_id,
        )

        return SessionResponse(
            session_id=session_id,
            user_id=request.user_id,
            scopes=request.scopes,
            message="Session created successfully. Call POST /sessions/{session_id}/activate to use it.",
        )
    except Exception as e:
        logger.error(f"[REST API] Failed to create session: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/sessions/{session_id}/activate",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Activate a session for MCP tools",
    description="Set the specified session as the active session. MCP tools will use this session.",
    tags=["Sessions"],
)
async def activate_session(session_id: str):
    """Activate a session for use by MCP tools.
    
    After creating a session, call this endpoint to make it the active
    session. All subsequent MCP tool calls will use this session.
    """
    try:
        session_manager.set_active_session(session_id)
        session = token_manager.get_session(session_id)
        
        return SessionResponse(
            session_id=session_id,
            user_id=session.user_id,
            scopes=session.scopes,
            message="Session activated. MCP tools will now use this session.",
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[REST API] Failed to activate session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/sessions/{session_id}",
    response_model=SessionInfoResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get session information",
    description="Get detailed information about a session including token expiry times.",
    tags=["Sessions"],
)
async def get_session_info(session_id: str):
    """Get information about a session."""
    stats = token_manager.get_session_stats(session_id)
    
    if "error" in stats:
        raise HTTPException(status_code=404, detail=stats["error"])
    
    return SessionInfoResponse(
        session_id=stats["session_id"],
        user_id=stats["user_id"],
        scopes=stats["scopes"],
        access_token_expires_in_seconds=stats["access_token_expires_in_seconds"],
        refresh_token_expires_in_seconds=stats["refresh_token_expires_in_seconds"],
        refresh_count=stats["refresh_count"],
        created_at=stats["created_at"],
        last_refreshed_at=stats["last_refreshed_at"],
    )


@app.delete(
    "/sessions/{session_id}",
    summary="Delete a session",
    description="Delete a session and clear it if it was active.",
    tags=["Sessions"],
)
async def delete_session(session_id: str):
    """Delete a session (logout)."""
    # Clear if this was the active session
    try:
        if session_manager.has_active_session and session_manager.get_active_session() == session_id:
            session_manager.clear_active_session()
    except AuthenticationError:
        pass
    
    deleted = token_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Session deleted"}


@app.get(
    "/sessions/active/info",
    response_model=SessionInfoResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get active session information",
    description="Get information about the currently active session.",
    tags=["Sessions"],
)
async def get_active_session_info():
    """Get information about the active session."""
    try:
        session_id = session_manager.get_active_session()
        stats = token_manager.get_session_stats(session_id)
        
        return SessionInfoResponse(
            session_id=stats["session_id"],
            user_id=stats["user_id"],
            scopes=stats["scopes"],
            access_token_expires_in_seconds=stats["access_token_expires_in_seconds"],
            refresh_token_expires_in_seconds=stats["refresh_token_expires_in_seconds"],
            refresh_count=stats["refresh_count"],
            created_at=stats["created_at"],
            last_refreshed_at=stats["last_refreshed_at"],
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==============================================================================
# Entry Point
# ==============================================================================

def main():
    """Run the server with uvicorn."""
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description="Capital Planning MCP Server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="Port to bind to (default: 8002)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    
    args = parser.parse_args()
    
    logger.info(f"[Server] Starting on {args.host}:{args.port}")
    logger.info(f"[Server] REST API: http://{args.host}:{args.port}/sessions")
    logger.info(f"[Server] MCP Endpoint: http://{args.host}:{args.port}/mcp")
    logger.info(f"[Server] API Docs: http://{args.host}:{args.port}/docs")
    
    uvicorn.run(
        "mcp_server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
