# Capital Planning MCP Server

A stateful MCP (Model Context Protocol) server that provides tools for capital planning workflows with **automatic token management and refresh**.

## Key Design Principle

**Tokens never touch the agent/LLM.**

Sessions are created and activated via REST API endpoints *before* the agent starts. The agent only sees the domain tools (assets, risk, investments) — authentication is handled entirely out-of-band.

## Architecture

A single ASGI application serves both the REST API and MCP endpoint:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Single ASGI Application (FastAPI)                         │
│                         uvicorn mcp_server.main:app                          │
│                                                                              │
│   ┌─────────────────────────────────┐  ┌──────────────────────────────────┐  │
│   │         REST API                │  │         MCP Server               │  │
│   │        /sessions/*              │  │           /mcp                   │  │
│   │                                 │  │                                  │  │
│   │  POST /sessions                 │  │  capital_get_assets              │  │
│   │  POST /sessions/{id}/activate   │  │  capital_get_asset               │  │
│   │  GET  /sessions/{id}            │  │  capital_analyze_risk            │  │
│   │  DELETE /sessions/{id}          │  │  capital_optimize_investments    │  │
│   │  GET  /sessions/active/info     │  │  capital_session_info            │  │
│   │  GET  /health                   │  │                                  │  │
│   └────────────────┬────────────────┘  └───────────────┬──────────────────┘  │
│                    │                                   │                     │
│                    └───────────────┬───────────────────┘                     │
│                                    │                                         │
│                    ┌───────────────▼───────────────┐                         │
│                    │       SessionManager          │                         │
│                    │   (tracks active session)     │                         │
│                    └───────────────┬───────────────┘                         │
│                                    │                                         │
│                    ┌───────────────▼───────────────┐                         │
│                    │        TokenManager           │                         │
│                    │  (auto-refresh with rotation) │                         │
│                    └───────────────────────────────┘                         │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                      Capital Planning Services API
```

## Endpoints

### REST API (Session Management)

Called by the frontend to manage authentication — tokens never reach the agent.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sessions` | POST | Create session from OIDC tokens |
| `/sessions/{id}/activate` | POST | Set session as active for MCP tools |
| `/sessions/{id}` | GET | Get session info (token expiry, refresh count) |
| `/sessions/{id}` | DELETE | Delete session (logout) |
| `/sessions/active/info` | GET | Get active session info |
| `/health` | GET | Health check |
| `/docs` | GET | OpenAPI documentation (Swagger UI) |

### MCP Endpoint (Agent Tools)

Called by the agent via Model Context Protocol at `/mcp`.

| Tool | Description | Required Scope |
|------|-------------|----------------|
| `capital_get_assets` | List all assets in a portfolio | `assets:read` |
| `capital_get_asset` | Get details for a single asset | `assets:read` |
| `capital_analyze_risk` | Analyze risk for specified assets | `risk:analyze` |
| `capital_optimize_investments` | Generate optimized investment plan | `investments:write` |
| `capital_session_info` | Get current session status | - |

**Note:** None of these tools take authentication parameters. They automatically use the active session.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

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

## Running

Single command serves both REST API and MCP:

```bash
# Using uvicorn directly
uvicorn mcp_server.main:app --port 8002

# Or using the module
python -m mcp_server.main --port 8002

# With auto-reload for development
python -m mcp_server.main --port 8002 --reload
```

Once running:
- **REST API**: `http://localhost:8002/sessions`
- **MCP Endpoint**: `http://localhost:8002/mcp`
- **API Docs**: `http://localhost:8002/docs`

## Usage Flow

### Step 1: Frontend obtains tokens from OIDC server

```bash
# (handled by your OIDC flow)
```

### Step 2: Frontend creates session

```bash
curl -X POST http://localhost:8002/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "expires_in": 10,
    "refresh_expires_in": 30,
    "scopes": ["assets:read", "risk:analyze", "investments:write"],
    "user_id": "admin_user"
  }'

# Response: {"session_id": "abc123...", "user_id": "admin_user", ...}
```

### Step 3: Frontend activates session

```bash
curl -X POST http://localhost:8002/sessions/abc123.../activate

# Response: {"message": "Session activated. MCP tools will now use this session."}
```

### Step 4: Agent uses tools (no auth needed!)

The agent connects to `http://localhost:8002/mcp` and calls tools without any authentication parameters:

```json
{
  "tool": "capital_get_assets",
  "params": {
    "portfolio_id": "default",
    "response_format": "markdown"
  }
}
```

The token refresh happens automatically and transparently.

## Token Refresh Flow

```
Time 0s:    Session created with access_token (10s) + refresh_token (30s)
Time 8s:    Tool call → access_token expiring → auto-refresh triggered
            → New access_token (10s) + NEW refresh_token (30s) stored
Time 16s:   Tool call → access_token expiring → auto-refresh triggered
            → New access_token (10s) + NEW refresh_token (30s) stored
... continues indefinitely while agent is active
```

The agent never sees this happening.

## Authorization Enforcement

The server checks user scopes before each tool call:

```python
TOOL_SCOPE_REQUIREMENTS = {
    "capital_get_assets": ["assets:read"],
    "capital_get_asset": ["assets:read"],
    "capital_analyze_risk": ["risk:analyze"],
    "capital_optimize_investments": ["investments:write"],
}
```

A user with only `assets:read` will get a clear error when calling `capital_analyze_risk`:

```
**Authorization Error**: Access denied: User lacks required scope(s): ['risk:analyze']. User has: ['assets:read']
```

## Test Users (with mock OIDC server)

| User | Password | Scopes |
|------|----------|--------|
| `admin_user` | `admin_pass` | `assets:read`, `risk:analyze`, `investments:write` |
| `limited_user` | `limited_pass` | `assets:read` only |

## File Structure

```
mcp_server/
├── __init__.py          # Package exports
├── main.py              # Combined ASGI app (REST + MCP)
├── config.py            # Configuration constants
├── models.py            # Pydantic models (API + tools)
├── token_manager.py     # Stateful token lifecycle with rotation
├── api_client.py        # HTTP client for Capital Planning services
├── tools.py             # Tool implementation with formatting
└── requirements.txt     # Dependencies
```

## Security Notes

1. **Tokens isolated from agent** — Tokens only exist in REST API calls, never in MCP tool calls or LLM context.

2. **Scope enforcement at MCP layer** — Authorization checked before API calls, not just at the service layer.

3. **Token rotation** — Each refresh invalidates the previous refresh token, limiting exposure window.

4. **Tokens not logged** — Token values are never logged (only truncated session IDs).

## For Agent System Prompt

When configuring your agent, you can use a system prompt like:

```
You have access to capital planning tools for analyzing infrastructure assets 
and creating investment plans. Authentication is handled automatically — 
just call the tools directly.

Available tools:
- capital_get_assets: List all assets in a portfolio
- capital_get_asset: Get details for a specific asset  
- capital_analyze_risk: Analyze failure risk for assets
- capital_optimize_investments: Create an optimized investment plan
- capital_session_info: Check your session status (for debugging)

You do not need to handle authentication or tokens — focus on the capital 
planning task.
```

## Why Single ASGI App?

The REST API and MCP server share:
- `SessionManager` — tracks which session is active
- `TokenManager` — handles token refresh with rotation
- `api_client` — makes authenticated requests to services

By running as a single ASGI app:
- No threading or multiprocessing complexity
- Shared state without IPC
- Single port to expose
- Simpler deployment
