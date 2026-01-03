# Capital Planning Agentic AI System

A production-ready demonstration of an autonomous AI agent for capital planning workflows, featuring OAuth 2.0 authentication, automatic token refresh, and a novel stateful MCP server architecture designed for long-running autonomous operations.

## Project Overview

This system demonstrates how to build an agentic AI application that:
- Autonomously orchestrates multi-step capital planning workflows through natural language interaction
- Handles authentication with intentionally short-lived tokens from a local OIDC auth server (simulating token expiration in production)
- Manages token lifecycle transparently during operations that exceed token lifetimes
- Enforces scope-based authorization at the tool level (agents have the same access as the user who launches them)
- Provides complete intervention recommendations to prevent hallucination

**Example workflow:**
> "Analyze the top 5 assets at risk of failure and propose an optimized investment plan for next year."

The agent autonomously:
1. Retrieves asset portfolio data
2. Analyzes risk for all assets
3. Identifies top 5 at-risk assets
4. Reviews intervention recommendations (repair, replace, rehabilitate, etc.)
5. Selects optimal interventions based on budget and strategy
6. Generates an optimized investment plan

All while managing token refresh transparently across multiple long-running API calls.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start All Servers

**Option A: Automated (Windows)**
```bash
python start_servers.py
```

**Option B: Manual (separate terminals)**

Terminal 1 - OIDC Server:
```bash
uv run python -m oidc_server.main
```

Terminal 2 - Mock Services API:
```bash
uv run python -m services.main
```

Terminal 3 - MCP Server:
```bash
uv run python -m mcp_server.main
```

Terminal 4 - Agent Service:
```bash
uv run python -m agent.main
```

Terminal 5 - Frontend:
```bash
cd frontend
uv run python -m http.server 8080
```

### 3. Open the Frontend

Navigate to: http://localhost:8080

## Test Users

### Admin User (Full Access)
- Username: `admin_user`
- Password: `admin_pass`
- Scopes: `assets:read`, `risk:analyze`, `investments:write`
- Can use all tools and complete full workflows

### Limited User (Read-only)
- Username: `limited_user`
- Password: `limited_pass`
- Scopes: `assets:read`
- Can only view assets, cannot analyze risk or optimize investments

## Novel Architecture: Stateful MCP Server with REST API

This project implements a **hybrid MCP server architecture** that solves a critical challenge: how to manage OAuth token lifecycle for long-running autonomous agent workflows.

### The Problem

Standard MCP servers are stateless - they receive a request, process it, and return a response. But autonomous agents often:
- Execute workflows lasting minutes, hours, or days
- Make multiple tool calls in sequence
- Need to handle tokens that expire mid-workflow 

### Our Solution: Hybrid MCP + REST Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                           Frontend (Port 8080)                         │
│  ┌────────────────┐                             ┌──────────────────┐   │
│  │  Login UI      │                             │  Chat Interface  │   │
│  │  (OAuth Flow)  │                             │  (Agent Comms)   │   │
│  └────────┬───────┘                             └────────┬─────────┘   │
└───────────┼──────────────────────────────────────────────┼─────────────┘
            │                                              │
            │ 1. Authenticate                              │ 4. Chat
            │    (OIDC tokens)                             │    (natural language)
            ▼                                              ▼
┌──────────────────────────────────┐           ┌─────────────────────┐
│   OIDC Server (Port 8000)        │           │  Agent (Port 8003)  │
│  ┌────────────────────────────┐  │           │  ┌───────────────┐  │
│  │ OAuth 2.0 Token Endpoint   │  │           │  │  LangChain    │  │
│  │ - Access: 10s lifetime     │  │           │  │  Agent        │  │
│  │ - Refresh: 30s lifetime    │  │           │  │  Orchestrator │  │
│  │ - Token Rotation           │  │           │  └───────┬───────┘  │
│  └────────────────────────────┘  │           │          │          │
└──────────────────────────────────┘           └──────────┼──────────┘
            │                                             │
            │ 2. Session Creation                         │ 5. Tool Calls
            │    POST /sessions                           │    via MCP
            │    (REST endpoint)                          │
            ▼                                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│              MCP Server (Port 8002) - HYBRID ARCHITECTURE            │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    REST API (Session Management)                │ │
│  │  POST /sessions           - Create authenticated session        │ │
│  │  POST /sessions/{id}/activate - Set active session              │ │
│  │  GET  /sessions/{id}      - Get session info                    │ │
│  │  DELETE /sessions/{id}    - Logout                              │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    MCP Endpoint (Tool Access)                   │ │
│  │  /mcp/streamable          - Streamable HTTP MCP transport       │ │
│  │  Tools: capital_get_assets, capital_analyze_risk, etc.          │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    Stateful Token Manager                       │ │
│  │  - Stores access + refresh tokens per session                   │ │
│  │  - Checks token expiry before EVERY API call                    │ │
│  │  - Automatically refreshes using refresh token                  │ │
│  │  - Handles token rotation                                       │ │
│  │  - Global heartbeat: refreshes ALL sessions every 25s           │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    API Client (Backend Calls)                   │ │
│  │  - Calls Mock Services with token from TokenManager             │ │
│  │  - Enforces scope-based authorization                           │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ 3. API Calls with
                                 │    Token Management
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│               Mock Services API (Port 8001)                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  GET  /assets              - List assets                       │  │
│  │  GET  /assets/{id}         - Get asset details                 │  │
│  │  POST /risk/analyze        - Analyze risk (5s delay)           │  │
│  │                              Returns risk + interventions      │  │
│  │  POST /investments/optimize - Optimize plan (8s delay)         │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  - JWT verification via JWKS                                         │
│  - Scope-based authorization                                         │
│  - Artificial delays to exceed token lifetimes                       │
│  - Returns intervention recommendations with costs & risk reductions │
└──────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

#### 1. Hybrid REST + MCP Design

**Why not use MCP protocol for authentication?**
- MCP tools receive all parameters from the LLM, exposing tokens in conversation logs
- Token refresh requires securely stored refresh tokens that shouldn't be in tool parameters

**Solution:**
- **REST API** (`/sessions/*`) for session management - tokens never touch the agent
- **MCP Endpoint** (`/mcp/streamable`) for tool access - uses active session transparently
- Frontend creates session with tokens, then agent uses tools without seeing credentials

#### 2. Stateful Token Management

**Challenge:** Operations take longer than access token lifetime (10s)

**Solution: TokenManager class**
```python
# Before EVERY API call:
1. Check if access token is still valid (with 2s buffer)
2. If expired/expiring, use refresh token to get new access token
3. Store new access token AND new refresh token (rotation)
4. Make API call with fresh token
```

This enables workflows lasting hours without user re-authentication.

#### 3. Global Token Refresh Heartbeat

**Challenge:** A single tool call may take longer than the refresh token lifetime (30s)

For example:
- Tool call starts at t=0
- Access token refreshed at t=8 (expires at t=10)
- Tool still running at t=38 (refresh token expired at t=30)
- Cannot refresh anymore - workflow fails

**Solution: Background Heartbeat Task**
```python
# Independently of tool calls:
Every 25 seconds:
  For each active session:
    If access token is expiring soon:
      Refresh it proactively
      Get new refresh token (with fresh 30s lifetime)
```

Tokens stay fresh regardless of individual operation duration.

Configuration: `TOKEN_REFRESH_HEARTBEAT_SECONDS = 25` (in `mcp_server/config.py`)

#### 4. Intentionally Short Token Lifetimes

**Why such short tokens?**
- Access token: 10 seconds
- Refresh token: 30 seconds

This simulates production constraints where tokens expire quickly for security. It forces the system to demonstrate robust token lifecycle management.

In production, you might have:
- Access token: 15 minutes
- Refresh token: 1 hour
- Same heartbeat pattern keeps them fresh indefinitely

## Mock Services & Data Design

### Philosophy: No Hallucination

The agent must **never** invent or estimate:
- Intervention costs
- Expected risk reductions
- Available intervention types

### Risk Analysis Returns Complete Intervention Recommendations

When the agent calls `capital_analyze_risk`, it receives:

```json
{
  "asset_id": "asset-001",
  "risk_score": 7.8,
  "probability_of_failure": 0.65,
  "recommended_interventions": [
    {
      "intervention_type": "replace",
      "description": "Complete replacement of Water Main - Section 1",
      "estimated_cost": 450000.00,
      "expected_risk_reduction": 0.9500
    },
    {
      "intervention_type": "rehabilitate",
      "description": "Major rehabilitation and system upgrade",
      "estimated_cost": 280000.00,
      "expected_risk_reduction": 0.8000
    },
    {
      "intervention_type": "repair",
      "description": "Targeted repairs to critical components",
      "estimated_cost": 135000.00,
      "expected_risk_reduction": 0.6500
    }
  ]
}
```

The agent then:
1. Reviews the 2-5 intervention options per asset
2. Selects interventions based on strategy (max risk reduction, cost-effectiveness, balanced)
3. Passes exact values to `capital_optimize_investments`

**No estimation, no hallucination - just intelligent selection from provided options.**

### Mock Data Generation

**30 realistic assets** with:
- Different types (water mains, pump stations, treatment plants, valves, sewer lines)
- Ages ranging from 10 to 50 years
- Conditions correlated with age (newer = excellent/good, older = poor/critical)
- Replacement costs based on asset type
- Expected life spans

**Risk calculation** considers:
- Asset condition (critical = 90% base failure rate, excellent = 5%)
- Age vs. expected life (assets past expected life have accelerated risk)
- Time horizon (longer planning period = higher cumulative risk)

**Intervention options** tailored by condition:
- Critical assets: replace, repair, monitoring
- Poor assets: replace, rehabilitate, repair, monitoring
- Fair assets: replace, rehabilitate, repair, preventive_maintenance, monitoring
- Good assets: repair, preventive_maintenance, monitoring
- Excellent assets: preventive_maintenance

Costs calculated as percentages of replacement cost with realistic variation.

### Artificial Delays

Operations intentionally exceed token lifetimes:
- `get_assets`: 2 seconds
- `analyze_risk`: **5 seconds** (requires 1 token refresh)
- `optimize_investments`: **8 seconds** (may require multiple refreshes)

This demonstrates the token management system under realistic load.

## Agent Architecture

### LangChain Agent with MCP Tools

Located in `agent/`:
- Uses LangChain's create_agent (creates a Langgraph agent) for agentic orchestration
- Connects to MCP server via HTTP transport
- System prompt guides tool selection and workflow planning
- Streams responses to frontend in real-time via SSE

### Key Agent Capabilities

1. **Multi-step reasoning**: Plans workflow before executing
2. **Strategic selection**: Chooses interventions based on user priorities
3. **Budget awareness**: Respects budget constraints when selecting interventions
4. **Transparent operation**: Explains reasoning and selections to user

### Agent Instructions

The agent is instructed to:
- Extract intervention recommendations from risk analysis results
- Use exact costs and risk reduction values (never estimate)
- Select interventions based on strategy (max risk reduction, cost-effectiveness, balanced)
- Build investment candidates from provided recommendations
- Explain selection rationale

See `agent/agent_instruction.py` for complete system prompt.

## Testing the System

### 1. Basic Workflow

1. Login as `admin_user`
2. In chat, type: "Analyze the top 5 assets at risk of failure and propose an optimized investment plan with a budget of $2 million."
3. Observe agent:
   - Fetch assets
   - Analyze risk
   - Review intervention recommendations
   - Select optimal interventions
   - Generate investment plan
4. Watch MCP server logs for token refresh events

### 2. Token Refresh Under Load

Monitor logs during the workflow:

**MCP Server logs:**
```
[Heartbeat] Token refresh heartbeat started (interval: 25s)
[Heartbeat] Refresh cycle complete: total=1, refreshed=1, skipped=0, failed=0
[TokenManager] Tokens refreshed for session abc123... (refresh #1)
[TokenManager] Tokens refreshed for session abc123... (refresh #2)
```

**Services logs:**
```
[Services] POST /risk/analyze - User: admin_user
[Services] Simulating analysis delay of 5s...
[Services] Risk analysis complete: risk-analysis-xyz
```

### 3. Authorization Testing

1. Login as `limited_user`
2. Try: "Analyze the top 5 assets at risk"
3. Observe authorization error:
   ```
   Authorization Error: Access denied: User lacks required scope(s): ['risk:analyze']
   ```

### 4. Long-Running Operations

The system handles operations longer than both token lifetimes:
- Access token: 10s
- Refresh token: 30s
- Risk analysis (5s) + Optimization (8s) = 13s total
- Heartbeat refreshes tokens every 25s
- Workflow completes successfully

## Project Structure

```
capital-planner/
├── README.md                    # This file
├── DESIGN.md                    # Detailed design document
├── CLAUDE.md                    # Project overview for Claude
├── requirements.txt             # Python dependencies
├── start_servers.py             # Automated server startup
│
├── oidc_server/                 # Mock OIDC provider
│   ├── main.py                  # FastAPI OIDC server
│   ├── config.py                # Token lifetimes, users
│   ├── jwt_utils.py             # JWT creation/validation
│   └── models.py                # Pydantic models
│
├── services/                    # Mock backend services
│   ├── main.py                  # Asset, Risk, Investment APIs
│   ├── config.py                # Delays, mock data config
│   ├── auth.py                  # JWT verification
│   ├── mock_data.py             # Mock asset data + interventions
│   └── models.py                # Pydantic models
│
├── mcp_server/                  # Stateful MCP server
│   ├── main.py                  # Hybrid REST + MCP server
│   ├── token_manager.py         # Token lifecycle + heartbeat
│   ├── api_client.py            # Calls to services
│   ├── tools.py                 # MCP tool implementations
│   ├── models.py                # Pydantic models
│   └── config.py                # Server configuration
│
├── agent/                       # LangChain agent
│   ├── main.py                  # Agent service with SSE
│   ├── agent_instruction.py     # System prompt
│   └── config.py                # Model configuration
│
└── frontend/                    # Web UI
    ├── index.html               # Login + chat interface
    ├── app.js                   # Authentication logic
    ├── chatbot.js               # Chat interface
    └── styles.css               # Styling
```

## Configuration

### Token Lifetimes (`oidc_server/config.py`)

```python
ACCESS_TOKEN_LIFETIME = 10   # seconds (intentionally short)
REFRESH_TOKEN_LIFETIME = 30  # seconds (intentionally short)
ROTATE_REFRESH_TOKENS = True # Enable token rotation
```

### Heartbeat Interval (`mcp_server/config.py`)

```python
TOKEN_REFRESH_HEARTBEAT_SECONDS = 25  # Must be < REFRESH_TOKEN_LIFETIME
```

### Operation Delays (`services/config.py`)

```python
ENDPOINT_DELAYS = {
    "get_assets": 2,           # Fast operation
    "get_asset": 1,            # Fast operation
    "analyze_risk": 5,         # Exceeds access token lifetime
    "optimize_investments": 8  # Exceeds access token lifetime
}
```

## Key Features Demonstrated

### 1. Autonomous Agent Workflows
- Natural language task decomposition
- Multi-step planning and execution
- Strategic decision-making with provided data

### 2. Stateful MCP Server
- Session management via REST API
- Tool access via MCP protocol
- Transparent token lifecycle management

### 3. Token Refresh Strategies
- Per-request refresh: Check before each API call
- Global heartbeat: Proactive refresh for all sessions
- Handles operations longer than both token lifetimes

### 4. Authorization in Code
- Scope enforcement at tool level
- Agent cannot bypass user permissions
- Clear error messages for missing scopes

### 5. No Hallucination Design
- Complete intervention recommendations from backend
- Agent selects and reasons from among provided options
- No estimation or invention of costs/risk reductions

### 6. Long-Running Workflow Support
- Operations exceeding HTTP request lifetimes
- Multi-step workflows spanning minutes
- Transparent to both user and agent

### 7. Production-Ready Patterns
- OAuth 2.0 authorization code flow
- Refresh token rotation
- JWT with RS256 signing
- JWKS for key distribution
- Scope-based authorization

## API Endpoints

### OIDC Server (http://localhost:8000)

- `GET /.well-known/openid-configuration` - OIDC discovery
- `GET /authorize` - Authorization endpoint
- `POST /token` - Token endpoint (authorization_code, refresh_token grants)
- `GET /userinfo` - User information
- `GET /jwks` - JSON Web Key Set

### Mock Services API (http://localhost:8001)

- `GET /health` - Health check
- `GET /assets?portfolioId={id}` - List assets (requires: `assets:read`)
- `GET /assets/{id}` - Get asset details (requires: `assets:read`)
- `POST /risk/analyze` - Analyze risks + get intervention recommendations (requires: `risk:analyze`)
- `POST /investments/optimize` - Optimize investment plan (requires: `investments:write`)

### MCP Server REST API (http://localhost:8002)

- `GET /health` - Health check
- `POST /sessions` - Create authenticated session
- `POST /sessions/{id}/activate` - Set active session for MCP tools
- `GET /sessions/{id}` - Get session information
- `DELETE /sessions/{id}` - Delete session (logout)
- `GET /sessions/active/info` - Get active session info

### MCP Server Tools (http://localhost:8002/mcp/streamable)

Accessed via MCP protocol:
- `capital_get_assets` - Fetch all infrastructure assets
- `capital_get_asset` - Fetch single asset details
- `capital_analyze_risk` - Analyze risk + get intervention recommendations
- `capital_optimize_investments` - Generate optimized investment plan
- `capital_session_info` - Get session and token status

### Agent Service (http://localhost:8003)

- `POST /chat` - Chat with agent (returns SSE stream)
- `POST /session` - Create MCP session with tokens

## What's Next?

This system is **complete and production-ready** as a demonstration of:
- Agentic AI workflows with real authorization
- Stateful MCP server architecture
- Long-running autonomous operations
- Token lifecycle management

**Potential extensions:**
- Multi-user support with session isolation
- Persistent workflow state across sessions
- Real-time collaboration features
- Integration with actual asset management systems
- Advanced optimization algorithms
- Multi-day workflow support with workflow-specific grants

## License

This is a demonstration project. See LICENSE for details.
