"""API Client for Capital Planning Services.

This client automatically handles token management - before each request,
it ensures the access token is valid (refreshing if needed) and includes
it in the Authorization header.
"""
import httpx
import json
from typing import Any, Optional
import logging

from .config import SERVICES_BASE_URL, TOOL_SCOPE_REQUIREMENTS
from .token_manager import token_manager, AuthenticationError, AuthorizationError
from .models import (
    Asset,
    RiskAnalysisResponse,
    InvestmentOptimizationResponse,
    InvestmentCandidate,
)

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when an API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class CapitalPlanningAPIClient:
    """Client for the Capital Planning Services API.
    
    This client:
    - Automatically refreshes tokens before requests (via token_manager)
    - Checks user authorization before making requests
    - Provides typed methods for each API endpoint
    """

    def __init__(self):
        """Initialize the API client."""
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=SERVICES_BASE_URL,
                timeout=60.0,  # Long timeout for slow operations
            )
        return self._http_client

    async def close(self):
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        session_id: str,
        required_scopes: list[str],
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> Any:
        """Make an authenticated request to the API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            session_id: Session ID for authentication
            required_scopes: Scopes required for this operation
            params: Query parameters
            json_body: JSON request body
            
        Returns:
            Parsed JSON response
            
        Raises:
            AuthenticationError: If authentication fails
            AuthorizationError: If user lacks required scopes
            APIError: If the API request fails
        """
        # Check authorization BEFORE making the request
        token_manager.check_authorization(session_id, required_scopes)

        # Get a valid access token (may trigger refresh)
        access_token = await token_manager.ensure_valid_token(session_id)

        # Make the request
        client = await self._get_http_client()
        headers = {"Authorization": f"Bearer {access_token}"}

        logger.debug(f"[APIClient] {method} {endpoint} - session {session_id[:8]}...")

        try:
            if method.upper() == "GET":
                response = await client.get(endpoint, params=params, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(endpoint, json=json_body, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if response.status_code == 401:
                raise AuthenticationError(
                    "API returned 401 Unauthorized. Token may have been revoked."
                )
            elif response.status_code == 403:
                raise AuthorizationError(
                    f"API returned 403 Forbidden. User lacks permission for this operation."
                )
            elif response.status_code == 404:
                raise APIError("Resource not found", status_code=404)
            elif response.status_code >= 400:
                error_detail = response.text
                raise APIError(
                    f"API error {response.status_code}: {error_detail}",
                    status_code=response.status_code
                )

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"[APIClient] Network error: {e}")
            raise APIError(f"Network error: {e}")

    # ==========================================================================
    # Asset Service Methods
    # ==========================================================================

    async def get_assets(
        self,
        session_id: str,
        portfolio_id: str = "default"
    ) -> list[Asset]:
        """Get all assets in a portfolio.
        
        Args:
            session_id: Authenticated session ID
            portfolio_id: Portfolio to fetch assets from
            
        Returns:
            List of Asset objects
        """
        data = await self._make_request(
            method="GET",
            endpoint="/assets",
            session_id=session_id,
            required_scopes=TOOL_SCOPE_REQUIREMENTS["capital_get_assets"],
            params={"portfolio_id": portfolio_id},
        )
        return [Asset(**asset) for asset in data]

    async def get_asset(
        self,
        session_id: str,
        asset_id: str
    ) -> Asset:
        """Get a single asset by ID.
        
        Args:
            session_id: Authenticated session ID
            asset_id: Asset ID to fetch
            
        Returns:
            Asset object
        """
        data = await self._make_request(
            method="GET",
            endpoint=f"/assets/{asset_id}",
            session_id=session_id,
            required_scopes=TOOL_SCOPE_REQUIREMENTS["capital_get_asset"],
        )
        return Asset(**data)

    # ==========================================================================
    # Risk Service Methods
    # ==========================================================================

    async def analyze_risk(
        self,
        session_id: str,
        asset_ids: list[str],
        horizon_months: int = 12
    ) -> RiskAnalysisResponse:
        """Analyze risk for given assets.
        
        Args:
            session_id: Authenticated session ID
            asset_ids: List of asset IDs to analyze
            horizon_months: Time horizon for analysis
            
        Returns:
            RiskAnalysisResponse with risk scores for each asset
        """
        data = await self._make_request(
            method="POST",
            endpoint="/risk/analyze",
            session_id=session_id,
            required_scopes=TOOL_SCOPE_REQUIREMENTS["capital_analyze_risk"],
            json_body={
                "asset_ids": asset_ids,
                "horizon_months": horizon_months,
            },
        )
        return RiskAnalysisResponse(**data)

    # ==========================================================================
    # Investment Service Methods
    # ==========================================================================

    async def optimize_investments(
        self,
        session_id: str,
        candidates: list[InvestmentCandidate],
        budget: float,
        horizon_months: int = 12
    ) -> InvestmentOptimizationResponse:
        """Optimize investment plan.
        
        Args:
            session_id: Authenticated session ID
            candidates: List of investment candidates
            budget: Total budget available
            horizon_months: Planning horizon
            
        Returns:
            InvestmentOptimizationResponse with optimized plan
        """
        data = await self._make_request(
            method="POST",
            endpoint="/investments/optimize",
            session_id=session_id,
            required_scopes=TOOL_SCOPE_REQUIREMENTS["capital_optimize_investments"],
            json_body={
                "candidates": [c.model_dump() for c in candidates],
                "budget": budget,
                "horizon_months": horizon_months,
            },
        )
        return InvestmentOptimizationResponse(**data)


# Global API client instance
api_client = CapitalPlanningAPIClient()
