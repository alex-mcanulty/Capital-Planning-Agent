"""Configuration for the Capital Planning MCP Server"""
import os

# OIDC Server Configuration
OIDC_SERVER_URL = os.getenv("OIDC_SERVER_URL", "http://localhost:8000")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "capital-planner-mcp")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "mcp-secret")

# Capital Planning Services Configuration
SERVICES_BASE_URL = os.getenv("SERVICES_BASE_URL", "http://localhost:8001")

# Token refresh buffer (refresh if token expires within this many seconds)
TOKEN_REFRESH_BUFFER_SECONDS = 2

# Logging
LOG_TOKEN_EVENTS = os.getenv("LOG_TOKEN_EVENTS", "true").lower() == "true"

# Scope to tool mapping - defines which scopes are required for each tool
TOOL_SCOPE_REQUIREMENTS = {
    "capital_get_assets": ["assets:read"],
    "capital_get_asset": ["assets:read"],
    "capital_analyze_risk": ["risk:analyze"],
    "capital_optimize_investments": ["investments:write"],
}
