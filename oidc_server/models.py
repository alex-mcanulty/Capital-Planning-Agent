"""Pydantic models for OIDC server"""
from pydantic import BaseModel
from typing import Optional


class TokenRequest(BaseModel):
    grant_type: str
    code: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: str
    redirect_uri: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: str


class AuthorizeRequest(BaseModel):
    username: str
    password: str
    client_id: str
    redirect_uri: Optional[str] = None
    response_type: str = "code"


class UserInfo(BaseModel):
    sub: str
    name: str
    email: str
    scopes: list[str]
