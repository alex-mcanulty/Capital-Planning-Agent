"""Stateful Token Manager for the Capital Planning MCP Server.

This module handles:
- Storing authenticated sessions (access + refresh tokens)
- Checking token validity before API calls
- Transparently refreshing tokens using refresh token rotation
- Tracking refresh chains for debugging/demo purposes
"""
import httpx
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

from .config import (
    OIDC_SERVER_URL,
    OIDC_CLIENT_ID,
    OIDC_CLIENT_SECRET,
    LOG_TOKEN_EVENTS,
)
from .models import TokenSession

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


class AuthenticationError(Exception):
    """Raised when authentication fails or tokens cannot be refreshed."""
    pass


class AuthorizationError(Exception):
    """Raised when user lacks required scope for an operation."""
    pass


class TokenManager:
    """Manages token lifecycle for authenticated sessions.
    
    This is the core stateful component that enables long-running agent
    workflows by transparently refreshing tokens before they expire.
    
    Key features:
    - Stores access and refresh tokens per session
    - Checks token validity before each API call
    - Uses refresh token rotation (gets new refresh token on each refresh)
    - Tracks refresh chain for debugging
    """

    def __init__(self):
        """Initialize the token manager."""
        self._sessions: dict[str, TokenSession] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    # ==========================================================================
    # Session Management
    # ==========================================================================

    async def create_session(
        self,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        refresh_expires_in: int,
        scopes: list[str],
        user_id: str,
    ) -> str:
        """Create a new authenticated session.
        
        Args:
            access_token: The access token from OIDC server
            refresh_token: The refresh token from OIDC server
            expires_in: Access token lifetime in seconds
            refresh_expires_in: Refresh token lifetime in seconds
            scopes: List of granted scopes
            user_id: User identifier (sub claim)
            
        Returns:
            Session ID that can be used for subsequent API calls
        """
        session_id = secrets.token_urlsafe(32)
        now = utc_now()

        session = TokenSession(
            session_id=session_id,
            user_id=user_id,
            access_token=access_token,
            access_token_expires_at=now + timedelta(seconds=expires_in),
            refresh_token=refresh_token,
            refresh_token_expires_at=now + timedelta(seconds=refresh_expires_in),
            scopes=scopes,
            created_at=now,
        )

        self._sessions[session_id] = session

        if LOG_TOKEN_EVENTS:
            logger.info(
                f"[TokenManager] Session created: {session_id[:8]}... "
                f"user={user_id}, scopes={scopes}, "
                f"access_expires_in={expires_in}s, refresh_expires_in={refresh_expires_in}s"
            )

        return session_id

    def get_session(self, session_id: str) -> Optional[TokenSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session (logout)."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            if LOG_TOKEN_EVENTS:
                logger.info(f"[TokenManager] Session deleted: {session_id[:8]}...")
            return True
        return False

    @property
    def session_count(self) -> int:
        """Get the number of active sessions."""
        return len(self._sessions)

    # ==========================================================================
    # Token Validation and Refresh
    # ==========================================================================

    async def ensure_valid_token(self, session_id: str) -> str:
        """Get the access token for a session.

        This method returns the current access token. Token refresh is handled
        exclusively by the global heartbeat (every 8s), which ensures tokens
        are always fresh. This eliminates race conditions from concurrent refresh.

        Args:
            session_id: The session to get the token for

        Returns:
            The current access token

        Raises:
            AuthenticationError: If session doesn't exist or token has expired
        """
        session = self._sessions.get(session_id)
        if not session:
            raise AuthenticationError(f"Session not found: {session_id[:8]}...")

        now = utc_now()

        # Check if access token is still valid
        if session.access_token_expires_at > now:
            if LOG_TOKEN_EVENTS:
                remaining = (session.access_token_expires_at - now).total_seconds()
                logger.debug(
                    f"[TokenManager] Access token valid: {session_id[:8]}... "
                    f"({remaining:.1f}s remaining)"
                )
            return session.access_token

        # Access token expired - this shouldn't happen if heartbeat is working
        # Log a warning and return the token anyway (let the API reject it if needed)
        if LOG_TOKEN_EVENTS:
            logger.warning(
                f"[TokenManager] Access token expired for session {session_id[:8]}... "
                f"Heartbeat may not be running frequently enough. "
                f"Expired {(now - session.access_token_expires_at).total_seconds():.1f}s ago"
            )

        # Return the expired token - the Services API will reject it with 401
        # This is better than trying to refresh here and causing race conditions
        return session.access_token

    async def _refresh_tokens(self, session: TokenSession) -> None:
        """Refresh tokens using the refresh token grant.
        
        This implements refresh token rotation - the OIDC server returns
        BOTH a new access token AND a new refresh token. We store both,
        extending the session lifetime indefinitely as long as the agent
        remains active.
        
        Args:
            session: The session to refresh
            
        Raises:
            AuthenticationError: If refresh fails
        """
        client = await self._get_http_client()

        try:
            response = await client.post(
                f"{OIDC_SERVER_URL}/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": session.refresh_token,
                    "client_id": OIDC_CLIENT_ID,
                    "client_secret": OIDC_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_detail = response.text
                if LOG_TOKEN_EVENTS:
                    logger.error(
                        f"[TokenManager] Refresh failed for session {session.session_id[:8]}...: "
                        f"{response.status_code} - {error_detail}"
                    )
                raise AuthenticationError(
                    f"Token refresh failed: {response.status_code}. User may need to re-authenticate."
                )

            token_data = response.json()
            now = utc_now()

            # Update session with new tokens (ROTATION - both tokens are new!)
            session.access_token = token_data["access_token"]
            session.access_token_expires_at = now + timedelta(
                seconds=token_data.get("expires_in", 300)
            )

            # Store the NEW refresh token (this is the key to rotation)
            if "refresh_token" in token_data:
                session.refresh_token = token_data["refresh_token"]
                # Use 30s to match OIDC server config (heartbeat refreshes every 25s)
                # The OIDC server doesn't return refresh_expires_in, so we hardcode it
                refresh_expires_in = token_data.get("refresh_expires_in", 30)
                session.refresh_token_expires_at = now + timedelta(seconds=refresh_expires_in)

            session.last_refreshed_at = now
            session.refresh_count += 1

            if LOG_TOKEN_EVENTS:
                logger.info(
                    f"[TokenManager] Tokens refreshed for session {session.session_id[:8]}... "
                    f"(refresh #{session.refresh_count}). "
                    f"New access token expires in {token_data.get('expires_in', 300)}s"
                )

        except httpx.RequestError as e:
            if LOG_TOKEN_EVENTS:
                logger.error(
                    f"[TokenManager] Network error during refresh for session "
                    f"{session.session_id[:8]}...: {e}"
                )
            raise AuthenticationError(f"Token refresh failed due to network error: {e}")

    # ==========================================================================
    # Authorization Checking
    # ==========================================================================

    def check_authorization(self, session_id: str, required_scopes: list[str]) -> None:
        """Check if the session has the required scopes.
        
        Args:
            session_id: The session to check
            required_scopes: List of scopes required for the operation
            
        Raises:
            AuthenticationError: If session doesn't exist
            AuthorizationError: If session lacks required scopes
        """
        session = self._sessions.get(session_id)
        if not session:
            raise AuthenticationError(f"Session not found: {session_id[:8]}...")

        missing_scopes = [s for s in required_scopes if s not in session.scopes]
        if missing_scopes:
            if LOG_TOKEN_EVENTS:
                logger.warning(
                    f"[TokenManager] Authorization denied for session {session_id[:8]}... "
                    f"Missing scopes: {missing_scopes}"
                )
            raise AuthorizationError(
                f"Access denied: User lacks required scope(s): {missing_scopes}. "
                f"User has: {session.scopes}"
            )

    def get_user_scopes(self, session_id: str) -> list[str]:
        """Get the scopes for a session."""
        session = self._sessions.get(session_id)
        if not session:
            raise AuthenticationError(f"Session not found: {session_id[:8]}...")
        return session.scopes.copy()

    # ==========================================================================
    # Heartbeat Token Refresh
    # ==========================================================================

    async def refresh_all_sessions(self) -> dict:
        """Refresh tokens for all active sessions.

        This method is called by the global heartbeat to proactively refresh
        all tokens every 25 seconds, regardless of their current expiration state.
        This ensures tokens never expire during long-running workflows.

        Returns:
            Dictionary with refresh statistics:
            - total_sessions: Total number of sessions
            - refreshed: Number of sessions successfully refreshed
            - failed: Number of sessions that failed to refresh
            - errors: List of error messages
        """
        stats = {
            "total_sessions": len(self._sessions),
            "refreshed": 0,
            "failed": 0,
            "errors": []
        }

        now = utc_now()

        for session_id, session in list(self._sessions.items()):
            try:
                # Log timing information
                access_remaining = (session.access_token_expires_at - now).total_seconds()
                refresh_remaining = (session.refresh_token_expires_at - now).total_seconds()

                if LOG_TOKEN_EVENTS:
                    logger.info(
                        f"[TokenManager] Heartbeat refreshing session {session_id[:8]}... "
                        f"access_remaining={access_remaining:.1f}s, refresh_remaining={refresh_remaining:.1f}s"
                    )

                # Always refresh - don't check expiration times
                # The heartbeat runs every 25s which is less than both
                # access token (10s) and refresh token (30s) lifetimes
                await self._refresh_tokens(session)
                stats["refreshed"] += 1

                if LOG_TOKEN_EVENTS:
                    logger.info(f"[TokenManager] Heartbeat: Session {session_id[:8]}... refreshed successfully")

            except Exception as e:
                error_msg = f"Session {session_id[:8]}... refresh failed: {str(e)}"
                if LOG_TOKEN_EVENTS:
                    logger.error(f"[TokenManager] Heartbeat: {error_msg}")
                stats["failed"] += 1
                stats["errors"].append(error_msg)

        return stats

    # ==========================================================================
    # Debug/Demo Utilities
    # ==========================================================================

    def get_session_stats(self, session_id: str) -> dict:
        """Get statistics about a session for debugging/demo purposes."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        now = utc_now()
        return {
            "session_id": session.session_id[:8] + "...",
            "user_id": session.user_id,
            "scopes": session.scopes,
            "access_token_expires_in_seconds": max(
                0, (session.access_token_expires_at - now).total_seconds()
            ),
            "refresh_token_expires_in_seconds": max(
                0, (session.refresh_token_expires_at - now).total_seconds()
            ),
            "refresh_count": session.refresh_count,
            "created_at": session.created_at.isoformat(),
            "last_refreshed_at": (
                session.last_refreshed_at.isoformat() if session.last_refreshed_at else None
            ),
        }


# Global token manager instance
token_manager = TokenManager()
