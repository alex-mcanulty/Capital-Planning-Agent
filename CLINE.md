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
- REST `/sessions/*` endpoints manage user tokens (called by agent, not frontend)
- MCP `/mcp` endpoint exposes tools (called by agent)
- Tokens are passed from frontend → agent → MCP server (agent doesn't inspect them)

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

### 3. 8-Second Heartbeat (Sole Refresh Mechanism)
```python
# mcp_server/config.py
TOKEN_REFRESH_HEARTBEAT_SECONDS = 8  # Must be < 10s access token lifetime
```
**Why:** The heartbeat is the ONLY place tokens are refreshed. This eliminates race conditions from concurrent refresh attempts. The 8s interval ensures access tokens (10s lifetime) are always refreshed with ~2s buffer. No on-demand refresh exists - if a token expires, it means the heartbeat isn't running fast enough.

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
| `agent/main.py` | Creates/deletes MCP sessions per invocation |
| `agent/agent_instruction.py` | System prompt for the LangChain agent |
| `frontend/chatbot.js` | Passes OIDC tokens with each chat request |

## Session Flow (Agent-Scoped Sessions)

```
1. Frontend: User logs in via OIDC → gets access_token + refresh_token
2. Frontend: POST /chat/stream to Agent with { message, tokens, scopes, user_id, history }
3. Agent: POST /sessions to MCP server → creates session, gets session_id
4. Agent: Creates MCP client with X-Session-ID header set to session_id
5. Agent: Invokes LangGraph agent, which calls MCP tools
6. MCP Server: Tools read X-Session-ID header → look up session → use that user's tokens
7. MCP Server: Makes authenticated API calls to Services
8. Agent: DELETE /sessions/{session_id} when agent completes (success or error)
9. Agent: Returns streaming response to frontend
```

**Key point:** MCP sessions are scoped to agent invocations, not browser sessions.
Each chat request creates a new session, uses it for the duration of the agent run,
then deletes it. This eliminates stale session issues and simplifies the design.
Multiple concurrent requests (even from different browser tabs) each get their own session.
