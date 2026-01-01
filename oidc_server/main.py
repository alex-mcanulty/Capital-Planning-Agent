"""Mock OIDC Server with token rotation support"""
from fastapi import FastAPI, HTTPException, Form, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import (
    USERS, ISSUER, CLIENT_ID,
    ACCESS_TOKEN_LIFETIME, REFRESH_TOKEN_LIFETIME,
    ROTATE_REFRESH_TOKENS
)
from .jwt_utils import JWTManager
from .models import TokenResponse, UserInfo

app = FastAPI(title="Mock OIDC Server")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize JWT manager
jwt_manager = JWTManager()

# In-memory storage for authorization codes and refresh tokens
auth_codes = {}  # code -> {sub, scopes, expires, used}
refresh_tokens_store = {}  # token_id -> {sub, scopes, expires, revoked, parent}


@app.get("/.well-known/openid-configuration")
async def openid_configuration():
    """OIDC Discovery endpoint"""
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "jwks_uri": f"{ISSUER}/jwks",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["assets:read", "risk:analyze", "investments:write"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
    }


@app.get("/authorize")
async def authorize(
    username: str = Query(...),
    password: str = Query(...),
    client_id: str = Query(...),
    response_type: str = Query(default="code"),
    redirect_uri: Optional[str] = Query(default=None)
):
    """
    Simplified authorization endpoint
    In a real OIDC flow, this would show a login page and redirect
    For demo purposes, we accept credentials directly and return a code
    """
    if client_id != CLIENT_ID:
        raise HTTPException(status_code=400, detail="Invalid client_id")

    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only 'code' response_type supported")

    # Validate credentials
    if username not in USERS:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = USERS[username]
    if user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate authorization code
    code = secrets.token_urlsafe(32)
    auth_codes[code] = {
        "sub": user["sub"],
        "scopes": user["scopes"],
        "expires": datetime.now(timezone.utc) + timedelta(seconds=60),
        "used": False
    }

    return {
        "code": code,
        "state": "demo_state"
    }


@app.post("/token")
async def token(
    grant_type: str = Form(...),
    code: Optional[str] = Form(default=None),
    refresh_token: Optional[str] = Form(default=None),
    client_id: str = Form(...)
):
    """
    Token endpoint supporting:
    - authorization_code grant
    - refresh_token grant with rotation
    """
    if client_id != CLIENT_ID:
        raise HTTPException(status_code=400, detail="Invalid client_id")

    if grant_type == "authorization_code":
        return await handle_authorization_code_grant(code)
    elif grant_type == "refresh_token":
        return await handle_refresh_token_grant(refresh_token)
    else:
        raise HTTPException(status_code=400, detail="Unsupported grant_type")


async def handle_authorization_code_grant(code: str):
    """Handle authorization_code grant type"""
    if not code or code not in auth_codes:
        raise HTTPException(status_code=400, detail="Invalid authorization code")

    code_data = auth_codes[code]

    # Check if already used (prevent replay)
    if code_data["used"]:
        raise HTTPException(status_code=400, detail="Authorization code already used")

    # Check expiration
    if datetime.now(timezone.utc) > code_data["expires"]:
        raise HTTPException(status_code=400, detail="Authorization code expired")

    # Mark as used
    code_data["used"] = True

    # Create tokens
    access_token = jwt_manager.create_access_token(code_data["sub"], code_data["scopes"])
    refresh_token = jwt_manager.create_refresh_token(code_data["sub"], code_data["scopes"])

    # Store refresh token metadata
    refresh_token_id = secrets.token_urlsafe(32)
    refresh_tokens_store[refresh_token] = {
        "id": refresh_token_id,
        "sub": code_data["sub"],
        "scopes": code_data["scopes"],
        "expires": datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_LIFETIME),
        "revoked": False,
        "parent": None
    }

    print(f"[OIDC] Issued tokens for user: {code_data['sub']}")

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_LIFETIME,
        refresh_token=refresh_token,
        scope=" ".join(code_data["scopes"])
    ).model_dump()


async def handle_refresh_token_grant(refresh_token: str):
    """Handle refresh_token grant with rotation"""
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Missing refresh_token")

    # Validate the refresh token JWT
    payload = jwt_manager.verify_token(refresh_token)
    if not payload or payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Check if token is in our store
    if refresh_token not in refresh_tokens_store:
        raise HTTPException(status_code=401, detail="Unknown refresh token")

    token_data = refresh_tokens_store[refresh_token]

    # Check if revoked
    if token_data["revoked"]:
        # Potential token theft - revoke entire chain
        print(f"[OIDC] WARNING: Refresh token reuse detected for user {token_data['sub']}! Revoking session.")
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    # Check expiration
    if datetime.now(timezone.utc) > token_data["expires"]:
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Revoke the old refresh token
    token_data["revoked"] = True

    # Create new tokens
    access_token = jwt_manager.create_access_token(token_data["sub"], token_data["scopes"])

    if ROTATE_REFRESH_TOKENS:
        # Issue new refresh token
        new_refresh_token = jwt_manager.create_refresh_token(token_data["sub"], token_data["scopes"])

        # Store new refresh token metadata
        new_token_id = secrets.token_urlsafe(32)
        refresh_tokens_store[new_refresh_token] = {
            "id": new_token_id,
            "sub": token_data["sub"],
            "scopes": token_data["scopes"],
            "expires": datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_LIFETIME),
            "revoked": False,
            "parent": token_data["id"]
        }

        print(f"[OIDC] Rotated refresh token for user: {token_data['sub']}")

        return TokenResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_LIFETIME,
            refresh_token=new_refresh_token,
            scope=" ".join(token_data["scopes"])
        ).model_dump()
    else:
        # Reuse same refresh token (update expiry)
        token_data["revoked"] = False
        token_data["expires"] = datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_LIFETIME)

        print(f"[OIDC] Refreshed access token for user: {token_data['sub']}")

        return TokenResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_LIFETIME,
            refresh_token=refresh_token,
            scope=" ".join(token_data["scopes"])
        ).model_dump()


@app.get("/userinfo")
async def userinfo(authorization: Optional[str] = Header(None)):
    """UserInfo endpoint"""
    # Debug logging
    print(f"[OIDC] /userinfo called, authorization header: {authorization}")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization.replace("Bearer ", "")
    payload = jwt_manager.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get user data
    username = payload["sub"]
    if username not in USERS:
        raise HTTPException(status_code=404, detail="User not found")

    user = USERS[username]

    print(f"[OIDC] Returning userinfo for: {username}")

    return UserInfo(
        sub=user["sub"],
        name=user["name"],
        email=user["email"],
        scopes=user["scopes"]
    ).model_dump()


@app.get("/jwks")
async def jwks():
    """JSON Web Key Set endpoint"""
    return jwt_manager.get_jwks()


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "oidc-server"}


if __name__ == "__main__":
    import uvicorn
    print("[OIDC] Starting Mock OIDC Server on port 8000")
    print(f"[OIDC] Access token lifetime: {ACCESS_TOKEN_LIFETIME}s")
    print(f"[OIDC] Refresh token lifetime: {REFRESH_TOKEN_LIFETIME}s")
    print(f"[OIDC] Refresh token rotation: {ROTATE_REFRESH_TOKENS}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
