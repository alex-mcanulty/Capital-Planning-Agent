"""JWT utilities for token creation and validation"""
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import base64
import json

from .config import ISSUER, ACCESS_TOKEN_LIFETIME, REFRESH_TOKEN_LIFETIME


class JWTManager:
    """Manages JWT signing keys and token creation"""

    def __init__(self):
        # Generate RSA keypair on startup
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()

        # Key ID for JWKS
        self.kid = secrets.token_urlsafe(16)

    def create_access_token(self, sub: str, scopes: list[str]) -> str:
        """Create a JWT access token"""
        now = datetime.now(timezone.utc)
        payload = {
            "iss": ISSUER,
            "sub": sub,
            "aud": "capital-planning-api",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ACCESS_TOKEN_LIFETIME)).timestamp()),
            "scope": " ".join(scopes),
            "scopes": scopes
        }

        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid}
        )
        return token

    def create_refresh_token(self, sub: str, scopes: list[str]) -> str:
        """Create a JWT refresh token"""
        now = datetime.now(timezone.utc)
        payload = {
            "iss": ISSUER,
            "sub": sub,
            "aud": "capital-planning-api",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=REFRESH_TOKEN_LIFETIME)).timestamp()),
            "scope": " ".join(scopes),
            "scopes": scopes,
            "token_type": "refresh"
        }

        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid}
        )
        return token

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=["RS256"],
                audience="capital-planning-api",
                issuer=ISSUER,
                leeway=10  # Allow 10 seconds of clock skew
            )
            return payload
        except jwt.ExpiredSignatureError as e:
            print(f"[JWT] Token expired: {e}")
            return None
        except jwt.InvalidAudienceError as e:
            print(f"[JWT] Invalid audience: {e}")
            return None
        except jwt.InvalidIssuerError as e:
            print(f"[JWT] Invalid issuer: {e}")
            return None
        except jwt.InvalidTokenError as e:
            print(f"[JWT] Invalid token: {type(e).__name__}: {e}")
            return None

    def get_jwks(self) -> dict:
        """Get JSON Web Key Set for token verification"""
        public_numbers = self.public_key.public_numbers()

        # Convert to base64url encoded values
        def int_to_base64url(n: int) -> str:
            byte_length = (n.bit_length() + 7) // 8
            n_bytes = n.to_bytes(byte_length, byteorder='big')
            return base64.urlsafe_b64encode(n_bytes).rstrip(b'=').decode('utf-8')

        jwk = {
            "kty": "RSA",
            "use": "sig",
            "kid": self.kid,
            "alg": "RS256",
            "n": int_to_base64url(public_numbers.n),
            "e": int_to_base64url(public_numbers.e)
        }

        return {
            "keys": [jwk]
        }

    def get_public_key_pem(self) -> str:
        """Get public key in PEM format"""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
