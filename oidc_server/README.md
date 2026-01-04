# Mock OIDC Server

A simplified OpenID Connect server for development and demonstration purposes. This server implements the core OAuth 2.0 / OIDC flows needed to authenticate users and issue tokens for the Capital Planning Agent system.

## Purpose

This mock server simulates what a production identity provider (like Okta, Auth0, or Azure AD) would provide. It allows the demo to run entirely locally without external dependencies.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/openid-configuration` | GET | OIDC Discovery document |
| `/authorize` | GET | Authorization endpoint (simplified) |
| `/token` | POST | Token endpoint |
| `/userinfo` | GET | UserInfo endpoint |
| `/jwks` | GET | JSON Web Key Set for token verification |
| `/health` | GET | Health check |

## Configuration

All configuration is in `config.py`:

```python
ACCESS_TOKEN_LIFETIME = 10      # Seconds (intentionally short for demo)
REFRESH_TOKEN_LIFETIME = 30     # Seconds (intentionally short for demo)
ROTATE_REFRESH_TOKENS = True    # Enable refresh token rotation
ISSUER = "http://localhost:8000"
CLIENT_ID = "capital-planning-client"
```

## Comparison with Okta

### Similarities (Production-Like Behavior)

| Feature | This Server | Okta |
|---------|-------------|------|
| Authorization Code Flow | Yes | Yes |
| Refresh Token Grant | Yes | Yes |
| Refresh Token Rotation | Yes | Yes (configurable) |
| JWT Access Tokens | RS256-signed | RS256-signed |
| JWKS Endpoint | Yes | Yes |
| OIDC Discovery | Yes | Yes |
| Token Expiration | Enforced | Enforced |
| Scope-Based Authorization | Yes | Yes |
| UserInfo Endpoint | Yes | Yes |

### Differences (Simplified for Demo)

| Feature | This Server | Okta |
|---------|-------------|------|
| Authentication | Direct username/password via query params | Hosted login page with redirect |
| Authorization Code | Returned directly in JSON | Returned via redirect to `redirect_uri` |
| Client Authentication | `client_id` only | `client_id` + `client_secret` (various methods) |
| PKCE | Not implemented | Supported and recommended |
| ID Token | Not issued | Issued with access token |
| Token Introspection | Not implemented | `/introspect` endpoint |
| Token Revocation | Not implemented | `/revoke` endpoint |
| Session Management | In-memory only | Persistent with SSO |
| Multi-Factor Auth | Not implemented | Supported |
| User Management | Hardcoded users | Full user directory |
| Consent Screen | Not implemented | Configurable |
| Audit Logging | Console only | Full audit trail |

## Token Structure

### Access Token Claims

```json
{
  "iss": "http://localhost:8000",
  "sub": "admin_user",
  "aud": "capital-planning-api",
  "iat": 1234567890,
  "exp": 1234567900,
  "scope": "assets:read risk:analyze investments:write",
  "scopes": ["assets:read", "risk:analyze", "investments:write"]
}
```

### Refresh Token Claims

Same as access token, plus:
```json
{
  "token_type": "refresh"
}
```

## Test Users

| Username | Password | Scopes |
|----------|----------|--------|
| `admin_user` | `admin_pass` | `assets:read`, `risk:analyze`, `investments:write` |
| `limited_user` | `limited_pass` | `assets:read` |

## Refresh Token Rotation

When `ROTATE_REFRESH_TOKENS = True`:

1. Client sends refresh token to `/token` endpoint
2. Server validates the refresh token
3. Server **revokes** the old refresh token
4. Server issues a **new** access token AND a **new** refresh token
5. If the old refresh token is used again, it's detected as potential token theft

This matches Okta's "Rotate token after every use" setting.

## Migrating to Okta

To use Okta instead of this mock server:

1. Create an Okta application (Web or SPA type)
2. Configure the authorization server with custom scopes
3. Update environment variables:
   ```
   OIDC_SERVER_URL=https://your-domain.okta.com/oauth2/default
   OIDC_CLIENT_ID=your-client-id
   OIDC_CLIENT_SECRET=your-client-secret
   ```
4. Update the frontend to use Okta's hosted login or SDK
5. The Services API's JWKS validation will work unchanged (just different JWKS URL)

## Known Limitations

- **No persistent storage**: All tokens and sessions are lost on restart
- **No PKCE**: Authorization code flow doesn't require proof key
- **No ID tokens**: Only access and refresh tokens are issued
- **Single-node only**: No distributed session support
- **Hardcoded users**: No user registration or management
