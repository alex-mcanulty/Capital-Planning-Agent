# Capital Planning Agent - Development Guide

## Quick Start

```bash
python start_servers.py    # Starts all 5 servers
# Open http://localhost:8080
# Login: admin_user / admin_pass
```

## Project Purpose

Demo of an agentic AI system with:
- Per-user OAuth authentication via MCP server
- Automatic token refresh during long-running operations
- Scope-based authorization (agent inherits user's permissions)

## Architecture

```
Frontend (8080) → OIDC (8000) → tokens
                ↓
         MCP Server (8002) ← Agent (8003)
                ↓
         Services API (8001)
```

The MCP server is a **hybrid REST + MCP** design:
- REST `/sessions/*` endpoints manage user tokens (called by frontend)
- MCP `/mcp` endpoint exposes tools (called by agent)
- Tokens never reach the agent/LLM

## Intentional Design Decisions (Don't "Fix" These)

### 1. Extremely Short Token Lifetimes
```python
# oidc_server/config.py
ACCESS_TOKEN_LIFETIME = 10   # 10 seconds - intentionally short!
REFRESH_TOKEN_LIFETIME = 30  # 30 seconds - intentionally short!
```
**Why:** This forces the token refresh mechanism to activate during normal operations. In production you'd use 15min/1hr, but short lifetimes prove the system works.

### 2. Artificial API Delays
```python
# services/config.py
ENDPOINT_DELAYS = {
    "analyze_risk": 5,         # Exceeds 10s access token!
    "optimize_investments": 8  # Also exceeds access token!
}
```
**Why:** These delays ensure tokens expire mid-request, forcing the heartbeat refresh to kick in. Don't remove these.

### 3. 25-Second Heartbeat
```python
# mcp_server/config.py
TOKEN_REFRESH_HEARTBEAT_SECONDS = 25  # Must be < 30s refresh token lifetime
```
**Why:** Proactively refreshes all sessions before refresh tokens expire. This handles long-running tool calls where the token can't be refreshed mid-request.

### 4. Token Rotation Enabled
```python
# oidc_server/config.py
ROTATE_REFRESH_TOKENS = True
```
**Why:** Each refresh invalidates the old refresh token. This is a security best practice being demonstrated.

### 5. Hardcoded Test Users
```python
# oidc_server/config.py
USERS = {
    "admin_user": {..., "scopes": ["assets:read", "risk:analyze", "investments:write"]},
    "limited_user": {..., "scopes": ["assets:read"]}  # Can only read assets!
}
```
**Why:** Demo purposes. `limited_user` exists specifically to test authorization failures.

## Key Files

| File | Purpose |
|------|---------|
| `mcp_server/token_manager.py` | Stores tokens per-session, handles refresh |
| `mcp_server/api_client.py` | Calls Services API with user's token |
| `mcp_server/main.py` | Hybrid REST + MCP server, heartbeat task |
| `services/auth.py` | JWT validation via OIDC's JWKS |
| `agent/agent_instruction.py` | System prompt for the LangChain agent |
| `frontend/chatbot.js` | Creates MCP session, activates it, sends chat |

