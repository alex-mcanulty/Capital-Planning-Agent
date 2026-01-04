# Capital Planning Agentic AI System

A production-ready demonstration of an autonomous AI agent for capital planning workflows, featuring OAuth 2.0 authentication, automatic token refresh, and a novel stateful MCP server architecture designed for long-running autonomous operations.

## Project Overview

This system demonstrates how to build an agentic AI application that:
- Autonomously orchestrates multi-step capital planning workflows through natural language interaction
- Handles authentication with intentionally short-lived tokens from a local OIDC auth server 
- Simulates access token *and* refresh token expiration mid-workflow
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

## Authentication Flow

Authentication is handled **per-user** with isolated sessions. The MCP server acts as a token proxy - it never has its own service credentials, but manages each user's tokens independently.

### Step-by-Step Flow

```
1. LOGIN
   Browser → OIDC Server (8000)
   └── POST /authorize + POST /token
   └── Returns: access_token, refresh_token, user_id, scopes

2. CHAT REQUEST (includes tokens)
   Browser → Agent Service (8003)
   └── POST /chat { message, access_token, refresh_token, scopes, user_id, history }

3. SESSION CREATION (per agent invocation)
   Agent → MCP Server (8002)
   └── POST /sessions { access_token, refresh_token, user_id, scopes }
   └── Returns: session_id

4. TOOL EXECUTION
   Agent → MCP Server (8002)
   └── MCP tool call with X-Session-ID header
   └── MCP Server looks up session by header
   └── TokenManager retrieves user's access_token

5. API CALL
   MCP Server → Services API (8001)
   └── GET /assets with Authorization: Bearer {user's access_token}
   └── Services validates JWT via OIDC's JWKS endpoint
   └── Returns data (if user has required scopes)

6. SESSION CLEANUP
   Agent → MCP Server (8002)
   └── DELETE /sessions/{session_id} (when agent completes)
```

### Key Security Properties

| Property | Implementation |
|----------|---------------|
| **Per-User Isolation** | Each user gets their own `session_id` with isolated tokens |
| **Token Storage** | Tokens stored in MCP server's `TokenManager`, never in agent/LLM context |
| **Token Validation** | Services API validates JWTs using OIDC's public key (RS256 + JWKS) |
| **Scope Enforcement** | Two-level: MCP checks scopes before API call, Services validates JWT claims |
| **Token Refresh** | Automatic via 8-second heartbeat (sole refresh mechanism) |

### Token Lifecycle

- **Access Token**: 10 seconds (intentionally short to demonstrate refresh)
- **Refresh Token**: 30 seconds (with rotation - each refresh gets new refresh token)
- **Heartbeat**: Every 8 seconds, proactively refreshes all active sessions
- **Session Scope**: Sessions are created per agent invocation and deleted when complete

This design ensures tokens stay fresh even during long-running operations (e.g., 8-second optimization calls).

## Architecture: Stateful MCP Server

This project implements a **hybrid MCP server architecture** that solves a critical challenge: how to manage OAuth token lifecycle for long-running autonomous agent workflows.

### The Problem

Standard MCP servers are stateless - they receive a request, process it, and return a response. But autonomous agents often:
- Execute workflows lasting minutes, hours, or days
- Make multiple tool calls in sequence
- Need to handle tokens that expire mid-workflow 

### My Solution: Hybrid MCP + REST Architecture

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
│  │  GET  /sessions/{id}      - Get session info                    │ │
│  │  DELETE /sessions/{id}    - Delete session                      │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    MCP Endpoint (Tool Access)                   │ │
│  │  /mcp/streamable          - Streamable HTTP MCP transport       │ │
│  │  Tools: capital_get_assets, capital_analyze_risk, etc.          │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    Stateful Token Manager                       │ │
│  │  - Stores access + refresh tokens per session                   │ │
│  │  - Global heartbeat: refreshes ALL sessions every 8s            │ │
│  │  - Heartbeat is sole refresh mechanism (no on-demand refresh)   │ │
│  │  - Handles token rotation                                       │ │
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

### Why Hybrid REST + MCP?

**Problem:** MCP tools receive parameters from the LLM, which would expose tokens in conversation logs.

**Solution:**
- **REST API** (`/sessions/*`) for session management - tokens never touch the agent
- **MCP Endpoint** (`/mcp/streamable`) for tool access - uses active session transparently
- Frontend creates session with tokens, then agent uses tools without seeing credentials

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
- Uses LangChain's create_agent (creates a Langgraph ReAct agent) for planning and orchestration
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

### Basic Workflow

1. Login as `admin_user`
2. In chat, type: "Analyze the top 5 assets at risk of failure and propose an optimized investment plan with a budget of $2 million."
3. Observe agent fetch assets, analyze risk, and generate an investment plan
4. Watch MCP server logs for token refresh events during long operations

### Authorization Testing

1. Login as `limited_user`
2. Try: "Analyze the top 5 assets at risk"
3. Observe authorization error:
   ```
   Authorization Error: Access denied: User lacks required scope(s): ['risk:analyze']
   ```

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
│   ├── README.md                # OIDC server documentation & Okta comparison
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
TOKEN_REFRESH_HEARTBEAT_SECONDS = 8  # Must be < ACCESS_TOKEN_LIFETIME (10s)
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

- **Autonomous Agent Workflows**: Natural language task decomposition, multi-step planning, strategic decision-making
- **Hybrid MCP Architecture**: REST for session management, MCP for tools, tokens never exposed to agent
- **Per-User Authentication**: Isolated sessions with automatic token refresh via background heartbeat
- **Two-Level Authorization**: Scope enforcement at both MCP and Services API levels
- **No Hallucination Design**: Agent selects from backend-provided intervention options, never estimates
- **Production-Ready Patterns**: OAuth 2.0, refresh token rotation, RS256 JWTs, JWKS key distribution

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
- `GET /sessions/{id}` - Get session information
- `DELETE /sessions/{id}` - Delete session

### MCP Server Tools (http://localhost:8002/mcp/streamable)

Accessed via MCP protocol:
- `capital_get_assets` - Fetch all infrastructure assets
- `capital_get_asset` - Fetch single asset details
- `capital_analyze_risk` - Analyze risk + get intervention recommendations
- `capital_optimize_investments` - Generate optimized investment plan
- `capital_session_info` - Get session and token status

### Agent Service (http://localhost:8003)

- `GET /health` - Health check
- `POST /chat/stream` - Chat with agent (returns SSE stream)
- `POST /chat` - Chat with agent (non-streaming, for testing)
