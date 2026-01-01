# Capital Planning MCP Server

A stateful MCP (Model Context Protocol) server that provides tools for capital planning workflows with **automatic token management and refresh**.

## Overview

This MCP server enables AI agents to interact with Capital Planning services (Assets, Risk Analysis, Investment Optimization) while handling OAuth2 token lifecycle transparently. The server:

- **Manages tokens stateully** — Stores access and refresh tokens per session
- **Refreshes automatically** — Checks token validity before each API call and refreshes as needed
- **Uses token rotation** — Each refresh returns a new refresh token, enabling indefinite sessions
- **Enforces authorization** — Checks user scopes before allowing tool execution

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Server (Stateful)                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Token Manager                          │  │
│  │  - Stores access_token + refresh_token per session        │  │
│  │  - Checks expiry before each API call                     │  │
│  │  - Refreshes transparently with rotation                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│           ┌──────────────────┼──────────────────┐                │
│           ▼                  ▼                  ▼                │
│    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│    │ Asset Tools │    │ Risk Tools  │    │ Investment  │        │
│    │             │    │             │    │ Tools       │        │
│    └─────────────┘    └─────────────┘    └─────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   Capital Planning Services API
```

## Tools

| Tool | Description | Required Scope |
|------|-------------|----------------|
| `capital_authenticate` | Establish authenticated session | - |
| `capital_get_assets` | List all assets in a portfolio | `assets:read` |
| `capital_get_asset` | Get details for a single asset | `assets:read` |
| `capital_analyze_risk` | Analyze risk for specified assets | `risk:analyze` |
| `capital_optimize_investments` | Generate optimized investment plan | `investments:write` |
| `capital_session_info` | Get current session status | - |

## Installation

```bash
cd mcp_server
pip install -r requirements.txt
```

## Configuration

Set environment variables or use defaults:

```bash
# OIDC Server
export OIDC_SERVER_URL="http://localhost:8000"
export OIDC_CLIENT_ID="capital-planner-mcp"
export OIDC_CLIENT_SECRET="mcp-secret"

# Capital Planning Services
export SERVICES_BASE_URL="http://localhost:8001"

# Logging
export LOG_TOKEN_EVENTS="true"
```

## Running the Server

### stdio transport (for local tools)

```bash
python -m mcp_server.main
```

### Streamable HTTP transport (for remote access)

```bash
python -m mcp_server.main --transport streamable-http --port 8002
```

## Usage Example

### 1. Authenticate

First, establish a session with tokens from your OIDC server:

```json
{
  "tool": "capital_authenticate",
  "params": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "expires_in": 10,
    "refresh_expires_in": 30,
    "scopes": ["assets:read", "risk:analyze", "investments:write"],
    "user_id": "admin_user"
  }
}
```

### 2. Get Assets

```json
{
  "tool": "capital_get_assets",
  "params": {
    "portfolio_id": "default",
    "response_format": "markdown"
  }
}
```

### 3. Analyze Risk

```json
{
  "tool": "capital_analyze_risk",
  "params": {
    "asset_ids": ["asset-001", "asset-002", "asset-003"],
    "horizon_months": 12,
    "response_format": "markdown"
  }
}
```

### 4. Optimize Investments

```json
{
  "tool": "capital_optimize_investments",
  "params": {
    "candidates": [
      {
        "asset_id": "asset-001",
        "intervention_type": "replace",
        "cost": 500000,
        "expected_risk_reduction": 0.85
      },
      {
        "asset_id": "asset-002",
        "intervention_type": "repair",
        "cost": 150000,
        "expected_risk_reduction": 0.45
      }
    ],
    "budget": 1000000,
    "horizon_months": 12,
    "response_format": "markdown"
  }
}
```

## Token Refresh Flow

The token manager handles refresh automatically:

```
Time 0s:    Session created with access_token (10s) + refresh_token (30s)
Time 8s:    API call → access_token expiring → refresh triggered
            → New access_token (10s) + NEW refresh_token (30s) stored
Time 16s:   API call → access_token expiring → refresh triggered
            → New access_token (10s) + NEW refresh_token (30s) stored
... continues indefinitely while agent is active
```

The agent never sees tokens or handles refresh. It simply calls tools.

## Error Handling

| Error Type | When | Response |
|------------|------|----------|
| `AuthenticationError` | Session not found, token invalid, refresh failed | Clear message with re-auth suggestion |
| `AuthorizationError` | User lacks required scope | Lists missing scopes and user's current scopes |
| `APIError` | Service request failed | HTTP status and error details |

## Scope Requirements

The server enforces authorization before each tool call:

```python
TOOL_SCOPE_REQUIREMENTS = {
    "capital_get_assets": ["assets:read"],
    "capital_get_asset": ["assets:read"],
    "capital_analyze_risk": ["risk:analyze"],
    "capital_optimize_investments": ["investments:write"],
}
```

A user with only `assets:read` scope will receive an authorization error when attempting to call `capital_analyze_risk`.

## Demo Users

When using the mock OIDC server:

| User | Password | Scopes |
|------|----------|--------|
| `admin_user` | `admin_pass` | `assets:read`, `risk:analyze`, `investments:write` |
| `limited_user` | `limited_pass` | `assets:read` only |

## Development

### File Structure

```
mcp_server/
├── __init__.py          # Package exports
├── main.py              # FastMCP server & tool registration
├── config.py            # Configuration constants
├── models.py            # Pydantic models
├── token_manager.py     # Stateful token lifecycle management
├── api_client.py        # HTTP client for services
├── tools.py             # Tool implementation functions
└── requirements.txt     # Dependencies
```

### Testing

Verify syntax:
```bash
python -m py_compile mcp_server/main.py
```

Test with MCP Inspector:
```bash
npx @modelcontextprotocol/inspector python -m mcp_server.main
```

## Security Considerations

1. **Token Storage**: Tokens are held in memory only. Consider encryption at rest for production.
2. **Scope Enforcement**: Authorization is checked at the MCP layer, not just the API layer.
3. **Token Rotation**: Each refresh invalidates the previous refresh token.
4. **Logging**: Token values are never logged in full (only prefixes shown).
