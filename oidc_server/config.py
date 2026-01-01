"""OIDC Server Configuration"""

# Token lifetimes (in seconds)
ACCESS_TOKEN_LIFETIME = 10
REFRESH_TOKEN_LIFETIME = 30
ROTATE_REFRESH_TOKENS = True

# Server configuration
ISSUER = "http://localhost:8000"
CLIENT_ID = "capital-planning-client"

# Hardcoded users for demo
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
