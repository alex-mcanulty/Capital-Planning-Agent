# Capital Planning Agentic AI System — Design Document

## 1. Overview

### 1.1 Problem Statement

Capital Planners manually review thousands of assets, analyze failure risks, evaluate investment options, and assemble optimized investment plans. We are building an Agentic AI system that automates this workflow, allowing a Planner to issue natural language requests such as:

> "Analyze the top 5 assets at risk of failure and propose an optimized investment plan for next year."

### 1.2 Key Requirements (from Assignment)

| Requirement | Description |
|-------------|-------------|
| Agentic Orchestrator | Accept prompts, decompose into steps, call services, produce structured output |
| Agent + Tool Abstractions | At least one agent with tool wrappers for Asset, Risk, and Investment services |
| Authorization in Code | Agent cannot call tools the user wouldn't have permission to use directly |
| Long-Running Workflow Handling | Handle operations that outlast HTTP requests (hours/days) |
| Security & Safety | Prompt injection prevention, tool constraints, I/O validation, data leak prevention |

### 1.3 Our Approach

Rather than mocking at the tool level, we will build a realistic multi-service architecture:

- **Mock OIDC Server** — Issues and rotates tokens with configurable short lifetimes
- **Mock FastAPI Services** — Asset, Risk, and Investment endpoints with token auth and artificial delays
- **MCP Server** — Stateful server managing token lifecycle and exposing tools to the agent
- **LangGraph Agent** — Orchestrates tool calls to fulfill user requests
- **Frontend** — Simple login UI and chat interface for demonstration

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (Web UI)                             │
│                         Login + Chat Interface                             │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │ 
                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                           LangGraph Agent                                  │
│                   Capital Planning Orchestrator                            │
│            - Accepts user prompt                                           │
│            - Decomposes into steps                                         │
│            - Invokes MCP tools                                             │
│            - Produces structured response                                  │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │ Tool calls
                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                        MCP Server (Stateful)                               │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Token Manager                                 │  │
│  │   - Stores access_token + refresh_token per user session            │  │
│  │   - Checks token expiry before each API call                        │  │
│  │   - Refreshes transparently using refresh token rotation            │  │
│  │   - Stores rotated refresh tokens                                   │  │
│  │   - Surfaces error only if refresh chain breaks                     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                       │
│           ┌────────────────────────┼────────────────────────┐              │
│           ▼                        ▼                        ▼              │
│    ┌─────────────┐          ┌─────────────┐          ┌─────────────┐       │
│    │ Asset Tool  │          │ Risk Tool   │          │ Investment  │       │
│    │             │          │             │          │ Tool        │       │
│    └─────────────┘          └─────────────┘          └─────────────┘       │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     Authorization Enforcer                           │  │
│  │   - Checks user scopes before tool execution                        │  │
│  │   - Rejects unauthorized tool calls                                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │ HTTP + Bearer Token
                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      FastAPI Mock Services                                 │
│                                                                            │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│   │  Asset Service  │  │  Risk Service   │  │ Investment Svc  │            │
│   │                 │  │                 │  │                 │            │
│   │ GET /assets     │  │ POST /risk/     │  │ POST /invest/   │            │
│   │ GET /assets/:id │  │      analyze    │  │      optimize   │            │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                            │
│   - Token validation via OIDC introspection or JWT verification            │
│   - Artificial delays to simulate long-running operations                  │
│   - Scope-based authorization                                              │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │ Token issuance/refresh
                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         Mock OIDC Server                                   │
│                                                                            │
│   Endpoints:                                                               │
│   - GET  /.well-known/openid-configuration                                 │
│   - GET  /authorize                                                        │
│   - POST /token                                                            │
│   - GET  /userinfo                                                         │
│   - GET  /jwks                                                             │
│                                                                            │
│   Users (in-memory):                                                       │
│   - admin_user: full scopes (assets:read, risk:analyze, investments:write) │
│   - limited_user: restricted scopes (assets:read only)                     │
│                                                                            │
│   Configuration:                                                           │
│   - Access token lifetime: 10 seconds                                      │
│   - Refresh token lifetime: 30 seconds                                     │
│   - Refresh token rotation: enabled                                        │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Components

### 3.1 Mock OIDC Server

**Language:** Python  
**Framework:** FastAPI  

#### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/openid-configuration` | GET | Discovery document |
| `/authorize` | GET | Authorization endpoint (simplified for demo) |
| `/token` | POST | Token endpoint (authorization_code + refresh_token grants) |
| `/userinfo` | GET | Returns user claims |
| `/jwks` | GET | JSON Web Key Set for token verification |

#### Users (Hardcoded)

```python
USERS = {
    "admin_user": {
        "password": "admin_pass",
        "sub": "admin_user",
        "scopes": ["assets:read", "risk:analyze", "investments:write"],
        "name": "Admin User",
        "email": "admin@example.com"
    },
    "limited_user": {
        "password": "limited_pass", 
        "sub": "limited_user",
        "scopes": ["assets:read"],
        "name": "Limited User",
        "email": "limited@example.com"
    }
}
```

#### Token Configuration

```python
ACCESS_TOKEN_LIFETIME = 10      # seconds
REFRESH_TOKEN_LIFETIME = 30     # seconds
ROTATE_REFRESH_TOKENS = True    # Issue new refresh token on each refresh
```

#### Refresh Token Rotation Logic

```python
@app.post("/token")
async def token_endpoint(grant_type: str, ...):
    if grant_type == "refresh_token":
        # 1. Validate refresh token
        # 2. Check for reuse (optional: detect token theft)
        # 3. Invalidate old refresh token
        # 4. Issue new access_token + new refresh_token
        # 5. Return both tokens
```

#### TODOs

- [ ] Implement JWT signing with RS256 (generate keypair on startup)
- [ ] Implement `/jwks` endpoint exposing public key
- [ ] Implement `/.well-known/openid-configuration` discovery
- [ ] Implement `/authorize` endpoint (simplified: accept username/password, return code)
- [ ] Implement `/token` endpoint with `authorization_code` grant
- [ ] Implement `/token` endpoint with `refresh_token` grant + rotation
- [ ] Implement `/userinfo` endpoint
- [ ] Track issued refresh tokens in memory (for rotation/revocation)
- [ ] Optional: Implement refresh token reuse detection

---

### 3.2 FastAPI Mock Services

**Language:** Python  
**Framework:** FastAPI  

#### Endpoints

**Asset Service:**
```
GET /assets?portfolioId={id}
    → Returns list of assets in portfolio
    
GET /assets/{assetId}
    → Returns single asset details
```

**Risk Service:**
```
POST /risk/analyze
    Body: { "assetIds": string[], "horizonMonths": number }
    → Returns risk analysis for each asset
```

**Investment Service:**
```
POST /investments/optimize
    Body: {
        "candidates": [
            { "assetId": string, "interventionType": string, "cost": number, "expectedRiskReduction": number }
        ],
        "budget": number,
        "horizonMonths": number
    }
    → Returns optimized investment plan
```

#### Authentication

- All endpoints require `Authorization: Bearer <token>` header
- Token validated via JWT verification using OIDC server's public key
- Scopes extracted from token and checked against endpoint requirements

#### Scope Requirements

| Endpoint | Required Scope |
|----------|----------------|
| `GET /assets*` | `assets:read` |
| `POST /risk/analyze` | `risk:analyze` |
| `POST /investments/optimize` | `investments:write` |

#### Artificial Delays

```python
ENDPOINT_DELAYS = {
    "get_assets": 2,           # seconds
    "get_asset": 1,            # seconds
    "analyze_risk": 5,         # seconds (longer than access token!)
    "optimize_investments": 8  # seconds (longer than access token!)
}
```

#### Mock Data

Generate realistic-looking asset data:

```python
MOCK_ASSETS = [
    {
        "id": "asset-001",
        "name": "Water Main - Section 14A",
        "type": "water_main",
        "installDate": "1987-03-15",
        "location": "District 5",
        "condition": "poor",
        "replacementCost": 450000
    },
    # ... more assets
]
```

#### TODOs

- [ ] Set up FastAPI application with CORS
- [ ] Implement JWT verification dependency (fetch JWKS from OIDC server)
- [ ] Implement scope-checking dependency
- [ ] Implement `GET /assets` endpoint with mock data
- [ ] Implement `GET /assets/{assetId}` endpoint
- [ ] Implement `POST /risk/analyze` endpoint with mock risk calculations
- [ ] Implement `POST /investments/optimize` endpoint with mock optimization
- [ ] Add configurable delays to each endpoint
- [ ] Generate 20-30 realistic mock assets

---

### 3.3 MCP Server

**Language:** Python  
**Framework:** FastMCP or MCP SDK  

#### Tools Exposed

| Tool | Description | Required Scope |
|------|-------------|----------------|
| `get_assets` | Fetch assets for a portfolio | `assets:read` |
| `get_asset` | Fetch single asset details | `assets:read` |
| `analyze_risk` | Analyze risk for given assets | `risk:analyze` |
| `optimize_investments` | Generate optimized investment plan | `investments:write` |

#### Token Manager

The MCP server maintains a stateful Token Manager that:

1. **Stores credentials per user session**
   ```python
   sessions: dict[str, TokenSession] = {}
   
   class TokenSession:
       user_id: str
       access_token: str
       access_token_expires: datetime
       refresh_token: str
       refresh_token_expires: datetime
       scopes: list[str]
   ```

2. **Checks token validity before each API call**
   ```python
   async def ensure_valid_token(self, session_id: str) -> str:
       session = self.sessions[session_id]
       
       if session.access_token_expires > now() + buffer:
           return session.access_token
       
       if session.refresh_token_expires > now():
           await self.refresh_tokens(session_id)
           return session.access_token
       
       raise AuthenticationExpired("Session expired, re-authentication required")
   ```

3. **Refreshes tokens transparently**
   ```python
   async def refresh_tokens(self, session_id: str):
       session = self.sessions[session_id]
       
       response = await http_client.post(
           f"{OIDC_SERVER}/token",
           data={
               "grant_type": "refresh_token",
               "refresh_token": session.refresh_token,
               "client_id": CLIENT_ID
           }
       )
       
       # Store BOTH new tokens (rotation)
       session.access_token = response["access_token"]
       session.refresh_token = response["refresh_token"]  # New!
       session.access_token_expires = now() + timedelta(seconds=response["expires_in"])
       # Refresh token expiry estimated or returned by server
   ```

#### Authorization Enforcer

Before executing any tool:

```python
def check_authorization(session: TokenSession, required_scope: str):
    if required_scope not in session.scopes:
        raise AuthorizationError(
            f"User lacks required scope '{required_scope}' for this operation"
        )
```

This ensures the agent cannot call tools the user wouldn't have access to directly.

#### TODOs

- [ ] Set up MCP server with FastMCP
- [ ] Implement TokenSession dataclass
- [ ] Implement TokenManager with session storage
- [ ] Implement token refresh with rotation support
- [ ] Implement authorization checking per tool
- [ ] Implement `get_assets` tool
- [ ] Implement `get_asset` tool
- [ ] Implement `analyze_risk` tool
- [ ] Implement `optimize_investments` tool
- [ ] Handle and surface authentication/authorization errors gracefully
- [ ] Add logging for token refresh events (for demo visibility)

---

### 3.4 LangGraph Agent

**Language:** Python  
**Framework:** LangGraph  

#### Agent: CapitalPlanningAgent

Responsibilities:
- Accept natural language prompts from users
- Decompose requests into executable steps
- Invoke MCP tools in appropriate sequence
- Handle tool errors gracefully
- Produce structured final response

#### Example Flow

User: "Analyze the top 5 assets at risk of failure and propose an optimized investment plan for next year."

```
1. Call get_assets(portfolioId="default") → list of assets
2. Call analyze_risk(assetIds=[...all asset ids...], horizonMonths=12) → risk scores
3. Sort by risk, take top 5
4. For each high-risk asset, determine intervention options
5. Call optimize_investments(candidates=[...], budget=1000000, horizonMonths=12)
6. Format and return structured response
```

#### Binding MCP Tools

```python
from langchain_mcp import MCPToolkit

toolkit = MCPToolkit(server_url="http://localhost:8002")
tools = toolkit.get_tools()

agent = create_react_agent(
    model=ChatAnthropic(model="claude-sonnet-4-20250514"),
    tools=tools,
    system_prompt=CAPITAL_PLANNING_SYSTEM_PROMPT
)
```

#### System Prompt Considerations

The system prompt should:
- Explain the Capital Planning domain
- Describe available tools and when to use them
- Instruct on handling errors (especially auth errors)
- Define output format expectations

#### TODOs

- [ ] Define agent system prompt
- [ ] Set up MCP tool binding
- [ ] Implement LangGraph agent with tool-calling loop
- [ ] Implement structured output formatting
- [ ] Handle authorization errors gracefully (inform user of permission issues)
- [ ] Handle authentication expiry (inform user session expired)
- [ ] Add conversation memory (optional, for multi-turn interactions)

---

### 3.5 Frontend

**Framework:** Simple HTML/JS or React (minimal)

#### Pages

1. **Login Page**
   - Username/password form
   - Submits to OIDC `/authorize` → `/token` flow
   - Stores tokens and redirects to chat

2. **Chat Interface**
   - Text input for user prompts
   - Display area for agent responses
   - Shows structured investment plans nicely formatted
   - Visual indicator when agent is working

#### Authentication Flow

```
1. User enters credentials
2. Frontend calls /authorize (or simplified direct /token for demo)
3. Receives access_token + refresh_token
4. Sends tokens to MCP server to establish session
5. Subsequent agent calls reference that session
```

#### TODOs

- [ ] Create login page with form
- [ ] Implement OIDC authorization flow
- [ ] Create chat interface
- [ ] Implement session establishment with MCP server
- [ ] Display agent responses with formatting
- [ ] Handle session expiry (redirect to login)
- [ ] Show visual feedback during long operations

---

## 4. Security & Safety Considerations

### 4.1 Prompt Injection Prevention

| Mitigation | Implementation |
|------------|----------------|
| Input sanitization | Validate/sanitize user input before passing to agent |
| Tool output isolation | Don't allow tool outputs to be interpreted as instructions |
| Structured tool interfaces | Tools accept typed parameters, not free-form strings |
| System prompt hardening | Clear separation of instructions vs. user input |

### 4.2 Tool Usage Constraints

| Mitigation | Implementation |
|------------|----------------|
| Scope-based authorization | MCP server checks user scopes before each tool call |
| Rate limiting | Limit tool calls per session (optional) |
| Tool allowlisting | Agent can only access explicitly defined tools |
| Audit logging | Log all tool invocations with user context |

### 4.3 Input/Output Validation

| Mitigation | Implementation |
|------------|----------------|
| Schema validation | Pydantic models for all API request/response bodies |
| Parameter bounds | Validate ranges (e.g., horizonMonths between 1-120) |
| Output sanitization | Ensure tool outputs don't contain executable content |

### 4.4 Sensitive Data Protection

| Mitigation | Implementation |
|------------|----------------|
| Token security | Tokens stored securely, never logged in full |
| Response filtering | Don't expose internal IDs or system details in errors |
| Scope principle | Users only see data their scopes permit |

### 4.5 TODOs

- [ ] Implement input validation on all API endpoints
- [ ] Add audit logging for tool invocations
- [ ] Ensure tokens are not logged (or are redacted)
- [ ] Document prompt injection mitigations in README
- [ ] Document authorization model in README

---

## 5. Long-Running Workflow Handling

### 5.1 The Problem

- Access tokens expire in 10 seconds
- Some operations (risk analysis, optimization) take longer than 10 seconds
- Agent may chain multiple operations, total time exceeding token lifetime
- Traditional auth assumes user is present to re-authenticate

### 5.2 Our Solution: Transparent Token Refresh with Rotation

1. **MCP server manages tokens** — Agent never sees or handles tokens
2. **Pre-call token check** — Before each API call, check if access token is expired/expiring
3. **Automatic refresh** — Use refresh token to obtain new access token
4. **Refresh token rotation** — Each refresh also returns a new refresh token
5. **Sliding window** — As long as agent is active, session continues indefinitely

### 5.3 Edge Cases

| Scenario | Behavior |
|----------|----------|
| Access token expires mid-call | Retry with refreshed token (or rely on pre-check) |
| Refresh token expires (agent idle) | Surface error, user must re-authenticate |
| Refresh token reuse detected | Revoke session, user must re-authenticate |
| Maximum session lifetime exceeded | Policy decision — could enforce if desired |

### 5.4 Demo Scenarios

| Scenario | Configuration | Expected Outcome |
|----------|---------------|------------------|
| Normal operation | 10s access, 30s refresh | Agent completes multi-step task, tokens refresh seamlessly |
| Multiple refreshes | 10s access, 30s refresh, task takes 60s+ | Multiple refresh cycles, all transparent |
| Idle timeout | 10s access, 30s refresh, 45s pause mid-task | Refresh fails, user notified |

---

## 6. File Structure

```
capital-planner/
├── README.md
├── DESIGN.md                    # This document
├── docker-compose.yml           # Optional: orchestrate all services
├── requirements.txt             # Shared Python dependencies
│
├── oidc_server/
│   ├── __init__.py
│   ├── main.py                  # FastAPI OIDC server
│   ├── config.py                # Token lifetimes, users
│   ├── jwt_utils.py             # JWT creation/validation
│   └── models.py                # Pydantic models
│
├── services/
│   ├── __init__.py
│   ├── main.py                  # FastAPI services (Asset, Risk, Investment)
│   ├── config.py                # Delays, mock data config
│   ├── auth.py                  # JWT verification dependency
│   ├── mock_data.py             # Asset/risk/investment mock data
│   └── models.py                # Pydantic models
│
├── mcp_server/
│   ├── __init__.py
│   ├── main.py                  # MCP server entry point
│   ├── token_manager.py         # Token lifecycle management
│   ├── tools.py                 # Tool definitions
│   └── auth.py                  # Authorization enforcement
│
├── agent/
│   ├── __init__.py
│   ├── main.py                  # LangGraph agent
│   ├── prompts.py               # System prompts
│   └── config.py                # Model configuration
│
└── frontend/
    ├── index.html               # Login + chat UI
    ├── app.js                   # Frontend logic
    └── styles.css               # Styling
```

---

## 7. Open Questions & Considerations

### 7.1 For Implementation

1. **MCP session management** — How does the frontend establish a session with the MCP server? Options:
   - Frontend sends tokens to MCP server, receives session ID
   - MCP server handles full OIDC flow itself
   - WebSocket connection maintains session implicitly

2. **Error surfacing** — When auth fails mid-workflow, how much detail does the agent reveal to the user?

3. **Partial completion** — If a multi-step workflow fails partway through, should we return partial results?

### 7.2 For Interview Discussion

1. **Production token storage** — In production, would tokens be encrypted at rest? Use a secure vault?

2. **Horizontal scaling** — If MCP server scales to multiple instances, how is session state shared? Redis? Sticky sessions?

3. **True long-running workflows** — For genuinely multi-day workflows, is token refresh sufficient, or do we need a different model (stored permissions, workflow-specific grants)?

4. **Observability** — How would we monitor token refresh patterns, detect anomalies, alert on auth failures?

5. **Revocation** — If a user's permissions change mid-workflow, how quickly should that take effect?

---

## 8. Implementation Order

Suggested build sequence:

1. **Mock OIDC Server** — Foundation for all auth
2. **FastAPI Services** — Need something for tools to call
3. **MCP Server** — Token management + tools
4. **Agent** — Orchestration logic
5. **Frontend** — Demo interface

Each component can be tested independently before integration.

---

## 9. Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-01-01 | Initial | Created design document |
