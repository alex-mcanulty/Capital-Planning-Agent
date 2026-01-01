# Capital Planning Agentic AI System

A demonstration system for capital planning with OAuth 2.0 authentication, token rotation, and long-running workflow support.

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

Terminal 2 - Services API:
```bash
uv run python -m services.main
```

Terminal 3 - MCP Server:
```bash
uv run python -m mcp_server.main --transport streamable-http --port 8002
```

Terminal 4 - Frontend:
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

### Limited User (Read-only)
- Username: `limited_user`
- Password: `limited_pass`
- Scopes: `assets:read`

## Testing Authorization

The frontend provides buttons to test each API endpoint:

1. **Asset Endpoints** (requires: `assets:read`)
   - GET /assets - List all assets
   - GET /assets/{id} - Get single asset

2. **Risk Analysis** (requires: `risk:analyze`)
   - POST /risk/analyze - Analyze asset risks
   - Takes 5 seconds (exceeds access token lifetime!)

3. **Investment Optimization** (requires: `investments:write`)
   - POST /investments/optimize - Optimize investment plan
   - Takes 8 seconds (exceeds access token lifetime!)

## Testing Token Refresh

The access token lifetime is intentionally set to **10 seconds** to demonstrate token refresh behavior:

1. Login as `admin_user`
2. Wait for the token to expire (watch the countdown)
3. Click "POST /risk/analyze" (takes 5s)
4. Observe automatic token refresh in the activity log
5. Click "POST /investments/optimize" (takes 8s)
6. Observe multiple token refreshes during a single long-running operation

## Testing Authorization Failures

1. Login as `limited_user` (only has `assets:read` scope)
2. Try clicking "POST /risk/analyze"
3. Observe 403 Forbidden error due to missing `risk:analyze` scope

## Architecture

```
┌─────────────┐
│  Frontend   │ (http://localhost:8080)
└──────┬──────┘
       │
       ├──────────────────┬──────────────────┐
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ OIDC Server │    │ Services API│    │  MCP Server │
│   :8000     │    │    :8001    │    │    :8002    │
└─────────────┘    └──────┬──────┘    └──────┬──────┘
                          │                  │
                          └──────────────────┘
                          (MCP calls Services with token management)
```

### OIDC Server (port 8000)
- Issues JWT tokens with RS256 signing
- Access token: 10s lifetime
- Refresh token: 30s lifetime
- Implements token rotation on refresh

### Services API (port 8001)
- Asset Service (GET /assets, GET /assets/{id})
- Risk Service (POST /risk/analyze)
- Investment Service (POST /investments/optimize)
- JWT verification using OIDC server's JWKS
- Scope-based authorization

### MCP Server (port 8002)
- Stateful MCP server with token management
- Transparently refreshes access tokens before API calls
- Scope-based authorization enforcement
- Tools: get_assets, get_asset, analyze_risk, optimize_investments

### Frontend (port 8080)
- Login interface with OAuth 2.0 authorization code flow
- Token display and manual refresh
- API endpoint testing
- Real-time activity logging

## Key Features Demonstrated

1. **JWT Authentication**
   - RS256 signing with public key verification
   - JWKS endpoint for key distribution
   - Token expiry validation

2. **Token Refresh with Rotation**
   - Automatic token refresh before expiry
   - Refresh token rotation (new refresh token on each refresh)
   - Prevents token replay attacks

3. **Long-Running Operations**
   - Operations that exceed access token lifetime
   - Transparent token refresh during execution
   - No interruption to user experience

4. **Scope-Based Authorization**
   - Different users have different permissions
   - API endpoints check required scopes
   - 403 Forbidden when scopes are insufficient

5. **Security Features**
   - Authorization code flow (not implicit)
   - Refresh token rotation
   - Token reuse detection
   - Scope enforcement

## API Endpoints

### OIDC Server (http://localhost:8000)

- `GET /.well-known/openid-configuration` - OIDC discovery
- `GET /authorize` - Authorization endpoint (simplified)
- `POST /token` - Token endpoint (authorization_code, refresh_token grants)
- `GET /userinfo` - User information
- `GET /jwks` - JSON Web Key Set

### Services API (http://localhost:8001)

- `GET /assets` - List assets
- `GET /assets/{id}` - Get asset details
- `POST /risk/analyze` - Analyze asset risks
- `POST /investments/optimize` - Optimize investment plan

## MCP Server Tools

The MCP server exposes the following tools for agent workflows:

### Authentication
- `capital_authenticate` - Establish an authenticated session with tokens

### Capital Planning Tools
- `capital_get_assets` - Fetch all infrastructure assets in a portfolio
- `capital_get_asset` - Fetch detailed information about a specific asset
- `capital_analyze_risk` - Analyze failure risk for specified assets
- `capital_optimize_investments` - Generate optimized investment plan within budget
- `capital_session_info` - Get current session information and token status

All tools automatically handle token refresh when needed, supporting long-running operations.

## Development

### Project Structure

```
capital-planner/
├── oidc_server/         # Mock OIDC provider
│   ├── main.py
│   ├── config.py
│   ├── jwt_utils.py
│   └── models.py
├── services/            # Mock backend services
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── mock_data.py
│   └── models.py
├── mcp_server/          # MCP server with token management
│   ├── main.py
│   ├── token_manager.py
│   ├── api_client.py
│   ├── tools.py
│   ├── models.py
│   └── config.py
└── frontend/            # Web UI
    ├── index.html
    ├── app.js
    └── styles.css
```

### Configuration

Edit token lifetimes in `oidc_server/config.py`:
```python
ACCESS_TOKEN_LIFETIME = 10   # seconds
REFRESH_TOKEN_LIFETIME = 30  # seconds
ROTATE_REFRESH_TOKENS = True
```

Edit operation delays in `services/config.py`:
```python
ENDPOINT_DELAYS = {
    "get_assets": 2,
    "analyze_risk": 5,
    "optimize_investments": 8
}
```

## Next Steps

The MCP server is complete! Next steps:
- LangGraph Agent for agentic orchestration
- Integration with Claude desktop or other MCP clients
- Multi-step workflows with transparent auth handling

See DESIGN.md for the complete architecture plan.
