# Setup and Testing Guide

## Installation

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

## Running the System

### Option 1: Start All Servers (Recommended for Windows)

```bash
python start_servers.py
```

This will open 3 separate console windows for each service.

### Option 2: Manual Start (3 separate terminals)

**Terminal 1 - OIDC Server:**
```bash
python -m oidc_server.main
```

**Terminal 2 - Services API:**
```bash
python -m services.main
```

**Terminal 3 - Frontend:**
```bash
cd frontend
python -m http.server 8080
```

## Testing Steps

### 1. Open the Frontend
Navigate to: **http://localhost:8080**

### 2. Login as Admin User
- Username: `admin_user`
- Password: `admin_pass`
- This user has all scopes: `assets:read`, `risk:analyze`, `investments:write`

### 3. Test Basic Asset Endpoints
Click these buttons:
- ✅ **GET /assets** - Should succeed (requires: assets:read)
- ✅ **GET /assets/asset-001** - Should succeed (requires: assets:read)

### 4. Test Long-Running Operations (Token Refresh Demo)

**Important:** Watch the "Access Token Expires" countdown. It starts at 10 seconds.

Click:
- ✅ **POST /risk/analyze** - Takes 5 seconds
  - Watch the Activity Log - you'll see token refresh happening!
  - Even though the operation takes 5s and token lifetime is 10s, the frontend checks expiry before the call

- ✅ **POST /investments/optimize** - Takes 8 seconds
  - Watch multiple token refreshes in the Activity Log
  - The refresh token also rotates (you get a new one each time)

### 5. Test Authorization Failures

Logout and login as:
- Username: `limited_user`
- Password: `limited_pass`
- This user only has: `assets:read`

Now try:
- ✅ **GET /assets** - Should succeed
- ❌ **POST /risk/analyze** - Should fail with 403 Forbidden
- ❌ **POST /investments/optimize** - Should fail with 403 Forbidden

Watch the Activity Log for the authorization error messages.

### 6. Test Manual Token Refresh

While logged in as admin_user:
1. Wait for the token to get close to expiry (< 5 seconds remaining)
2. Click the **"Manual Refresh Token"** button
3. Watch the countdown reset to 10 seconds
4. Check the Activity Log - you'll see the refresh token was rotated

## What to Observe

### In the Frontend UI:
1. **Token Information section** - Shows token expiry countdown
2. **Activity Log** - Shows all API calls and token refreshes
3. **Response section** - Shows full JSON responses

### In the OIDC Server Console:
```
[OIDC] Issued tokens for user: admin_user
[OIDC] Rotated refresh token for user: admin_user
```

### In the Services Console:
```
[Services] GET /assets - User: admin_user
[Services] Returning 30 assets
[Services] POST /risk/analyze - User: admin_user
[Services] Simulating analysis delay of 5s...
[Services] Risk analysis complete
```

## Key Behaviors to Test

### ✅ Token Refresh Works Transparently
- Operations longer than token lifetime complete successfully
- No user intervention needed
- Automatic refresh before token expires

### ✅ Token Rotation Prevents Replay
- Each refresh gives you a new refresh token
- Old refresh token is invalidated
- Check the "Refresh Token" value in Token Info - it changes!

### ✅ Authorization is Enforced
- limited_user cannot access risk or investment endpoints
- 403 Forbidden errors are clear and informative

### ✅ Long Operations Complete Successfully
- 8-second optimization completes despite 10-second token lifetime
- Frontend handles refresh automatically

## Troubleshooting

### "Failed to fetch" errors
- Make sure all 3 servers are running
- Check the console outputs for errors

### CORS errors
- All servers have CORS enabled for localhost
- Try refreshing the browser page

### Token expired errors
- The token lifetime is very short (10s) by design
- If you wait too long between actions, you may need to login again
- The refresh token expires in 30s

### Services return 401 Unauthorized
- Check that the OIDC server is running
- The services fetch the JWKS from the OIDC server to verify tokens

## Next Steps

Once you've verified everything works:
1. Build the MCP Server with stateful token management
2. Build the LangGraph Agent for orchestration
3. Integrate everything for true agentic workflows

See DESIGN.md for the complete plan!
