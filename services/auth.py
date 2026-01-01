"""JWT authentication and authorization for services"""
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import httpx
from typing import Optional
from functools import lru_cache

from .config import JWKS_URL

security = HTTPBearer()

# Cache for JWKS
_jwks_cache = None


async def get_jwks():
    """Fetch JWKS from OIDC server (cached)"""
    global _jwks_cache

    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            response = await client.get(JWKS_URL)
            response.raise_for_status()
            _jwks_cache = response.json()

    return _jwks_cache


def get_public_key_from_jwks(jwks: dict, kid: str):
    """Extract public key from JWKS"""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            # Convert JWK to PEM
            from jwt.algorithms import RSAAlgorithm
            return RSAAlgorithm.from_jwk(key)
    return None


async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """Verify JWT token and return payload"""
    token = credentials.credentials

    try:
        # Decode header to get kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise HTTPException(status_code=401, detail="Missing kid in token header")

        # Get JWKS and extract public key
        jwks = await get_jwks()
        public_key = get_public_key_from_jwks(jwks, kid)

        if not public_key:
            raise HTTPException(status_code=401, detail="Public key not found for kid")

        # Verify and decode token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="capital-planning-api",
            options={"verify_exp": True}
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def require_scope(required_scope: str):
    """Dependency to require a specific scope"""
    async def scope_checker(token_payload: dict = Depends(verify_token)) -> dict:
        scopes = token_payload.get("scopes", [])

        if required_scope not in scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required scope: {required_scope}"
            )

        return token_payload

    return scope_checker
