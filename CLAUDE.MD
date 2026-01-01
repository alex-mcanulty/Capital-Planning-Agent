# Capital Planning Agentic AI System

## Project Overview

This is an Agentic AI system for Capital Planners that automates the workflow of reviewing assets, analyzing failure risks, and assembling optimized investment plans through natural language interaction.

**Example user request:**
> "Analyze the top 5 assets at risk of failure and propose an optimized investment plan for next year."

## Architecture Summary

The system consists of 5 main components:

1. **Mock OIDC Server** - Issues and rotates tokens with short lifetimes (10s access, 30s refresh)
2. **FastAPI Mock Services** - Asset, Risk, and Investment APIs with token auth and artificial delays
3. **MCP Server** - Stateful server managing token lifecycle and exposing tools to the agent
4. **LangGraph Agent** - Orchestrates tool calls to fulfill user requests
5. **Frontend** - Login UI and chat interface

## Key Features

- **Agentic Orchestration** - Natural language prompts decomposed into multi-step workflows
- **Authorization in Code** - Agent cannot call tools the user lacks permission for
- **Long-Running Workflow Handling** - Transparent token refresh handles operations exceeding HTTP request lifetimes
- **Security & Safety** - Prompt injection prevention, scope-based authorization, I/O validation

## Project Structure

```
capital-planner/
├── DESIGN.md                    # Detailed design document
├── CLAUDE.MD                    # This file
├── docker-compose.yml           # Service orchestration
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
│   ├── mock_data.py             # Mock asset data
│   └── models.py                # Pydantic models
│
├── mcp_server/                  # MCP server with token management
│   ├── main.py                  # MCP server entry point
│   ├── token_manager.py         # Token lifecycle management
│   ├── tools.py                 # Tool definitions
│   └── auth.py                  # Authorization enforcement
│
├── agent/                       # LangGraph agent
│   ├── main.py                  # Agent orchestrator
│   ├── prompts.py               # System prompts
│   └── config.py                # Model configuration
│
└── frontend/                    # Web UI
    ├── index.html               # Login + chat interface
    ├── app.js                   # Frontend logic
    └── styles.css               # Styling
```

## Current Status

**Not started** - See DESIGN.md for detailed implementation checklist.

## Implementation Order

1. Mock OIDC Server - Foundation for all authentication
2. FastAPI Services - Backend APIs for tools to call
3. MCP Server - Token management + tool wrappers
4. LangGraph Agent - Orchestration logic
5. Frontend - Demo interface

## Authentication Flow

1. User logs in with username/password
2. OIDC server issues access token (10s lifetime) + refresh token (30s lifetime)
3. Frontend establishes session with MCP server
4. Agent invokes tools via MCP server
5. MCP server transparently refreshes tokens as needed
6. Refresh token rotation ensures sliding window for long workflows

## Test Users

```
admin_user / admin_pass
  - Scopes: assets:read, risk:analyze, investments:write
  - Can use all tools

limited_user / limited_pass
  - Scopes: assets:read only
  - Cannot analyze risk or optimize investments
```

## Available Tools (via MCP)

| Tool | Description | Required Scope |
|------|-------------|----------------|
| `get_assets` | Fetch assets for a portfolio | `assets:read` |
| `get_asset` | Fetch single asset details | `assets:read` |
| `analyze_risk` | Analyze risk for given assets | `risk:analyze` |
| `optimize_investments` | Generate optimized investment plan | `investments:write` |

## API Endpoints

### OIDC Server (port 8000)
- `GET /.well-known/openid-configuration` - Discovery
- `GET /authorize` - Authorization endpoint
- `POST /token` - Token issuance and refresh
- `GET /userinfo` - User claims
- `GET /jwks` - Public keys for verification

### Asset Service (port 8001)
- `GET /assets?portfolioId={id}` - List assets
- `GET /assets/{assetId}` - Get asset details

### Risk Service (port 8001)
- `POST /risk/analyze` - Analyze asset failure risks

### Investment Service (port 8001)
- `POST /investments/optimize` - Generate optimized investment plan

## Security Considerations

### Prompt Injection Prevention
- Input sanitization before passing to agent
- Tool outputs isolated from instruction flow
- Structured tool interfaces (typed parameters)
- System prompt hardening

### Authorization
- Scope-based authorization checked by MCP server before each tool call
- Agent cannot bypass user permissions
- Audit logging for all tool invocations

### Token Security
- Tokens never logged in full
- Secure token storage in MCP server
- Refresh token rotation prevents replay attacks
- Token reuse detection (optional)

### Input/Output Validation
- Pydantic schema validation on all APIs
- Parameter bounds checking
- Output sanitization

## Long-Running Workflow Strategy

**Problem:** Operations take longer than access token lifetime (10s)

**Solution:** MCP server's Token Manager
1. Stores access_token + refresh_token per session
2. Checks token expiry before each API call
3. Automatically refreshes using refresh token
4. Stores rotated refresh tokens
5. Only surfaces error if refresh chain breaks

This enables multi-step workflows lasting hours/days without user re-authentication.

## Development Notes

### Running the System
```bash
# Start OIDC server
cd oidc_server && python main.py

# Start backend services
cd services && python main.py

# Start MCP server
cd mcp_server && python main.py

# Start agent
cd agent && python main.py

# Serve frontend
cd frontend && python -m http.server 8080
```

### Testing Token Refresh
Configure artificial delays in services/config.py to exceed token lifetime:
- Risk analysis: 5s (triggers at least one refresh)
- Investment optimization: 8s (triggers multiple refreshes)

### Debugging
- Check MCP server logs for token refresh events
- Check service logs for authorization failures
- Check OIDC server logs for token issuance/rotation

## Key Design Decisions

1. **Why MCP for tools?** - MCP servers are stateful, perfect for managing token lifecycle
2. **Why mock OIDC?** - Demonstrates realistic OAuth 2.0 flow with token rotation
3. **Why short token lifetimes?** - Forces demonstration of long-running workflow handling
4. **Why LangGraph?** - Best for complex multi-step agentic workflows

## Future Considerations

- Production token storage (encryption at rest, vault)
- Horizontal scaling (shared session state via Redis)
- Multi-day workflows (workflow-specific grants vs. token refresh)
- Observability (monitoring refresh patterns, auth failure alerts)
- Real-time permission revocation during workflows

## References

- See DESIGN.md for complete technical specification
- See interview assignment document for original requirements
