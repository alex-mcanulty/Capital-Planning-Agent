"""Service Configuration"""

# OIDC configuration
OIDC_SERVER_URL = "http://localhost:8000"
JWKS_URL = f"{OIDC_SERVER_URL}/jwks"

# Artificial delays for endpoints (in seconds)
ENDPOINT_DELAYS = {
    "get_assets": 2,
    "get_asset": 1,
    "analyze_risk": 5,      # Longer than access token lifetime!
    "optimize_investments": 8  # Longer than access token lifetime!
}

# Scope requirements
SCOPE_REQUIREMENTS = {
    "assets:read": ["GET /assets", "GET /assets/{assetId}"],
    "risk:analyze": ["POST /risk/analyze"],
    "investments:write": ["POST /investments/optimize"]
}
